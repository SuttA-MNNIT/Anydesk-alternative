using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using SIPSorcery.Net;

namespace CampusLink.Client {
    // A reliable ordered WebRTC data channel carries application-encrypted packets.
    // Acknowledgements and bounded replay bridge a broken direct path onto WSS.
    public sealed class HybridTransport : IPacketTransport {
        readonly BrokerNetwork broker;
        readonly bool host,forceRelay;
        readonly CryptoChannel signalCrypto;
        readonly SemaphoreSlim sending=new SemaphoreSlim(1,1),signaling=new SemaphoreSlim(1,1);
        readonly object gate=new object(),signalGate=new object();
        readonly SortedDictionary<long,byte[]> pending=new SortedDictionary<long,byte[]>(),waiting=new SortedDictionary<long,byte[]>();
        readonly ConcurrentQueue<Tuple<bool,byte[]>> incoming=new ConcurrentQueue<Tuple<bool,byte[]>>();
        readonly TaskCompletionSource<bool> settled=new TaskCompletionSource<bool>();
        readonly CancellationTokenSource stopped=new CancellationTokenSource();
        readonly List<string> candidates=new List<string>(),earlySignals=new List<string>();
        readonly ConcurrentQueue<string> signalQueue=new ConcurrentQueue<string>();
        int signalProcessing;
        bool signalReady;
        RTCPeerConnection pc;
        RTCDataChannel dc;
        bool direct,relay,ready,remoteDescription,disposed;
        int processing,queuedBytes,pendingBytes;
        long sequence,expected;
        DateTime lastProgress=DateTime.UtcNow;
        MemoryStream assembly;
        long assembling;
        int total;
        public readonly string Id;
        public Func<byte[],Task> Packet {get;set;}
        public Action<string> Ended {get;set;}
        public Action<string> Changed {get;set;}
        public string Name {get{return direct&&!relay?"Direct P2P · encrypted":ready&&!settled.Task.IsCompleted?"Checking direct connection…":"Encrypted relay";}}
        public HybridTransport(BrokerNetwork owner,string id,string key,bool isHost,bool forced) {
            broker=owner;Id=id;host=isHost;forceRelay=forced;
            signalCrypto=new CryptoChannel(key,id+"/signaling",host);
            Run(Watchdog);
        }
        void Update(){var callback=Changed;if(callback!=null)callback(Name);}
        void Debug(Exception error){var callback=broker.Diagnostic;if(callback!=null)callback(error.ToString());}
        void Trace(string text){var callback=broker.Diagnostic;if(callback!=null)callback((host?"host: ":"viewer: ")+text);}
        void Run(Func<Task> work){Task.Run(async delegate{try{await work();}catch(Exception error){if(!disposed){Debug(error);UseRelay();}}});}
        public async Task Ready(bool initiate) {
            lock(gate){if(ready)return;ready=true;}
            if(host)await broker.Control(new{type="ready",sessionId=Id});
            Update();
            if(forceRelay||relay){UseRelay();return;}
            try {
                pc=new RTCPeerConnection(new RTCConfiguration{
                    iceServers=broker.StunServers.Select(url=>new RTCIceServer{urls=url}).ToList(),
                    X_ICEIncludeAllInterfaceAddresses=true
                });
                pc.ondatachannel+=Bind;
                pc.onicecandidate+=candidate=>{if(candidate!=null){Trace("local ICE candidate");Run(()=>SendSignal(candidate.toJSON()));}};
                pc.oniceconnectionstatechange+=state=>Trace("ICE "+state);
                pc.onconnectionstatechange+=state=>{Trace("connection "+state);if(state==RTCPeerConnectionState.failed||state==RTCPeerConnectionState.disconnected||state==RTCPeerConnectionState.closed)UseRelay();};
                if(initiate){Bind(await pc.createDataChannel("CampusLink/4",new RTCDataChannelInit{ordered=true}));var offer=pc.createOffer();await pc.setLocalDescription(offer);await SendSignal(offer.toJSON());}
                lock(signalGate){signalReady=true;foreach(string signal in earlySignals)signalQueue.Enqueue(signal);earlySignals.Clear();}
                DrainSignals();
                if(await Task.WhenAny(settled.Task,Task.Delay(10000,stopped.Token))!=settled.Task){Trace("direct setup timeout");UseRelay();}
                await settled.Task;
            } catch(Exception error){if(!disposed){Debug(error);UseRelay();}}
        }
        void Bind(RTCDataChannel channel) {
            if(dc!=null && dc!=channel){channel.close();return;}
            dc=channel;
            Trace("data channel bound");
            Action opened=()=>{Trace("data channel open");lock(gate){if(disposed||relay)return;direct=true;settled.TrySetResult(true);}Update();};
            channel.onopen+=opened;
            channel.onclose+=UseRelay;
            channel.onmessage+=(ch,type,data)=>{if(type==DataChannelPayloadProtocols.WebRTC_Binary)Queue(true,data);};
            if(channel.readyState==RTCDataChannelState.open)opened();
        }
        async Task SendSignal(string text) {
            if(disposed||relay)return;
            await signaling.WaitAsync(stopped.Token);
            try{byte[] packet;lock(signalGate)packet=signalCrypto.Seal(1,Encoding.UTF8.GetBytes(text));await broker.Control(new{type="signal",sessionId=Id,payload=Convert.ToBase64String(packet)});}finally{signaling.Release();}
        }
        public void Signal(string text) {
            if(disposed||relay)return;
            lock(signalGate){if(!signalReady){if(earlySignals.Count>=64){Fail("Too many connection signals.");return;}earlySignals.Add(text);return;}if(signalQueue.Count>=64){Fail("Too many connection signals.");return;}signalQueue.Enqueue(text);}
            DrainSignals();
        }
        void DrainSignals() {
            if(Interlocked.CompareExchange(ref signalProcessing,1,0)!=0)return;
            Run(async delegate{try{string text;while(!disposed&&signalQueue.TryDequeue(out text)){await signaling.WaitAsync(stopped.Token);try{await ProcessSignal(text);}finally{signaling.Release();}}}finally{Interlocked.Exchange(ref signalProcessing,0);if(!disposed&&!signalQueue.IsEmpty)DrainSignals();}});
        }
        async Task ProcessSignal(string encoded) {
            if(disposed||relay)return;
            byte[] plain;lock(signalGate)plain=signalCrypto.Open(Convert.FromBase64String(encoded));
            if(plain[0]!=1||plain.Length>16384)throw new InvalidDataException();
            string text=Encoding.UTF8.GetString(plain,1,plain.Length-1);
            RTCIceCandidateInit candidate;RTCSessionDescriptionInit description;
            if(RTCIceCandidateInit.TryParse(text,out candidate)) {
                Trace("remote ICE candidate");
                if(!remoteDescription){if(candidates.Count>=64)throw new InvalidDataException();candidates.Add(text);}else pc.addIceCandidate(candidate);
            } else if(RTCSessionDescriptionInit.TryParse(text,out description)) {
                Trace("remote description "+description.type);
                if((host&&description.type!=RTCSdpType.offer)||(!host&&description.type!=RTCSdpType.answer)||remoteDescription)throw new InvalidDataException();
                if(pc.setRemoteDescription(description)!=SetDescriptionResultEnum.OK)throw new InvalidDataException();
                remoteDescription=true;
                foreach(string item in candidates){RTCIceCandidateInit c;if(RTCIceCandidateInit.TryParse(item,out c))pc.addIceCandidate(c);}candidates.Clear();
                if(host){var answer=pc.createAnswer();await pc.setLocalDescription(answer);
                    // The signal gate is already held on the receive path.
                    byte[] packet;lock(signalGate)packet=signalCrypto.Seal(1,Encoding.UTF8.GetBytes(answer.toJSON()));
                    await broker.Control(new{type="signal",sessionId=Id,payload=Convert.ToBase64String(packet)});
                }
            }else throw new InvalidDataException();
        }
        static long Read64(byte[] data,int offset){long n=0;for(int i=0;i<8;i++)n=(n<<8)|data[offset+i];return n;}
        static void Write64(byte[] data,int offset,long n){for(int i=7;i>=0;i--){data[offset+i]=(byte)n;n>>=8;}}
        static int Read32(byte[] data,int offset){return (data[offset]<<24)|(data[offset+1]<<16)|(data[offset+2]<<8)|data[offset+3];}
        static void Write32(byte[] data,int offset,int n){for(int i=3;i>=0;i--){data[offset+i]=(byte)n;n>>=8;}}
        public async Task Send(byte[] packet) {
            if(packet.Length>3*1024*1024)throw new InvalidDataException();
            await sending.WaitAsync(stopped.Token);
            try {
                if(disposed)return;
                long n=sequence++;byte[] envelope=new byte[8+packet.Length];Write64(envelope,0,n);Buffer.BlockCopy(packet,0,envelope,8,packet.Length);
                lock(gate){if(pendingBytes+envelope.Length>4*1024*1024||pending.Count>=128)throw new IOException("Connection is too slow.");if(pending.Count==0)lastProgress=DateTime.UtcNow;pending.Add(n,envelope);pendingBytes+=envelope.Length;}
                if(direct&&!relay) {
                    bool failed=false;
                    try {
                        for(int offset=0;offset<envelope.Length;offset+=16000) {
                            DateTime start=DateTime.UtcNow;
                            while(dc.bufferedAmount>512*1024){if(relay||disposed||(DateTime.UtcNow-start).TotalSeconds>2)throw new IOException();await Task.Delay(5,stopped.Token);}
                            if(relay||disposed)throw new IOException();
                            int size=Math.Min(16000,envelope.Length-offset);var chunk=new byte[16+size];Write64(chunk,0,n);Write32(chunk,8,envelope.Length);Write32(chunk,12,offset);Buffer.BlockCopy(envelope,offset,chunk,16,size);dc.send(chunk);
                        }
                    }catch{failed=true;UseRelay();}
                    if(failed)await broker.Relay(Id,envelope);
                }else await broker.Relay(Id,envelope);
            }finally{sending.Release();}
        }
        public void Acknowledge(long n) {
            lock(gate){if(n<0||n>=sequence)return;foreach(long key in pending.Keys.TakeWhile(x=>x<=n).ToArray()){pendingBytes-=pending[key].Length;pending.Remove(key);}lastProgress=DateTime.UtcNow;}
        }
        public void Enqueue(byte[] packet){Queue(false,packet);}
        void Queue(bool chunk,byte[] data) {
            if(disposed)return;
            if(Interlocked.Add(ref queuedBytes,data.Length)>8*1024*1024){Interlocked.Add(ref queuedBytes,-data.Length);Fail("Incoming connection is too fast.");return;}
            incoming.Enqueue(Tuple.Create(chunk,data));Drain();
        }
        void Drain() {
            if(Interlocked.CompareExchange(ref processing,1,0)!=0)return;
            Task.Run(async delegate {
                try {
                    Tuple<bool,byte[]> item;
                    while(!disposed&&incoming.TryDequeue(out item)) {
                        Interlocked.Add(ref queuedBytes,-item.Item2.Length);
                        byte[] envelope=item.Item2;
                        if(item.Item1) {
                            if(envelope.Length<17)throw new InvalidDataException();long n=Read64(envelope,0);int length=Read32(envelope,8),offset=Read32(envelope,12);
                            if(n<expected)continue;
                            if(length<46||length>3*1024*1024+8||offset<0||offset>length||envelope.Length-16>length-offset)throw new InvalidDataException();
                            if(offset==0){if(assembly!=null)assembly.Dispose();assembly=new MemoryStream(length);assembling=n;total=length;}
                            if(assembly==null||assembling!=n||assembly.Length!=offset||length!=total)continue;
                            assembly.Write(envelope,16,envelope.Length-16);
                            if(assembly.Length!=total)continue;
                            envelope=assembly.ToArray();assembly.Dispose();assembly=null;
                        }
                        if(envelope.Length<46)throw new InvalidDataException();long number=Read64(envelope,0);
                        if(number<0||number>expected+128)throw new InvalidDataException();
                        if(number>=expected) {
                            if(!waiting.ContainsKey(number)){if(waiting.Sum(x=>x.Value.Length)+envelope.Length>4*1024*1024)throw new IOException();waiting[number]=envelope;}
                            while(waiting.ContainsKey(expected)) {
                                var bytes=waiting[expected];waiting.Remove(expected);
                                var handler=Packet;if(handler==null)throw new IOException();await handler(bytes.Skip(8).ToArray());expected++;
                            }
                        }
                        if(expected>0)await broker.Control(new{type="ack",sessionId=Id,n=expected-1});
                    }
                }catch(Exception error){if(!disposed){Debug(error);Fail("Encrypted session validation failed.");}}
                finally{Interlocked.Exchange(ref processing,0);if(!disposed&&!incoming.IsEmpty)Drain();}
            });
        }
        public void UseRelay() {
            lock(gate){if(disposed||relay)return;relay=true;direct=false;settled.TrySetResult(false);}
            Update();
            Run(async delegate {
                await broker.Control(new{type="fallback",sessionId=Id});
                await sending.WaitAsync(stopped.Token);
                try{byte[][] packets;lock(gate)packets=pending.Values.ToArray();foreach(byte[] packet in packets)await broker.Relay(Id,packet);}finally{sending.Release();}
                if(pc!=null)pc.Close("Using encrypted relay");
            });
        }
#if CAMPUSLINK_TESTS
        public void InterruptDirect(){if(pc!=null)pc.Close("Test interruption of direct transport");}
#endif
        async Task Watchdog() {
            while(!stopped.IsCancellationRequested){await Task.Delay(500,stopped.Token);bool overdue;lock(gate)overdue=pending.Count>0&&(DateTime.UtcNow-lastProgress).TotalSeconds>3;if(overdue){if(direct)UseRelay();else if((DateTime.UtcNow-lastProgress).TotalSeconds>15)Fail("The connection stopped responding.");}}
        }
        public void Fail(string reason){var callback=Ended;Dispose();if(callback!=null)callback(reason);}
        public void Dispose() {
            lock(gate){if(disposed)return;disposed=true;direct=false;pending.Clear();pendingBytes=0;settled.TrySetResult(false);}
            stopped.Cancel();if(pc!=null)pc.Close("Disconnected");broker.Release(this);
            Task.Run(async delegate{await signaling.WaitAsync();try{lock(signalGate)signalCrypto.Dispose();}finally{signaling.Release();}});
        }
    }
}

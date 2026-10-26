using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace CampusLink.Client {
    public sealed class ClientSession : IDisposable {
        readonly ClientWebSocket socket=new ClientWebSocket();
        readonly CancellationTokenSource stop=new CancellationTokenSource();
        readonly SemaphoreSlim sendGate=new SemaphoreSlim(1,1);
        readonly object cryptoGate=new object(),stateGate=new object();
        readonly IInput input;
        readonly Queue<Tuple<DateTime,int>> pending=new Queue<Tuple<DateTime,int>>();
        int pendingBytes;
        CryptoChannel channel;
        IPacketTransport transport;
        bool hosting,approvalWaiting;
        string sessionId,reverseOut,reverseIn;
        bool reverseControl,finished;
        int generation;
        public string Mode { get; private set; }
        public string StreamId { get; private set; }
        public string RemoteName { get; private set; }
        public bool Control { get; private set; }
        public bool Native { get; private set; }
        public string Profile="Smooth · 30 fps target";
        public Func<byte[],string,Task> Frame;
        public Func<bool,Task<bool>> ReverseOffer;
        public Func<Task<bool>> ControlRequest;
        public Func<string,Task<int>> Approval;
        public string TransportName { get { return transport==null?"Encrypted relay":transport.Name; } }
        public Action<string> Changed;
        public Action<string> Ended;
        public Func<int,long,byte[]> CaptureFrame;
        public bool IsActive { get { return !finished && !stop.IsCancellationRequested; } }
        public ClientSession(IInput controller=null) { input=controller??new WindowsInput(); Mode="pending"; RemoteName="Remote computer"; CaptureFrame=Capture.Jpeg; }
        static Dictionary<string,object> Message(string type) { return new Dictionary<string,object> { {"type",type} }; }
        static string RandomHex(int length) { var data=new byte[length]; using(var rng=RandomNumberGenerator.Create()) rng.GetBytes(data); return BitConverter.ToString(data).Replace("-","").ToLowerInvariant(); }
        void Change(string text) { var callback=Changed; if(callback!=null) callback(text); }
        void Background(Func<Task> action) { Task.Run(action).ContinueWith(task=>{if(task.IsFaulted && IsActive)Finish("A background connection operation failed.");}); }
        public async Task Connect(Invitation invitation) {
            try {
                System.Net.ServicePointManager.SecurityProtocol=System.Net.SecurityProtocolType.Tls12;
                socket.Options.KeepAliveInterval=TimeSpan.FromSeconds(20);
                using(var timeout=CancellationTokenSource.CreateLinkedTokenSource(stop.Token)) { timeout.CancelAfter(15000); await socket.ConnectAsync(invitation.WebSocketUri,timeout.Token); }
                await SendPlain(new { type="connect", deviceId=invitation.DeviceId });
                await Receive(invitation.Key);
            } catch(OperationCanceledException) { Finish("Disconnected."); }
            catch(Exception) { Finish("Connection or authentication failed. Check the connection code and that the server is still sharing."); }
        }
        public void Attach(IPacketTransport wire,string key,string id,bool host) {
            hosting=host; sessionId=id; transport=wire;
            lock(cryptoGate) channel=new CryptoChannel(key,id,host);
            wire.Packet=ReceivePacket;
            wire.Ended=Finish;
            wire.Changed=message=>Change(message);
        }
        public Task Authenticate() { return Send(new {type="auth",name=Environment.MachineName,control=true,features=new[]{"native-switch-v1"}}); }
        async Task SendPlain(object value) { await SendBytes(Encoding.UTF8.GetBytes(Json.Encode(value)),WebSocketMessageType.Text); }
        async Task SendBytes(byte[] value,WebSocketMessageType type) {
            if(!IsActive) return;
            using(var timeout=CancellationTokenSource.CreateLinkedTokenSource(stop.Token)) {
                timeout.CancelAfter(5000); await sendGate.WaitAsync(timeout.Token);
                try { if(IsActive && socket.State==WebSocketState.Open) await socket.SendAsync(new ArraySegment<byte>(value),type,true,timeout.Token); }
                finally { sendGate.Release(); }
            }
        }
        public async Task Send(object value) {
            if(!IsActive) return;
            try {
                using(var timeout=CancellationTokenSource.CreateLinkedTokenSource(stop.Token)) {
                    timeout.CancelAfter(5000); await sendGate.WaitAsync(timeout.Token);
                    try {
                        byte[] packet;
                        lock(cryptoGate) { if(channel==null || !IsActive) return; packet=channel.Seal(1,Encoding.UTF8.GetBytes(Json.Encode(value))); }
                        if(transport!=null) await transport.Send(packet);
                        else if(socket.State==WebSocketState.Open) await socket.SendAsync(new ArraySegment<byte>(packet),WebSocketMessageType.Binary,true,timeout.Token);
                    } finally { sendGate.Release(); }
                }
            } catch { Finish("The connection closed."); }
        }
        async Task SendFrame(byte[] jpeg,int streamGeneration) {
            using(var timeout=CancellationTokenSource.CreateLinkedTokenSource(stop.Token)) {
                timeout.CancelAfter(5000); await sendGate.WaitAsync(timeout.Token);
                try {
                    byte[] packet;
                    lock(stateGate) {
                        if(!IsActive || Mode!="sharing" || streamGeneration!=generation) return;
                        lock(cryptoGate) packet=channel.Seal(2,jpeg);
                    }
                    if(transport!=null) await transport.Send(packet);
                    else await socket.SendAsync(new ArraySegment<byte>(packet),WebSocketMessageType.Binary,true,timeout.Token);
                } finally { sendGate.Release(); }
            }
        }
        async Task Receive(string key) {
            var buffer=new byte[32768];
            while(IsActive) {
                using(var body=new MemoryStream()) {
                    WebSocketReceiveResult result;
                    do {
                        result=await socket.ReceiveAsync(new ArraySegment<byte>(buffer),stop.Token);
                        if(result.MessageType==WebSocketMessageType.Close) { Finish("The other computer disconnected."); return; }
                        if(body.Length+result.Count>3*1024*1024) throw new InvalidDataException("Packet too large.");
                        body.Write(buffer,0,result.Count);
                    } while(!result.EndOfMessage);
                    byte[] data=body.ToArray();
                    if(result.MessageType==WebSocketMessageType.Text) {
                        if(data.Length>4096) throw new InvalidDataException();
                        var message=Json.Decode(Encoding.UTF8.GetString(data)); string type=Json.Text(message,"type");
                        if(type=="session") {
                            sessionId=Json.Text(message,"sessionId"); if(!Regex.IsMatch(sessionId,@"^[a-f0-9]{32}$")) throw new InvalidDataException();
                            lock(cryptoGate) channel=new CryptoChannel(key,sessionId);
                            await Send(new {type="auth",name=Environment.MachineName,control=true,features=new[]{"native-switch-v1"}});
                        } else if(type=="error" || type=="session-ended") { Finish(Json.Text(message,"message",Json.Text(message,"reason","Session ended."))); return; }
                    } else {
                        await ReceivePacket(data);
                    }
                }
            }
        }
        async Task ReceivePacket(byte[] data) {
            if(!IsActive) return;
            byte[] plain; lock(cryptoGate) { if(channel==null) throw new InvalidDataException(); plain=channel.Open(data); }
            if(plain[0]==2) {
                string id=StreamId;
                if(Mode=="viewing" && Frame!=null) { await Frame(plain.Skip(1).ToArray(),id); if(Mode=="viewing" && id==StreamId) await Send(new {type="ack",streamId=id}); }
            } else if(plain[0]==1 && plain.Length<=8193) await Command(Json.Decode(Encoding.UTF8.GetString(plain,1,plain.Length-1)));
            else throw new InvalidDataException("Invalid session command.");
        }
        async Task Command(Dictionary<string,object> message) {
            string type=Json.Text(message,"type");
            if(type=="auth" && hosting && Mode=="pending" && !approvalWaiting) {
                approvalWaiting=true;
                RemoteName=new string(Json.Text(message,"name","Remote computer").Where(c=>!char.IsControl(c)).Take(80).ToArray());if(RemoteName=="")RemoteName="Remote computer"; Native=Json.Feature(message,"native-switch-v1");
                HandleApproval(); return;
            }
            if(type=="approved" && Mode=="pending") {
                Mode="viewing"; Control=Json.Flag(message,"control"); Native=Json.Feature(message,"native-switch-v1"); RemoteName=Json.Text(message,"name","Remote computer");
                if(transport!=null) Background(()=>transport.Ready(true));
                if(Native) await Send(new {type="quality",profile=Profile}); Change("Viewing "+RemoteName); return;
            }
            if(type=="denied" || type=="error") { Finish("The other computer declined the connection."); return; }
            if(Mode=="pending") throw new InvalidDataException("Approval is required.");
            if(type=="stream" && Mode=="viewing") { string id=Json.Text(message,"streamId"); if(!Regex.IsMatch(id,@"^[a-f0-9]{16}$")) throw new InvalidDataException(); StreamId=id; }
            else if(type=="control" && Mode=="viewing") { Control=Json.Flag(message,"enabled"); Change(Control?"Remote control enabled.":"View-only mode."); }
            else if(type=="quality") { string profile=Json.Text(message,"profile"); if(IsProfile(profile)) Profile=profile; }
            else if(type=="ack" && Mode=="sharing") {
                lock(stateGate) if(Json.Text(message,"streamId")==StreamId && pending.Count>0) pendingBytes-=pending.Dequeue().Item2;
            } else if(new[]{"move","key","button","wheel","release"}.Contains(type) && Mode=="sharing" && Control) {
                lock(stateGate) {
                    if(Mode=="sharing" && Control) {
                        try { input.Apply(message); } catch(InvalidOperationException) { Control=false; input.Release(); }
                    }
                }
                if(!Control) { await Send(new {type="control",enabled=false}); Change("Windows blocked input; sharing is view only."); }
            } else if(type=="request-control" && Mode=="sharing" && !Control && ControlRequest!=null) {
                HandleControlRequest();
            } else if(type=="reverse-accepted" && Mode=="viewing") {
                if(reverseOut==null || Json.Text(message,"requestId")!=reverseOut) throw new InvalidDataException("No local approval for sharing.");
                reverseOut=null; await StartSharing(reverseControl);
            } else if(type=="reverse-denied" && Json.Text(message,"requestId")==reverseOut) { reverseOut=null; Change("Direction switch declined."); }
            else if(type=="reverse-request" && Native && Mode=="sharing") {
                string request=Json.Text(message,"requestId");
                if(reverseIn!=null || !Regex.IsMatch(request,@"^[a-f0-9]{32}$")) throw new InvalidDataException();
                reverseIn=request;
                bool granted=Json.Flag(message,"control");
                HandleReverseOffer(request,granted);
            }
        }
        async void HandleApproval() {
            try {
                int choice=Approval==null?-1:await Approval(RemoteName);
                if(!IsActive || Mode!="pending") return;
                if(choice<0) { await Send(new {type="denied"}); Finish("Connection declined locally."); return; }
                Mode="starting";
                Task connection=transport==null?Task.FromResult(false):transport.Ready(false);
                await Send(new {type="approved",name=Environment.MachineName,control=choice==1,features=new[]{"native-switch-v1"}});
                await connection;
                if(IsActive) await StartSharing(choice==1);
            } catch { Finish("The sharing request could not be completed."); }
        }
        async void HandleControlRequest() {
            try { if(await ControlRequest() && IsActive && Mode=="sharing") await SetControl(true); }
            catch { if(IsActive) Finish("The control request could not be completed."); }
        }
        async void HandleReverseOffer(string request,bool granted) {
            try {
                bool accept=ReverseOffer!=null && await ReverseOffer(granted);
                reverseIn=null;
                if(!IsActive) return;
                if(!accept || Mode!="sharing") { await Send(new {type="reverse-denied",requestId=request}); return; }
                lock(stateGate) { generation++; pending.Clear(); pendingBytes=0; input.Release(); Mode="viewing"; Control=granted; StreamId=null; }
                await Send(new {type="reverse-accepted",requestId=request}); Change("Viewing "+RemoteName);
            } catch { if(IsActive) Finish("The direction request could not be completed."); }
        }
        public static bool IsProfile(string profile) { return new[]{"Economy · 5 fps","Balanced · 10 fps","Sharper · 15 fps","Smooth · 30 fps target","Fast · 60 fps target"}.Contains(profile); }
        public async Task Input(object value) { if(Mode=="viewing" && Control) await Send(value); }
        public async Task SetControl(bool enabled) { lock(stateGate) { if(Mode!="sharing") return; Control=enabled; if(!enabled) input.Release(); } await Send(new {type="control",enabled=enabled}); Change(enabled?"Sharing with remote control.":"Sharing in view-only mode."); }
        public async Task Reverse(bool allowControl) {
            if(!Native || Mode!="viewing" || reverseOut!=null) return;
            string request=RandomHex(16); reverseOut=request; reverseControl=allowControl;
            await Input(new {type="release"}); await Send(new {type="reverse-request",requestId=request,control=allowControl}); Change("Waiting for direction switch approval…");
            Background(async delegate { await Task.Delay(30000); if(reverseOut==request) { reverseOut=null; Change("Direction switch timed out. Your screen was not shared."); } });
        }
        async Task StartSharing(bool control) {
            int streamGeneration;
            lock(stateGate) { Mode="sharing"; Control=control; StreamId=RandomHex(8); generation++; streamGeneration=generation; pending.Clear(); pendingBytes=0; }
            await Send(new {type="stream",streamId=StreamId}); Change(control?"Sharing your screen — REMOTE CONTROL":"Sharing your screen — VIEW ONLY");
            Background(()=>CaptureLoop(streamGeneration));
        }
        async Task CaptureLoop(int streamGeneration) {
            try {
                while(IsActive && Mode=="sharing" && generation==streamGeneration) {
                    int fps,width,quality; ProfileValues(out fps,out width,out quality);
                    int window=fps<=15?1:fps<=30?4:8;
                    bool ready;
                    lock(stateGate) { if(pending.Count>0 && (DateTime.UtcNow-pending.Peek().Item1).TotalSeconds>10) throw new TimeoutException(); ready=pending.Count<window && pendingBytes<2*1024*1024; }
                    if(!ready) { await Task.Delay(5); continue; }
                    var start=DateTime.UtcNow; byte[] frame=CaptureFrame(width,quality);
                    while(IsActive && Mode=="sharing" && generation==streamGeneration) {
                        lock(stateGate) { if(pending.Count>0 && (DateTime.UtcNow-pending.Peek().Item1).TotalSeconds>10) throw new TimeoutException(); ready=pending.Count==0 || pendingBytes+frame.Length<=2*1024*1024; }
                        if(ready) break;
                        await Task.Delay(5);
                    }
                    lock(stateGate) { if(Mode!="sharing" || generation!=streamGeneration) break; pending.Enqueue(Tuple.Create(DateTime.UtcNow,frame.Length)); pendingBytes+=frame.Length; }
                    await SendFrame(frame,streamGeneration);
                    int delay=(int)Math.Max(0,1000.0/fps-(DateTime.UtcNow-start).TotalMilliseconds); if(delay>0) await Task.Delay(delay);
                }
            } catch { if(IsActive && Mode=="sharing" && generation==streamGeneration) Finish("Screen sharing stopped. Check the connection and unlocked Windows desktop."); }
        }
        void ProfileValues(out int fps,out int width,out int quality) {
            fps=30; width=1600; quality=60;
            if(Profile.StartsWith("Economy")) {fps=5;width=1280;quality=50;}
            else if(Profile.StartsWith("Balanced")) {fps=10;quality=65;}
            else if(Profile.StartsWith("Sharper")) {fps=15;width=1920;quality=78;}
            else if(Profile.StartsWith("Fast")) {fps=60;width=960;quality=50;}
        }
        public void Finish(string message) {
            lock(stateGate) { if(finished) return; finished=true; Mode="ended"; generation++; Control=false; input.Release(); pending.Clear(); pendingBytes=0; }
            stop.Cancel(); socket.Abort(); if(transport!=null)transport.Dispose(); var callback=Ended; if(callback!=null) callback(message);
        }
        public void Dispose() { Finish("Disconnected."); lock(cryptoGate) { if(channel!=null) {channel.Dispose();channel=null;} } socket.Dispose(); }
    }
}

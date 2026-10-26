using System;
using System.IO;
using System.Linq;
using System.Net.WebSockets;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace CampusLink.Client {
    public sealed class BrokerNetwork : IPeerNetwork {
        ClientWebSocket socket;
        CancellationTokenSource cancel;
        readonly SemaphoreSlim sending=new SemaphoreSlim(1,1),joining=new SemaphoreSlim(1,1);
        TaskCompletionSource<bool> registered;
        TaskCompletionSource<ClientSession> connecting;
        PeerCode profile,target;
        HybridTransport active;
        string key=PeerCode.Random(16);
        public bool ForceRelay;
        public string TestIdentity;
        public string[] StunServers={"stun:stun.cloudflare.com:3478","stun:stun.l.google.com:19302"};
        public Func<ClientSession> SessionFactory;
        public Action<string> Diagnostic;
        public void PreferRelay(){var wire=active;if(wire!=null)wire.UseRelay();}
#if CAMPUSLINK_TESTS
        public void InterruptDirect(){var wire=active;if(wire!=null)wire.InterruptDirect();}
#endif
        public Action<string> Status {get;set;}
        public Action<ClientSession> Incoming {get;set;}
        public string DeviceId {get;private set;}
        public string Invitation {get{return profile==null||DeviceId==null?"":new PeerCode{Url=profile.Url,Token=profile.Token,DeviceId=DeviceId,Key=key}.Encode();}}
        public string SavedProfile {get{return PeerSettings.Load("server.profile");}}
        void Update(string text){var callback=Status;if(callback!=null)callback(text);}
        public async Task Join(string code) {
            var next=PeerCode.Parse(code);
            await joining.WaitAsync();
            try {
                if(profile!=null && profile.Url==next.Url && profile.Token==next.Token && DeviceId!=null && socket.State==WebSocketState.Open)return;
                if(active!=null)throw new InvalidOperationException("Disconnect the current session before changing server.");
                if(socket!=null){cancel.Cancel();socket.Abort();socket.Dispose();}
                profile=new PeerCode{Url=next.Url,Token=next.Token};DeviceId=null;
                registered=new TaskCompletionSource<bool>();cancel=new CancellationTokenSource();socket=new ClientWebSocket();socket.Options.KeepAliveInterval=TimeSpan.FromSeconds(20);
                System.Net.ServicePointManager.SecurityProtocol=System.Net.SecurityProtocolType.Tls12;
                Update("Joining server…");
                using(var timeout=CancellationTokenSource.CreateLinkedTokenSource(cancel.Token)){timeout.CancelAfter(15000);await socket.ConnectAsync(profile.WebSocketUri,timeout.Token);}
                Receive(socket,cancel.Token);
                await Control(new{type="join",token=profile.Token,identity=TestIdentity??PeerSettings.Identity(profile.Token)});
                if(await Task.WhenAny(registered.Task,Task.Delay(15000))!=registered.Task)throw new TimeoutException("Server registration timed out.");
                await registered.Task;
                if(TestIdentity==null)PeerSettings.Save("server.profile",profile.Encode());
            } finally{joining.Release();}
        }
        public async Task<ClientSession> Connect(string code) {
            var invitation=PeerCode.Parse(code);
            if(invitation.DeviceId=="")throw new ArgumentException("Use the other computer's code to connect; use Join server for a server code.");
            await Join(code);
            if(active!=null || connecting!=null)throw new InvalidOperationException("A session is already active.");
            target=invitation;connecting=new TaskCompletionSource<ClientSession>();var completion=connecting;
            try {
                await Control(new{type="connect",deviceId=target.DeviceId});
                if(await Task.WhenAny(completion.Task,Task.Delay(15000))!=completion.Task)throw new TimeoutException("Connection request timed out.");
                return await completion.Task;
            }finally{connecting=null;target=null;}
        }
        public async Task Control(object value) {await Bytes(Encoding.UTF8.GetBytes(Json.Encode(value)),false);}
        async Task Bytes(byte[] bytes,bool binary) {
            using(var timeout=CancellationTokenSource.CreateLinkedTokenSource(cancel.Token)) {
                timeout.CancelAfter(5000);await sending.WaitAsync(timeout.Token);
                try{await socket.SendAsync(new ArraySegment<byte>(bytes),binary?WebSocketMessageType.Binary:WebSocketMessageType.Text,true,timeout.Token);}finally{sending.Release();}
            }
        }
        public Task Relay(string id,byte[] bytes) {return Bytes(Hex(id).Concat(bytes).ToArray(),true);}
        public static byte[] Hex(string text){return Enumerable.Range(0,text.Length/2).Select(i=>Convert.ToByte(text.Substring(2*i,2),16)).ToArray();}
        public void Release(HybridTransport wire) {if(active!=wire)return;active=null;Task.Run(async delegate{try{await Control(new{type="end",sessionId=wire.Id});}catch{}});Update("Online · Your ID: "+DeviceId);}
        async void Receive(ClientWebSocket current,CancellationToken stopped) {
            try {
                var buffer=new byte[32768];
                while(!stopped.IsCancellationRequested)using(var body=new MemoryStream()) {
                    WebSocketReceiveResult result;
                    do{result=await current.ReceiveAsync(new ArraySegment<byte>(buffer),stopped);if(result.MessageType==WebSocketMessageType.Close)throw new IOException("Server disconnected: "+result.CloseStatus+" "+result.CloseStatusDescription);if(body.Length+result.Count>3*1024*1024+64)throw new IOException("Packet too large.");body.Write(buffer,0,result.Count);}while(!result.EndOfMessage);
                    byte[] data=body.ToArray();
                    if(result.MessageType==WebSocketMessageType.Binary){var wire=active;if(wire!=null && data.Length>=16 && data.Take(16).SequenceEqual(Hex(wire.Id)))wire.Enqueue(data.Skip(16).ToArray());continue;}
                    if(data.Length>65536)throw new IOException("Signal too large.");
                    var msg=Json.Decode(Encoding.UTF8.GetString(data));string type=Json.Text(msg,"type");
                    if(type=="registered") {string id=Json.Text(msg,"deviceId");if(!Regex.IsMatch(id,@"^\d{10}$"))throw new IOException();DeviceId=id;registered.TrySetResult(true);Update("Online · Your ID: "+id);}
                    else if(type=="unavailable"){if(connecting!=null)connecting.TrySetException(new IOException(Json.Text(msg,"message")));}
                    else if(type=="session") {
                        string id=Json.Text(msg,"sessionId");bool host=Json.Text(msg,"role")=="host";
                        if(active!=null||!Regex.IsMatch(id,@"^[a-f0-9]{32}$")||(!host && (target==null||connecting==null)))throw new IOException("Unexpected session.");
                        var wire=new HybridTransport(this,id,host?key:target.Key,host,ForceRelay);active=wire;
                        var peer=SessionFactory==null?new ClientSession():SessionFactory();peer.Attach(wire,host?key:target.Key,id,host);
                        if(host){var callback=Incoming;if(callback!=null)callback(peer);else peer.Finish("No local approval handler.");}
                        else connecting.TrySetResult(peer);
                    } else {
                        var wire=active;if(wire==null || Json.Text(msg,"sessionId")!=wire.Id)continue;
                        if(type=="signal")wire.Signal(Json.Text(msg,"payload"));
                        else if(type=="ack")wire.Acknowledge(Convert.ToInt64(msg["n"]));
                        else if(type=="fallback")wire.UseRelay();
                        else if(type=="ended")wire.Fail(Json.Text(msg,"reason","Session ended."));
                    }
                }
            } catch(Exception error) {
                if(stopped.IsCancellationRequested)return;
                var diagnostic=Diagnostic;if(diagnostic!=null)diagnostic("broker: "+error.ToString());
                registered.TrySetException(new IOException("Unable to register with the server."));if(connecting!=null)connecting.TrySetException(new IOException("Server disconnected."));
                var wire=active;if(wire!=null)wire.Fail("Server disconnected. Rejoin the server to continue.");DeviceId=null;Update("Offline. Rejoin the server to continue.");
            }
        }
        public void Dispose(){var wire=active;if(wire!=null)wire.Fail("Disconnected.");if(cancel!=null)cancel.Cancel();if(socket!=null){socket.Abort();socket.Dispose();}}
    }
}

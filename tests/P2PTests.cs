using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

namespace CampusLink.Client {
    static class P2PTests {
        sealed class NoInput : IInput {
            public int Applied;
            public void Apply(Dictionary<string,object> value){Interlocked.Increment(ref Applied);}
            public void Release(){}
        }
        static string folder;
        static List<string> diagnostics=new List<string>();
        static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
        static async Task Until(Func<bool> check,string message,int timeout=20000){DateTime end=DateTime.UtcNow.AddMilliseconds(timeout);while(!check()){if(DateTime.UtcNow>end)throw new Exception(message);await Task.Delay(20);}}
        static void Progress(string phase,object values){File.WriteAllText(Path.Combine(folder,"progress.json"),Json.Encode(new{phase=phase,values=values}));}
        static BrokerNetwork Make(bool relay=false) {var network=new BrokerNetwork{ForceRelay=relay,TestIdentity=PeerCode.Random(32),SessionFactory=()=>new ClientSession(new NoInput())};if(Environment.GetEnvironmentVariable("CAMPUSLINK_TEST_PUBLIC_TUNNEL")!="1")network.StunServers=new string[0];network.Diagnostic=message=>{lock(diagnostics)diagnostics.Add(message);};return network;}
        static byte[] Jpeg(){using(var bitmap=new Bitmap(960,540,PixelFormat.Format24bppRgb))using(var memory=new MemoryStream()){var area=bitmap.LockBits(new Rectangle(0,0,960,540),ImageLockMode.WriteOnly,PixelFormat.Format24bppRgb);var noise=new byte[area.Stride*540];new Random(1234).NextBytes(noise);Marshal.Copy(noise,0,area.Scan0,noise.Length);bitmap.UnlockBits(area);bitmap.Save(memory,ImageFormat.Jpeg);var bytes=memory.ToArray();Check(bytes.Length>16000,"Fragmentation fixture too small.");return bytes;}}
        [STAThread]static int Main(string[] args){EmbeddedLibraries.Install();try{return Run(args).GetAwaiter().GetResult();}catch(Exception error){File.WriteAllText(Path.Combine(args[1],"report.json"),Json.Encode(new{status="failed",error=error.ToString(),diagnostics=diagnostics.ToArray()}));return 1;}}
        [MethodImpl(MethodImplOptions.NoInlining)]static async Task<int> Run(string[] args) {
            folder=args[1];string code=File.ReadAllText(args[0]);byte[] jpeg=Jpeg();
            using(var host=Make())using(var viewer=Make())using(var otherHost=Make(true))using(var otherViewer=Make()) {
                await host.Join(code);await viewer.Join(code);await otherHost.Join(code);await otherViewer.Join(code);
                Check(new[]{host.DeviceId,viewer.DeviceId,otherHost.DeviceId,otherViewer.DeviceId}.Distinct().Count()==4,"Unique server-issued IDs required.");
                ClientSession sharing=null,otherSharing=null;var approval=new TaskCompletionSource<int>();int captures=0,frames=0,otherFrames=0;bool asked=false;NoInput hostInput=null;
                host.SessionFactory=()=>{hostInput=new NoInput();return new ClientSession(hostInput);};
                host.Incoming=peer=>{sharing=peer;peer.Profile="Economy · 5 fps";peer.Approval=name=>{asked=true;return approval.Task;};peer.CaptureFrame=(w,q)=>{Interlocked.Increment(ref captures);return jpeg;};peer.ControlRequest=()=>Task.FromResult(true);peer.ReverseOffer=control=>Task.FromResult(true);peer.Frame=(data,id)=>Task.FromResult(0);};
                otherHost.Incoming=peer=>{otherSharing=peer;peer.Approval=name=>Task.FromResult(0);peer.CaptureFrame=(w,q)=>jpeg;};
                var viewing=await viewer.Connect(host.Invitation);viewing.Profile="Economy · 5 fps";viewing.Frame=(data,id)=>{Check(data.SequenceEqual(jpeg),"Frame integrity.");Interlocked.Increment(ref frames);return Task.FromResult(0);};viewing.CaptureFrame=(w,q)=>jpeg;viewing.ReverseOffer=control=>Task.FromResult(true);
                await viewing.Authenticate();await Until(()=>asked,"Local approval prompt missing.");await Task.Delay(400);Check(captures==0,"Capture started before local approval.");approval.SetResult(0);
                await Until(()=>frames>=3,"Direct P2P frames did not arrive.");
                Check(viewing.TransportName.StartsWith("Direct")&&sharing.TransportName.StartsWith("Direct"),"Expected direct WebRTC, got "+viewing.TransportName+" / "+sharing.TransportName+"; "+string.Join(" | ",diagnostics));
                int directStart=frames;Progress("direct-active",new{frames=frames,captures=captures,transport=viewing.TransportName});
                await Task.Delay(2500);await Until(()=>frames>=directStart+2,"Direct stream did not continue.");
                // A second pair runs simultaneously, with one endpoint forcing relay.
                var otherViewing=await otherViewer.Connect(otherHost.Invitation);otherViewing.Profile="Economy · 5 fps";otherViewing.Frame=(data,id)=>{Check(data.SequenceEqual(jpeg),"Relay frame integrity.");Interlocked.Increment(ref otherFrames);return Task.FromResult(0);};
                await otherViewing.Authenticate();await Until(()=>otherFrames>=3,"Forced fallback frames missing.");
                Progress("two-pairs",new{frames=frames,relayFrames=otherFrames});
                Check(otherViewing.TransportName=="Encrypted relay"&&otherSharing.TransportName=="Encrypted relay","Fallback indicator incorrect.");
                int before=frames;await viewing.Send(new{type="key",code="KeyB",down=true});await Task.Delay(200);Check(hostInput.Applied==0,"View-only host accepted input.");
                await viewing.Send(new{type="request-control"});await Until(()=>viewing.Control,"Control grant missing.");await viewing.Input(new{type="key",code="KeyA",down=true});await Until(()=>hostInput.Applied==1,"Approved input did not arrive.");await sharing.SetControl(false);await Until(()=>!viewing.Control,"Control revocation missing.");
                viewer.InterruptDirect();await Until(()=>viewing.TransportName=="Encrypted relay"&&sharing.TransportName=="Encrypted relay"&&frames>=before+3,"Mid-session fallback did not continue.");
                Progress("recovered",new{frames=frames});
                await viewing.Reverse(false);await Until(()=>viewing.Mode=="sharing"&&sharing.Mode=="viewing","Approved direction switch failed.");
                await sharing.Reverse(false);await Until(()=>viewing.Mode=="viewing"&&sharing.Mode=="sharing","Return direction switch failed.");
                Progress("switched-back",new{frames=frames});
                viewing.Finish("Test complete");otherViewing.Finish("Test complete");
                await Until(()=>!sharing.IsActive&&!otherSharing.IsActive,"Disconnect did not stop sharing.");
                await Task.Delay(2200);
                string wrong=host.Invitation;var bad=PeerCode.Parse(wrong);bad.Key=PeerCode.Random(16);asked=false;captures=0;
                var rejected=await viewer.Connect(bad.Encode());await rejected.Authenticate();await Until(()=>!rejected.IsActive,"Wrong-key connection was not rejected.");Check(!asked&&captures==0,"Wrong-key connection reached approval/capture.");
                File.WriteAllText(Path.Combine(folder,"report.json"),Json.Encode(new{status="ok",uniqueDevices=4,directFrames=frames,relayFrames=otherFrames,approvalRequired=true,multiplePairs=true,midSessionFallback=true,directionSwitch=true,wrongKeyRejected=true,diagnostics=diagnostics.ToArray()}));
                return 0;
            }
        }
    }
}

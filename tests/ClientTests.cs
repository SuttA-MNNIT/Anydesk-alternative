using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;

namespace CampusLink.Client {
    public static class ClientTests {
        sealed class FakeInput : IInput { public int Calls; public void Apply(Dictionary<string,object> value) {Calls++;} public void Release(){} }
        static void Require(bool value,string message) {if(!value)throw new Exception(message);}
        static bool Reject(Action action) {try{action();return false;}catch(CryptographicException){return true;}}
        static void Crypto(string input,string output) {
            var values=Json.Decode(File.ReadAllText(input));
            string secret=Json.Text(values,"secret"),sid=Json.Text(values,"sessionId");
            byte[] packet=Convert.FromBase64String(Json.Text(values,"hostPacket"));
            using(var client=new CryptoChannel(secret,sid)) {
                byte[] damaged=(byte[])packet.Clone();damaged[damaged.Length-1]^=1;
                bool tamper=Reject(()=>client.Open(damaged));
                byte[] opened=client.Open(packet);
                bool replay=Reject(()=>client.Open(packet));
                byte[] reply=client.Seal(1,System.Text.Encoding.UTF8.GetBytes("{\"type\":\"auth\",\"name\":\"CSharp QA\",\"control\":false}"));
                bool reflection=Reject(()=>client.Open(reply));
                bool wrong;
                using(var other=new CryptoChannel(new string('f',32),sid))wrong=Reject(()=>other.Open(packet));
                Require(tamper&&replay&&reflection&&wrong,"Cryptographic rejection failed.");
                Require(WindowsInput.Size==40,"Native Windows input ABI mismatch.");
                bool invalidInvite=false;try{Invitation.Parse("CL3.bad");}catch{invalidInvite=true;}
                Require(invalidInvite,"Malformed invitation was accepted.");
                File.WriteAllText(output,Json.Encode(new {status="ok",tamperRejected=tamper,replayRejected=replay,reflectionRejected=reflection,wrongKeyRejected=wrong,
                    inputSize=WindowsInput.Size,hostPlaintext=System.Text.Encoding.UTF8.GetString(opened,1,opened.Length-1),reply=Convert.ToBase64String(reply)}));
            }
        }
        static async Task Network(string fixture,string output) {
            var config=Json.Decode(File.ReadAllText(fixture));
            var input=new FakeInput();using(var session=new ClientSession(input)) {
                var done=new TaskCompletionSource<bool>();int phase=0;int captures=0,frames=0;bool reverse=false;string initialStream=null;
                session.CaptureFrame=(width,quality)=>{Interlocked.Increment(ref captures);return File.ReadAllBytes(Json.Text(config,"syntheticJpeg"));};
                session.ReverseOffer=control=>Task.FromResult(true);
                session.ControlRequest=()=>Task.FromResult(false);
                session.Frame=async delegate(byte[] jpeg,string stream) {
                    using(var memory=new MemoryStream(jpeg))using(var image=Image.FromStream(memory))Require(image.Width>0,"Invalid JPEG.");
                    frames++;
                    if(phase==0){Require(!session.Control,"Expected initial view-only approval.");initialStream=stream;phase=1;await session.Send(new {type="request-control"});}
                    else if(phase==3 && reverse && stream!=initialStream){phase=4;done.TrySetResult(true);}
                };
                session.Changed=delegate(string message) {
                    if(phase==1 && session.Mode=="viewing" && session.Control){phase=2;Task.Run(async delegate{await session.Input(new {type="key",code="KeyA",down=true});await session.Input(new {type="key",code="KeyA",down=false});});}
                    else if(phase==2 && session.Mode=="viewing" && !session.Control){phase=3;Task.Run(()=>session.Reverse(false));}
                    else if(phase==3 && session.Mode=="sharing")reverse=true;
                };
                session.Ended=message=>{if(phase!=4)done.TrySetException(new Exception(message));};
                Task network=session.Connect(Invitation.Parse(Json.Text(config,"code")));
                Task winner=await Task.WhenAny(done.Task,Task.Delay(25000));
                if(winner!=done.Task)throw new TimeoutException("Native C# protocol test timed out at phase "+phase+"; native="+session.Native+"; mode="+session.Mode+"; frames="+frames+"; captures="+captures);
                await done.Task;
                Require(captures>0 && reverse && input.Calls==0,"Direction switch or view-only gating failed.");
                File.WriteAllText(output,Json.Encode(new {status="ok",nativeFrames=frames,syntheticReverseFrames=captures,reversedBothWays=true,remoteInputInjected=false,viewOnlyInputBlocked=true}));
                session.Finish("Test finished.");await network;
            }
        }
        [STAThread] public static int Main(string[] args) {
            try {if(args[0]=="crypto")Crypto(args[1],args[2]);else Network(args[1],args[2]).GetAwaiter().GetResult();return 0;}
            catch(Exception error){File.WriteAllText(args[2],Json.Encode(new {status="failed",error=error.ToString()}));return 1;}
        }
    }
}

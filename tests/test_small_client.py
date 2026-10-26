"""Cross-runtime CNG interoperability and native client/server tests. Never inject Windows input."""
import base64
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import unittest
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'host'))
from protocol import Channel
from desktop.invitation import Invitation
from desktop.peer import NativePeer
from desktop.runtime import ManagedRuntime
from tests.test_desktop import wait_event,RecordedController
from PIL import Image


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ROOT/'artifacts/small-client-tests';cls.folder.mkdir(parents=True,exist_ok=True)
        cls.exe=cls.folder/'ClientTests.exe'
        compiler=Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
        command=[str(compiler),'/nologo','/codepage:65001','/target:exe','/platform:x64','/optimize+','/main:CampusLink.Client.ClientTests','/out:'+str(cls.exe)]
        command += ['/reference:'+name for name in ('System.dll','System.Core.dll','System.Drawing.dll','System.Windows.Forms.dll','System.Web.Extensions.dll')]
        command += [str(p) for p in (ROOT/'client').glob('*.cs')]+[str(ROOT/'tests/ClientTests.cs')]
        subprocess.run(command,check=True,capture_output=True,text=True)

    def test_windows_cng_python_crypto_and_rejection(self):
        secret='0123456789abcdef0123456789abcdef';sid='a'*32
        host=Channel(secret,sid)
        fixture=self.folder/'crypto-input.json';report=self.folder/'crypto-output.json'
        fixture.write_text(json.dumps({'secret':secret,'sessionId':sid,'hostPacket':base64.b64encode(host.seal(1,b'{"type":"approved","control":false}')).decode()}))
        result=subprocess.run([str(self.exe),'crypto',str(fixture),str(report)],capture_output=True,text=True,timeout=30)
        data=json.loads(report.read_text());self.assertEqual(result.returncode,0,data)
        self.assertEqual(data['status'],'ok');self.assertTrue(data['tamperRejected'] and data['replayRejected'] and data['reflectionRejected'] and data['wrongKeyRejected'])
        kind,plain=host.open(base64.b64decode(data['reply']));self.assertEqual(kind,1);self.assertEqual(json.loads(plain)['type'],'auth')

    def test_small_client_frames_control_and_reverse_with_existing_server(self):
        events=queue.Queue();runtime=ManagedRuntime(events);peer=None;process=None
        try:
            public=os.environ.get('CAMPUSLINK_TEST_PUBLIC_TUNNEL')=='1'
            threading.Thread(target=runtime.start,kwargs={'tunnel':public},daemon=True).start();wait_event(events,'runtime-ready',95 if public else 20)
            jpg=self.folder/'synthetic.jpg';Image.effect_noise((960,540),55).convert('RGB').save(jpg,quality=65)
            class Capture:
                backend='synthetic test image'
                def grab(self,**kwargs):return Image.open(jpg).convert('RGB')
                def close(self):pass
            hq=queue.Queue();controller=RecordedController();key='b'*32
            peer=NativePeer(hq,'host','6655443322',key,'Server QA',controller,Capture)
            peer.connect('http://127.0.0.1:'+str(runtime.port),runtime.token);wait_event(hq,'online')
            fixture=self.folder/'network-input.json';report=self.folder/'network-output.json'
            fixture.write_text(json.dumps({'code':Invitation(runtime.url,'6655443322',key).encode(),'syntheticJpeg':str(jpg)}))
            process=subprocess.Popen([str(self.exe),'network',str(fixture),str(report)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            deadline=time.monotonic()+30;revoked=False;reverse_back=False
            while process.poll() is None and time.monotonic()<deadline:
                try:
                    category,value=hq.get(timeout=.02)
                    if category!='peer':continue
                    owner,kind,data=value
                    if kind=='approval':peer.approve(data[0],True,False)
                    elif kind=='control-request':peer.set_control(True)
                    elif kind=='reverse-offer':peer.accept_reverse(*data[:2],True,data[2])
                    elif kind=='frame':
                        peer.ack(data[0],data[1])
                        if not reverse_back:
                            # Bypass the sender's local guard to verify the C# receiver
                            # rejects encrypted input while its reverse stream is view only.
                            peer.secure({'type':'key','code':'KeyB','down':True})
                            reverse_back=True;peer.reverse(True)
                except queue.Empty:pass
                if not revoked and any(e.get('code')=='KeyA' and e.get('down') is False for e in controller.events):peer.set_control(False);revoked=True
            if process.poll() is None:process.kill();self.fail('C# network test timed out')
            data=json.loads(report.read_text());self.assertEqual(process.returncode,0,data)
            self.assertTrue(data['reversedBothWays']);self.assertTrue(data['viewOnlyInputBlocked']);self.assertTrue(reverse_back and revoked)
        finally:
            if process:
                if process.poll() is None:process.kill()
                process.communicate(timeout=3)
            if peer:peer.stop(wait=True)
            runtime.stop()


if __name__=='__main__':unittest.main()

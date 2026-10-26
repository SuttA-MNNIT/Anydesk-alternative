"""Real loopback UDP/DTLS/SCTP and encrypted WSS fallback; no screen/input access."""
import base64,json,os,secrets,subprocess,time,unittest,queue,threading,re
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
class PeerTests(unittest.TestCase):
    def test_direct_relay_multiple_pairs_and_attended_approval(self):
        folder=ROOT/('artifacts/p2p-public-tests' if os.environ.get('CAMPUSLINK_TEST_PUBLIC_TUNNEL')=='1' else 'artifacts/p2p-tests');folder.mkdir(exist_ok=True,parents=True)
        exe=folder/'P2PTests.exe'
        built=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/build-p2p-client.ps1'),'-TestSource',str(ROOT/'tests/P2PTests.cs'),'-Output',str(exe),'-Main','CampusLink.Client.P2PTests'],capture_output=True,text=True)
        self.assertEqual(built.returncode,0,built.stdout+built.stderr)
        token=secrets.token_hex(32);metrics=folder/'metrics.json'
        fixture=subprocess.Popen(['node','tests/p2p-fixture.mjs'],cwd=ROOT,env=dict(os.environ,CAMPUSLINK_TEST_TOKEN=token,CAMPUSLINK_TEST_METRICS=str(metrics)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        client=None;cloud=None
        try:
            port=json.loads(fixture.stdout.readline())['port']
            url=f'http://127.0.0.1:{port}'
            if os.environ.get('CAMPUSLINK_TEST_PUBLIC_TUNNEL')=='1':
                cloud=subprocess.Popen([str(ROOT/'tools/cloudflared.exe'),'tunnel','--protocol','http2','--url',url,'--no-autoupdate'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                lines=queue.Queue()
                def read():
                    for line in cloud.stdout:lines.put(line)
                threading.Thread(target=read,daemon=True).start();deadline=time.monotonic()+90;route=None;connected=False
                while time.monotonic()<deadline:
                    try:line=lines.get(timeout=.2)
                    except queue.Empty:continue
                    match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',line)
                    if match:route=match[0]
                    if 'Registered tunnel connection' in line:connected=True
                    if route and connected:url=route;break
                else:self.fail('Public test tunnel did not start.')
                deadline=time.monotonic()+45
                while time.monotonic()<deadline:
                    try:
                        with urllib.request.urlopen(url+'/healthz',timeout=5) as response:
                            if json.load(response).get('status')=='ok':break
                    except (OSError,ValueError):pass
                    time.sleep(2)
                else:self.fail('Public DNS/HTTPS did not become reachable.')
            code='CL4.'+base64.urlsafe_b64encode(json.dumps({'u':url,'t':token}).encode()).decode().rstrip('=')
            (folder/'code.txt').write_text(code)
            for name in ('progress.json','report.json'):(folder/name).unlink(missing_ok=True)
            client=subprocess.Popen([str(exe),str(folder/'code.txt'),str(folder)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            deadline=time.monotonic()+80;direct_checked=False
            while client.poll() is None and time.monotonic()<deadline:
                if not direct_checked and (folder/'progress.json').exists():
                    before=json.loads(metrics.read_text())['bytesForwarded'];time.sleep(1)
                    after=json.loads(metrics.read_text())['bytesForwarded'];self.assertEqual(before,after,'Server relayed payload bytes during the direct-only stream.');direct_checked=True
                time.sleep(.05)
            if client.poll() is None:client.kill();self.fail('P2P harness timed out.')
            out,err=client.communicate(timeout=5)
            report=json.loads((folder/'report.json').read_text()) if (folder/'report.json').exists() else {'stdout':out,'stderr':err}
            self.assertEqual(client.returncode,0,report);self.assertTrue(direct_checked);self.assertEqual(report['status'],'ok')
        finally:
            if client and client.poll() is None:client.kill();client.communicate()
            if cloud:cloud.terminate();cloud.wait(timeout=10);cloud.stdout.close()
            fixture.terminate();fixture.communicate(timeout=10)
if __name__=='__main__':unittest.main()

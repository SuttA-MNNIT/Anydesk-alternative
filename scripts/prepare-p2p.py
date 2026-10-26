"""Restore pinned NuGet assemblies, verify hashes and embed compressed DLL resources."""
import gzip, hashlib, io, json, urllib.request, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'build/p2p'

def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    notices=[]
    for package in json.loads((ROOT/'p2p-client/dependencies.lock.json').read_text()):
        name,version=package['id'],package['version']
        cache=ROOT/'artifacts/p2p-deps/cache'/f'{name}.{version}.nupkg'
        cache.parent.mkdir(parents=True,exist_ok=True)
        if not cache.exists():
            url=f'https://api.nuget.org/v3-flatcontainer/{name.lower()}/{version.lower()}/{name.lower()}.{version.lower()}.nupkg'
            cache.write_bytes(urllib.request.urlopen(url,timeout=60).read())
        raw=cache.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=package['sha256']:raise RuntimeError('Package checksum mismatch: '+name)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for member in package['assemblies']:
                data=archive.read(member)
                (OUT/Path(member).name).write_bytes(data)
                (OUT/(Path(member).name+'.gz')).write_bytes(gzip.compress(data,compresslevel=9,mtime=0))
            for member in package.get('references',[]):
                ref=ROOT/'build/p2p-ref'/Path(member).name
                ref.parent.mkdir(parents=True,exist_ok=True)
                ref.write_bytes(archive.read(member))
            license_name=package.get('licenseFile')
            license_text=archive.read(license_name).decode('utf-8-sig',errors='replace') if license_name else package.get('license','See package source.')
            notice_file={'Common.Logging':'common-logging','Common.Logging.Core':'common-logging','DnsClient':'dnsclient','IPNetwork2':'ipnetwork','Makaretu.Dns':'net-dns','Makaretu.Dns.Multicast':'net-mdns','SimpleBase':'simplebase','SIPSorcery.WebSocketSharp':'websocket-sharp'}.get(name)
            if notice_file:license_text+='\n'+(ROOT/'p2p-client/licenses'/(notice_file+'.txt')).read_text(encoding='utf-8-sig')
            if package.get('license','').startswith('MIT;') and name!='BouncyCastle.Cryptography':license_text+='\n'+(ROOT/'p2p-client/licenses/dotnet.txt').read_text(encoding='utf-8-sig')
            notices.append(name+' '+version+'\n'+package.get('authors','')+'\n'+package.get('copyright','')+'\nhttps://www.nuget.org/packages/'+name+'/'+version+'\n'+package.get('source','')+'\n'+license_text)
    notice='CampusLink P2P dependency notices\n\nSIPSorcery is distributed under its upstream BSD-3-Clause license with the additional use restriction reproduced below. The LGPL section in its license applies to SIPSorceryMedia.FFmpeg, which is not used here.\nDynamically loaded DLLs can be replaced in the libraries folder alongside the EXE.\nSource and build instructions: https://github.com/SuttA-MNNIT/Anydesk-alternative\nSIPSorcery exact source: https://github.com/sipsorcery-org/sipsorcery/tree/08c2ed0ad72c423ca06950dee2e842488a219884\n\n'+'\n\n'.join(notices)
    (OUT/'THIRD-PARTY-NOTICES.txt').write_text(notice,encoding='utf-8')
    print('Verified',len(notices),'pinned NuGet packages; compressed libraries:',sum(p.stat().st_size for p in OUT.glob('*.gz')),'bytes')
if __name__=='__main__':prepare()

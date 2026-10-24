"""Create an explicit allow-list bundle; never copy office enrollment secrets."""
from pathlib import Path
import hashlib
import importlib.metadata as metadata
import json
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
NOTICES = RELEASE / "third-party"
NOTICES.mkdir(parents=True, exist_ok=True)
for name in ("pillow", "cryptography", "websocket-client", "cffi", "pycparser", "pyinstaller", "dxcam", "numpy", "comtypes"):
    distribution = metadata.distribution(name)
    for entry in distribution.files or []:
        if any(part.lower().startswith(("license", "copying", "notice")) for part in Path(str(entry)).parts):
            source = Path(distribution.locate_file(entry))
            if source.is_file():
                destination = NOTICES / name / str(entry).replace("..", "_")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
for source, target in [(ROOT / "node_modules/ws/LICENSE", NOTICES / "ws-LICENSE.txt"), (Path(sys.base_prefix) / "LICENSE.txt", NOTICES / "Python-LICENSE.txt")]:
    if source.is_file():
        shutil.copy2(source, target)
for source in (Path(sys.base_prefix) / "tcl").rglob("license.terms"):
    target = NOTICES / "Tcl-Tk" / source.relative_to(Path(sys.base_prefix) / "tcl")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

names = ["README.md", "package.json", "package-lock.json", "START-RELAY.cmd", "START-HOST.cmd", "START-HOST-HIGHFPS.cmd", "START-TUNNEL.cmd", "INSTALL.cmd", ".gitignore", ".gitattributes"]
paths = [ROOT / name for name in names]
for directory in ("server", "web", "host", "scripts", "deploy", "docs", "tests", "node_modules/ws"):
    paths.extend(p for p in (ROOT / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name not in ("NETWORK.local.md", "network-inspection.json"))
paths += [ROOT / "config/host.example.json", ROOT / "dist/CampusLinkHost.exe", ROOT / "dist/CampusLinkHost-HighFPS.exe", ROOT / "tools/cloudflared.exe"]
paths += [p for p in NOTICES.rglob("*") if p.is_file()]
token = json.loads((ROOT / "config/relay.json").read_text())["enrollmentToken"].encode()
archive = RELEASE / "CampusLink-0.2.0-HighFPS-Windows-x64.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
    for file in sorted(set(paths)):
        relative = file.relative_to(ROOT).as_posix()
        if relative in ("config/relay.json", "config/host.json"):
            raise RuntimeError("Private configuration may not be packaged")
        data = file.read_bytes()
        if token in data:
            raise RuntimeError(f"Enrollment secret found in {relative}")
        bundle.writestr("CampusLink/" + relative, data)
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(RELEASE / "SHA256SUMS-HighFPS.txt").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "files": len(set(paths)), "sha256": digest, "privateConfigExcluded": True}, indent=2))

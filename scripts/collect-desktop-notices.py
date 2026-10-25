"""Collect dependency notices inside the single-file executable."""
import importlib.metadata as metadata
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
target = ROOT / "build/desktop-notices"
target.mkdir(parents=True, exist_ok=True)
for package in ("pillow", "cryptography", "websocket-client", "cffi", "pycparser", "numpy", "comtypes", "dxcam", "pyinstaller"):
    dist = metadata.distribution(package)
    for entry in dist.files or []:
        if any(part.lower().startswith(("license", "notice", "copying")) for part in Path(str(entry)).parts):
            source = Path(dist.locate_file(entry))
            if source.is_file():
                destination = target / package / str(entry).replace("..", "_")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
for source, destination in ((Path(sys.base_prefix) / "LICENSE.txt", target / "Python-LICENSE.txt"), (ROOT / "node_modules/ws/LICENSE", target / "ws-LICENSE.txt"), (ROOT / "docs/THIRD-PARTY.md", target / "COMPONENTS.md")):
    if source.is_file():
        shutil.copy2(source, destination)
for source in (Path(sys.base_prefix) / "tcl").rglob("license.terms"):
    destination = target / "Tcl-Tk" / source.relative_to(Path(sys.base_prefix) / "tcl")
    destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, destination)
node_version = subprocess.check_output([sys.argv[1], "--version"], text=True).strip()
for name, url in (("node-LICENSE.txt", f"https://raw.githubusercontent.com/nodejs/node/{node_version}/LICENSE"), ("cloudflared-LICENSE.txt", "https://raw.githubusercontent.com/cloudflare/cloudflared/2026.10.3/LICENSE")):
    with urllib.request.urlopen(url, timeout=30) as response:
        (target / name).write_bytes(response.read())
print("Collected desktop dependency notices.")

# Third-party components

CampusLink is an independent implementation. It contains no AnyDesk source, branding or proprietary codec.

The older 0.3.1 `CampusLinkClient.exe` uses the Windows-provided .NET Framework 4.8+ libraries and Windows CNG, GDI and input APIs. It includes no third-party runtime or library.

The new `p2p_Remote_Desktop.exe` also uses Windows .NET Framework 4.8+, CNG, GDI and input APIs. It embeds compressed managed WebRTC libraries, rather than a Python/Node/browser runtime: SIPSorcery 10.0.17, BouncyCastle.Cryptography 2.7.0, SIPSorceryMedia.Abstractions and their pinned dependencies. Exact package versions, SHA-256 digests, assembly paths and attribution are in `p2p-client/dependencies.lock.json`. `scripts/prepare-p2p.py` verifies downloads and combines package/upstream license text into `THIRD-PARTY-NOTICES-P2P.txt`, also embedded under **About / licenses**. SIPSorcery and its media abstractions use their upstream BSD-3-Clause license **with an additional use restriction**, reproduced in full; the LGPL section applies to FFmpeg, which this app does not use. Other dependency terms include MIT, Apache-2.0, BSD and the notices packaged with Concentus. This project does not relicense third-party code.

The P2P server bundles Node, ws, Python, Tcl/Tk and cloudflared. It does not bundle desktop capture/input functionality. The components below also cover the older full server/host releases; they are not all carried by the new broker server or P2P client.

Runtime dependencies and upstream licensing:

| Component | Use | Upstream |
|---|---|---|
| Node.js | Office relay runtime; installed separately | https://nodejs.org/ (MIT and bundled notices) |
| ws 8.22.0 | WebSocket relay | https://github.com/websockets/ws (MIT) |
| Python 3.12 | Host runtime embedded by PyInstaller | https://www.python.org/ (PSF license) |
| Pillow 12.3.0 | Screen capture and JPEG encoding | https://python-pillow.github.io/ (MIT-CMU and bundled notices) |
| cryptography 47.0.0 | AES-GCM, PBKDF2 | https://cryptography.io/ (Apache-2.0/BSD and bundled OpenSSL notices) |
| websocket-client 1.9.2 | Host WebSocket client | https://github.com/websocket-client/websocket-client (Apache-2.0) |
| PyInstaller 6.22.3 | Windows packaging | https://pyinstaller.org/ (GPL with bootloader exception) |
| cloudflared 2026.10.3 | Optional outbound tunnel | https://github.com/cloudflare/cloudflared (Apache-2.0 and upstream bundled notices) |
| DXcam 0.3.0 | High FPS DXGI desktop capture | https://github.com/ra1nty/DXcam |
| numpy 2.5.4 | DXcam frame arrays | https://numpy.org/ |
| comtypes 1.4.17 | DXGI COM interface | https://github.com/enthought/comtypes |

Pinned tunnel download:

`https://github.com/cloudflare/cloudflared/releases/download/2026.10.3/cloudflared-windows-amd64.exe`

Official release SHA-256:

`76b2805253d0d6ffacb092a7acfbee99e7af6917835c0c5410e23f3ef5052da2`

Dependency license files and upstream notices must accompany redistribution. `release/third-party/` collects the locally available dependency license files for the packaged host. Consult the upstream sources for complete attribution requirements before distributing modified versions publicly.

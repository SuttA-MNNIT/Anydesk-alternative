# Third-party components

CampusLink is an independent implementation. It contains no AnyDesk source, branding or proprietary codec.

The small `CampusLinkClient.exe` uses the Windows-provided .NET Framework 4.8+ libraries and Windows CNG, GDI and input APIs. It includes no third-party runtime or library. The components below are bundled in, used to build, or support the full server/legacy host; they are not carried by the small client.

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

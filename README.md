# CampusLink

**New: one-file native desktop app.** Copy `dist/CampusLink.exe` to both Windows PCs. On one choose **Share this computer**; on the other paste its connection code and choose **Connect**. No CMD windows, URL editing, browser, Python installation or Node installation is required for users. The app starts/stops its own bundled relay and tunnel. See [the desktop guide](docs/DESKTOP.md) for native controls and switching direction. The server remains on the office computer; VPS migration is deferred.

**Download:** [CampusLink.exe for Windows x64](https://github.com/SuttA-MNNIT/Anydesk-alternative/releases/download/v0.3.0/CampusLink.exe). Copy this same file to both PCs; use **Share this computer** on one and **Connect** on the other.

An independently built, self-hosted **attended Windows remote desktop** with native Share/Connect modes, an office-hosted relay and legacy browser compatibility. The current desktop build is one executable; the original separate host and command launchers are preserved. This is not a feature-for-feature reproduction of AnyDesk.

**Downloads:** Windows executables and the complete prepared bundle are distributed through [GitHub Releases](https://github.com/SuttA-MNNIT/Anydesk-alternative/releases). This Git repository contains source and launchers; generated binaries, local enrollment secrets and identifying network inspection data are excluded.

**High FPS upgrade:** `START-HOST-HIGHFPS.cmd` launches the separately built host with DXGI capture, bounded frame pipelining, and 30/60 fps targets. The original executable is preserved. See [docs/HIGH-FPS.md](docs/HIGH-FPS.md) for switching instructions and performance limits. Targets are not measured end-to-end guarantees.

## Legacy host/browser setup

1. Double-click **START-RELAY.cmd** and leave its terminal open. The relay listens only on `127.0.0.1:8787`.
2. Double-click **START-HOST.cmd**. The office host reads the enrollment token from the generated private `config/relay.json`.
3. Click **Go online** in the host app.
4. Open <http://localhost:8787> in a browser. Enter the host's 10-digit device ID, 32-character access key and your name.
5. Approve on the host: **View only** or **Allow control**. Use **Stop / disconnect** or close the host to end access.

Testing the host and viewer on one desktop creates a visual feedback effect. A second computer is preferable for practical use. The downloaded executable is unsigned and has not undergone an independent security audit.

The prepared workspace is installed already. The `release/CampusLink-0.2.0-HighFPS-Windows-x64.zip` bundle includes both host executables, relay source/dependency and tunnel connector, but excludes private office configuration. The original 0.1.0 archive is preserved separately. After extracting a bundle on another relay machine, run `npm.cmd run setup` once to generate a fresh host enrollment token; `START-RELAY.cmd` also does this automatically. Node.js 22+ is required for the relay. The Windows host executables need neither Python nor Node.js.

## Outside access without router access or a VPS

The machine is on a private campus subnet; see [docs/NETWORK.md](docs/NETWORK.md). An external HTTPS entry point is required.

### Temporary test — no domain or account

1. The prepared workspace includes the official Windows x64 `cloudflared` binary at `tools/cloudflared.exe`; its download checksum was checked against the official GitHub release. For a fresh source checkout, obtain it from <https://github.com/cloudflare/cloudflared/releases/latest> and save it at that path.
2. Start the relay, then double-click **START-TUNNEL.cmd**. This explicitly publishes only the CampusLink relay through an outbound tunnel; no router ports are opened. The launcher uses HTTP/2 for the outbound tunnel.
3. Copy the printed `https://…trycloudflare.com` URL. **Stop the host if it is online, paste that URL into Office relay URL, and click Go online again.**
4. Open the same HTTPS URL from the outside computer or phone. Connect with the host ID/key and approve on Windows.
5. Keep the relay and tunnel terminals open. Ctrl+C in the tunnel terminal removes public access. The URL changes when restarted.

Quick Tunnels are development tools without an uptime guarantee; the URL is public and the relay page can be opened by anyone who knows it. Device IDs, keys and host approval control desktop access. Quick Tunnels have a 200 in-flight request limit. Cloudflare supports WebSockets, but actual streaming performance and the service's applicable limits must be evaluated for your deployment. A permanent college installation should use an approved stable tunnel or a public VPS edge.

### Permanent option — named Cloudflare Tunnel

Requires a Cloudflare account and a domain you control. Follow Cloudflare's current instructions to authenticate, create a named tunnel and route a hostname. Adapt `deploy/cloudflared.example.yml` so `desk.yourdomain` points to `http://127.0.0.1:8787`, then run the connector on the office computer. No credential or domain has been created by this project. Use the final public HTTPS URL in every host and browser. Do not add interactive Cloudflare Access authentication in front of the host WebSocket endpoint without adding machine authentication to the host app.

### Optional public VPS edge

`deploy/frps.example.toml`, `deploy/frpc.example.toml` and `deploy/Caddyfile.example` show an alternative: frpc in the office initiates an outbound TLS tunnel to frps on a VPS; Caddy provides public HTTPS. The forwarded origin port is bound only to VPS loopback. Replace the sample token, configure certificate validation for the frp link, and provision DNS/TLS before use. This option needs a VPS and has not been deployed here.

## Windows hosts on other computers

Copy `dist/CampusLinkHost.exe` to each Windows x64 computer. The executable does not contain the enrollment token or an access key and does not require Python. Enter the public relay URL and the host enrollment token from the office's private `config/relay.json`. Alternatively put a private `config/host.json` next to the executable, following `config/host.example.json`. Protect the enrollment token: it grants permission to register hosts on your relay. Never publish `config/relay.json` or a populated `host.json`.

The ID and 128-bit access key are generated for each app launch. The key is not sent in plaintext to the relay or saved on disk. Restart the host to rotate it. Knowing the key still requires local approval for each session. Stop disconnects the host and session; there is no unattended background access or automatic reconnect.

## Implemented

- Primary-monitor screen sharing: JPEG frames, Economy (5 fps / 1280 px), Balanced (10 fps / 1600 px), Sharper (15 fps / 1920 px). Actual fps depends on CPU, capture time, network and acknowledgement latency.
- Browser viewer with full screen, connection status, resolution/fps/bitrate, pointer position, mouse clicks, scroll and common physical keyboard keys.
- View-only or remote-control approval, live control revocation, participant disconnect, host closure teardown, release of held input on focus loss/disconnect.
- AES-256-GCM session packets, independent direction keys, fresh per-session salt, PBKDF2-SHA256 derivation, authenticated sequence numbers and replay rejection.
- Opaque office relay with host enrollment, no public host directory, origin checking, size/rate limits, heartbeat and frame acknowledgement backpressure.
- Loopback default, no inbound Windows firewall changes. HTTPS required except on localhost.

## Limits

This version uses TCP/WebSocket JPEG streaming, not AnyDesk's proprietary codec or a WebRTC transport. One viewer per host; many hosts may register, but load capacity has not been benchmarked. No audio, file transfer, clipboard sync, multi-monitor switching, unattended login, Windows service, UAC/secure-desktop control, Ctrl+Alt+Delete, wake-on-LAN or automatic reconnection. Physical keyboard mapping is best tested with US-layout keys; IME/text composition and shortcuts reserved by the browser/OS are not handled. Normal Windows integrity restrictions apply to input into elevated applications. Screen capture requires an unlocked interactive session; do not rely on it across Windows lock/sign-in.

The browser JavaScript is served by your relay. Session encryption protects contents from a passive relay observer; an actively compromised relay/HTTPS edge could replace the browser code. Trusted delivery of viewer code and HTTPS are part of the security boundary. Device IDs, timing, packet sizes, addresses and other routing metadata are visible to the relay/edge. This is a new implementation; production hardening, signing and an independent security review remain.

## Install from source

Windows x64, Node.js 22+ and Python 3.12 are needed for source setup; only Node is needed on a relay-only machine. Run `INSTALL.cmd`, or:

```powershell
npm.cmd ci
npm.cmd run setup
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r host/requirements.lock.txt
npm.cmd start
```

In a separate terminal, run `.\.venv\Scripts\python.exe host/app.py`. To rebuild the distinct High FPS executable: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-host.ps1`. This preserves the original executable.

Validation:

```powershell
npm.cmd test
node tests/cross_runtime.mjs
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_host.py -v
```

See [docs/VALIDATION.md](docs/VALIDATION.md) for measured checks and remaining external verification. The generated access credentials are private configuration and are excluded from any shareable source archive.

## Official references

- Cloudflare Quick Tunnels: <https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/>
- Cloudflare Tunnel WebSockets: <https://developers.cloudflare.com/cloudflare-one/faq/cloudflare-tunnels-faq/>
- frp: <https://gofrp.org/en/docs/>
- Microsoft SendInput / Windows integrity restrictions: <https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-sendinput>

# CampusLink Desktop 0.3.1 — server and small client

Use **`dist/CampusLinkServer.exe`** on the office Windows x64 PC and **`dist/CampusLinkClient.exe`** on the outside Windows x64 PC. Each role needs one executable. The server retains the tested v0.3.0 code and bundled relay/tunnel. The client is a separate C# Windows Forms application using Windows .NET Framework 4.8+ and system cryptography; it bundles no Python, Node, tunnel connector or third-party libraries. Windows 11 includes .NET Framework 4.8 or newer; some older Windows PCs may need Microsoft's framework update. No runtime is silently downloaded by the client.

| Edition | File size | Role |
|---|---:|---|
| CampusLinkServer.exe | 88,967,631 bytes | Office desktop plus managed relay/tunnel |
| CampusLinkClient.exe | 83,968 bytes (82 KiB) | Connect, view, control, and reverse an approved session |

The old combined executable contained compressed Node (~34.4 MB), cloudflared (~18.7 MB), Python and its libraries. Single-file packaging did not remove these dependencies. The small client uses the OS-provided framework instead. Executable size and running memory usage are different quantities.

## Connect two computers

1. On the office PC, open **CampusLinkServer.exe** and click **Share this computer**.
2. Wait until the app says it is ready. The relay and outbound tunnel start as hidden, managed helpers.
3. Click **Copy code** and send the connection code privately to the intended person. Alternatively **Save invitation** and send that `.campuslink` file.
4. On the other PC, open **CampusLinkClient.exe**, paste the code and click **Connect**, or choose **Open invitation**.
5. Approve **View only** or **Allow control** on the office PC. The screen appears inside a native desktop window.

Only one desktop session is active in an app at a time. Stop an existing connection before starting a separate one. No background service or unattended access is installed.

The connection code includes the temporary route, device ID and access key. It is not a short globally discoverable AnyDesk ID. A fixed rendezvous service is deferred to the later VPS work. **There is no URL field and no URL needs to be copied.** Each new hosted connection creates a new access key and tunnel; previous invitations stop working when hosting stops. A persistent, non-secret device ID is saved in `%LOCALAPPDATA%/CampusLink/desktop.json`.

## Switch who is viewed

In the native viewer, click **Share my screen instead**. Choose whether the other person can only view or also control your screen. The other side must accept the direction switch. Existing sharing stops before the other screen begins. The same encrypted session and original office relay stay in use; no new invitation or tunnel is required. Either side can reverse direction again. Pending requests expire, and a denied request never starts capture.

**Request control** asks the sharing side to approve keyboard/mouse access if a session is view only. The sharing app can revoke control at any time. F11 toggles full screen; Escape exits full screen. The viewer releases held input when it loses focus. Windows secure desktop, UAC and integrity restrictions still apply.

The small client can share its screen after an approved direction switch, using Windows GDI capture. This reverse-capture path is not the DXGI-accelerated Python host path and may achieve a lower frame rate. The office server retains its DXGI capture and 30/60 fps targets. Neither path guarantees those frame rates over the Internet. The small client cannot start a public relay or create a hosting invitation by itself.

## Stop

Use **Stop / disconnect** or close the app. On the computer that created the hosted connection, this also closes its relay and tunnel. Processes are tracked by their own process handles; the app does not kill other Node servers or unrelated tunnels. A Windows Job Object also contains the owned helpers for parent-process termination. Closing the app on the other computer disconnects its session.

## Current environment and limits

The server remains on the office PC. The only outside component is the automatically created public Cloudflare tunnel edge. No GoDaddy or other VPS has been provisioned. Both computers still need Internet access, and campus egress policy must permit the connector. Temporary tunnels are development tools, have no uptime guarantee and cannot provide a stable route across restarts.

The old browser viewer is retained for compatibility, but the new connection workflow and direction switch use native clients. Original 30/60 fps **targets** remain; actual native render rate and Internet performance must be measured on the two PCs. JPEG/WebSocket streaming is retained. Audio, file transfer, clipboard synchronization, multiple concurrent sessions, unattended sign-in and UAC control are not implemented in this release.

Both executables are unsigned. The server extracts its bundled helpers to Windows temporary storage and runs them hidden as children; it is one file for the user to copy, not one operating-system process. The small client runs no server/tunnel helpers and uses Windows libraries instead. Neither executable embeds the office enrollment token. A fresh temporary relay token is generated when hosting starts. Invitations contain the per-hosting access key and should be shared only with the intended viewer. Local approval remains mandatory.

## Build from source

For the full server, install the pinned Python dependencies, Node.js 22+, ws via `npm ci`, PyInstaller 6.22.3 and the official `tools/cloudflared.exe` connector. Then:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-desktop.ps1
```

For development, run `.\.venv\Scripts\python.exe run_desktop.py`. The build downloads matching Node and cloudflared license text from their official source repositories. A packaged diagnostic that starts no public connection is available:

```powershell
dist\CampusLink.exe --check-installation artifacts\desktop-installation-check.json
```

## Validation scope

Tests cover invitation validation, native JPEG rendering/ACKs, local approval, view-only restrictions, control revocation, reversal in both directions on the same relay, declined reversal, stale ACK rejection and cleanup of owned helper processes. A real public-tunnel route test used two native protocol clients on this PC with synthetic frames and no real Windows input. It exercised HTTPS, encrypted 404,842-byte JPEG frames, reverse video and cleanup. This is not a fresh acceptance test between two physical PCs or evidence of 30/60 fps through the tunnel.

For the small client, no Python, Node, third-party .NET package or downloaded SDK is needed to build it on a Windows machine that has the .NET Framework C# compiler:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-client.ps1
```

The build fails if the client reaches 10,000,000 bytes. CNG AES-256-GCM and PBKDF2 are checked against the Python server, including wrong-key, tamper, reflection and replay rejection. Native-client protocol tests check frames, control changes, view-only input rejection and reversal in both directions, locally and through the real public tunnel. Synthetic frames and recorded input are used; no real desktop or Windows input is exposed by those tests.

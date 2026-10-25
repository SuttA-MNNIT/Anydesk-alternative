# CampusLink Desktop 0.3 — one executable

Copy **`dist/CampusLink.exe`** to each Windows x64 PC. It contains the native app, Python runtime, Node relay runtime, WebSocket dependency, tunnel connector and notices. Users do not need to install Python or Node, start CMD files, configure the router, edit a URL, or use a browser. The original host executables are preserved.

## Connect two computers

1. On the office PC, open **CampusLink.exe** and click **Share this computer**.
2. Wait until the app says it is ready. The relay and outbound tunnel start as hidden, managed helpers.
3. Click **Copy code** and send the connection code privately to the intended person. Alternatively **Save invitation** and send that `.campuslink` file.
4. On the other PC, open the **same CampusLink.exe**, paste the code and click **Connect**, or choose **Open invitation**.
5. Approve **View only** or **Allow control** on the office PC. The screen appears inside a native desktop window.

Only one desktop session is active in an app at a time. Stop an existing connection before starting a separate one. No background service or unattended access is installed.

The connection code includes the temporary route, device ID and access key. It is not a short globally discoverable AnyDesk ID. A fixed rendezvous service is deferred to the later VPS work. **There is no URL field and no URL needs to be copied.** Each new hosted connection creates a new access key and tunnel; previous invitations stop working when hosting stops. A persistent, non-secret device ID is saved in `%LOCALAPPDATA%/CampusLink/desktop.json`.

## Switch who is viewed

In the native viewer, click **Share my screen instead**. Choose whether the other person can only view or also control your screen. The other side must accept the direction switch. Existing sharing stops before the other screen begins. The same encrypted session and original office relay stay in use; no new invitation or tunnel is required. Either side can reverse direction again. Pending requests expire, and a denied request never starts capture.

**Request control** asks the sharing side to approve keyboard/mouse access if a session is view only. The sharing app can revoke control at any time. F11 toggles full screen; Escape exits full screen. The viewer releases held input when it loses focus. Windows secure desktop, UAC and integrity restrictions still apply.

## Stop

Use **Stop / disconnect** or close the app. On the computer that created the hosted connection, this also closes its relay and tunnel. Processes are tracked by their own process handles; the app does not kill other Node servers or unrelated tunnels. A Windows Job Object also contains the owned helpers for parent-process termination. Closing the app on the other computer disconnects its session.

## Current environment and limits

The server remains on the office PC. The only outside component is the automatically created public Cloudflare tunnel edge. No GoDaddy or other VPS has been provisioned. Both computers still need Internet access, and campus egress policy must permit the connector. Temporary tunnels are development tools, have no uptime guarantee and cannot provide a stable route across restarts.

The old browser viewer is retained for compatibility, but the new connection workflow and direction switch use native clients. Original 30/60 fps **targets** remain; actual native render rate and Internet performance must be measured on the two PCs. JPEG/WebSocket streaming is retained. Audio, file transfer, clipboard synchronization, multiple concurrent sessions, unattended sign-in and UAC control are not implemented in this release.

The executable is unsigned. On first launch, its bundled helpers are extracted to Windows temporary storage, then run hidden as children; this is one file for the user to copy, not one operating-system process. It never embeds the office enrollment token. A fresh temporary relay token is generated when hosting starts. Invitations contain the per-hosting access key and should be shared only with the intended viewer. Local approval remains mandatory.

## Build from source

Install the pinned Python dependencies, Node.js 22+, ws via `npm ci`, PyInstaller 6.22.3 and the official `tools/cloudflared.exe` connector. Then:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-desktop.ps1
```

For development, run `.\.venv\Scripts\python.exe run_desktop.py`. The build downloads matching Node and cloudflared license text from their official source repositories. A packaged diagnostic that starts no public connection is available:

```powershell
dist\CampusLink.exe --check-installation artifacts\desktop-installation-check.json
```

## Validation scope

Tests cover invitation validation, native JPEG rendering/ACKs, local approval, view-only restrictions, control revocation, reversal in both directions on the same relay, declined reversal, stale ACK rejection and cleanup of owned helper processes. A real public-tunnel route test used two native protocol clients on this PC with synthetic frames and no real Windows input. It exercised HTTPS, encrypted 404,842-byte JPEG frames, reverse video and cleanup. This is not a fresh acceptance test between two physical PCs or evidence of 30/60 fps through the tunnel.

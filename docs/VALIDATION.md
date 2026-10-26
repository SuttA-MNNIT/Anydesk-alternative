# P2P preview — 26 October 2026

- `p2p_Remote_Desktop` adds a broker registration endpoint, persistent server-issued client IDs, arbitrary client pairing, direct WebRTC data channels and automatic end-to-end encrypted WSS relay fallback. Separate pairs run simultaneously; each endpoint has one active session.
- The P2P harness passed locally and through a real temporary public HTTPS/WSS tunnel. Both endpoints ran on this Windows PC. It used real UDP ICE/DTLS/SCTP connections and generated JPEGs large enough to require data-channel fragmentation. No real desktop images or Windows input were used.
- The direct-only interval asserted **zero additional forwarded payload bytes** at the broker while the stream continued. The public run also passed forced relay, two simultaneous pairs, interruption of an established direct channel followed by continued frames on relay, direction switching and wrong-key rejection before capture/approval. Wrong-key rejection intentionally produces a CNG authentication failure in the private test diagnostics.
- Local approval precedes capture; view-only input is rejected; explicit grant and later revocation work. Registration tests cover unique IDs, duplicate identity rejection, persistence, pair isolation and malformed/cross-session packet rejection. Late frames from a recently closed pair are dropped without unregistering a client.
- Final standalone package checks passed with installed Python/Node removed from the child PATH. The client created its native window without external DLLs. The server started its bundled runtime, passed local health, stopped its owned helpers, and contained the exact current broker source. Inspection found no private configuration in the server bundle. The client home window was visually inspected; no connected-session GUI automation was performed.
- Executable sizes and SHA-256 values: [p2p-packages.json](measurements/p2p-packages.json). The client is **7,560,704 bytes (7.56 MB)**; server **65,384,593 bytes (65.38 MB)**. The client's embedded license notices are included in its size.
- Final suite: 20 Python checks, 12 Node checks and the JavaScript/Python interoperability check passed (33 total). The additional public-tunnel P2P run and both packaged installation checks passed. `npm audit --omit=dev` reported zero known vulnerabilities for ws at validation time.
- Tests on two physical PCs behind different NATs, sustained displayed FPS, gigabit throughput, long-duration/load testing, code signing and independent security review remain unverified. Quick Tunnel addresses are temporary. VPS deployment is deferred.

The older sections below describe earlier releases and their validation scopes.

# Validation — 23 October 2026

## Small client / separate server — 26 October 2026

- `CampusLinkClient.exe` is 83,968 bytes (82 KiB); its build enforces a strict 10 MB limit. It uses installed Windows .NET Framework 4.8+ and native CNG crypto, with no bundled server, Python, Node, tunnel connector or third-party client libraries.
- Windows CNG/Python interoperability passed in both directions. Wrong key, tampering, reflected packets and replay were rejected. The native Windows `INPUT` structure is 40 bytes.
- Small-client integration passed against the existing server: encrypted JPEGs, initial view-only approval, request/grant/revoke control, recorded key input, role reversal in both directions, and rejection of encrypted input while reverse sharing is view only. The same tests also passed through a real public Cloudflare tunnel on this PC. All imagery and input were synthetic/recorded.
- Portable startup passed from a folder containing only the small executable with Python/Node removed from PATH. .NET Framework was already installed; this is not a claim of a runtime-free executable.
- Current combined checks: 19 Python, 8 Node and 1 cross-runtime test (28 total).
- The main client window was visually inspected. The follow-up screen-rendering UI test was stopped with the physical Escape key; protocol/JPEG decoding tests passed. A new two-physical-PC acceptance test and actual native FPS measurement remain outstanding.
- `CampusLinkServer.exe` is an unchanged copy of the validated full v0.3.0 executable, renamed to distinguish roles. Its server startup, relay/tunnel management, notices and prior validation are retained.

## Unified native desktop — 25 October 2026

- Native suite: invitation validation, offline GUI startup/JPEG rendering, approval, view-only/input permissions, control revocation, denied sharing, native direction switches both ways, stale stream ACK rejection, and managed relay cleanup.
- Existing suites remain applicable. Total current automated checks: 8 Node tests, 17 Python tests and 1 cross-runtime crypto check (26 checks).
- Real public-tunnel smoke test passed with two native clients on this PC, synthetic encrypted JPEG frames of 404,842 bytes each in both directions, and all owned helper processes stopped afterwards. No real desktop was captured or remote Windows input injected by that smoke test.
- A new two-PC outside-network acceptance test and end-to-end native FPS measurement remain outstanding.
- Final portable executable startup passed from a separate folder containing only `CampusLink.exe`, with the installed Python/Node locations removed from the child's PATH. The bundled Node 24.18.0 and cloudflared 2026.10.3 both ran, the app remained offline, and its native UI initialized.
- Embedded asset inspection confirmed the Node runtime, connector, server, ws package and dependency notices are present and private configuration is absent. A loopback relay launched successfully using the assets extracted from the final executable; its Windows Job Object was created and its owned helper was stopped.

## High FPS upgrade

- Ten Python tests passed after the upgrade, including the original security/input tests plus bounded multi-frame pipelining, byte-budget backpressure, extra ACK rejection, timeout/teardown wakeup, and DXGI compatibility fallback. Original low-rate stop-and-wait behavior is also checked.
- Local DXGI processing benchmark: Smooth 1600 px averaged 24.69 ms/frame (40.5 fps processing ceiling); Fast 960 px averaged 10.69 ms/frame (93.6 fps processing ceiling). These are local processing figures, **not end-to-end displayed frame rates**. See `HIGH-FPS.md` for scope and limits.
- The original `dist/CampusLinkHost.exe` and 0.1.0 archive are preserved. The working relay and tunnel were not restarted.
- Actual 30/60 fps through the user's outside-network session has not been measured by the agent.
- Final `dist/CampusLinkHost-HighFPS.exe` installation diagnostic passed with `frozen: true`, `offline: true`, 40-byte Windows `INPUT`, 1920 × 1080 capture and **DXGI accelerated capture** selected. Original executable SHA-256 remains `21de5f9962f6ac202aebfcc27aea77176d2405a52f1116ed0539fd2fc694e3aa`.
- Seven relay/channel tests and the JavaScript/Python interoperability test passed again after the host upgrade: 18 automated checks across the Node, Python and interoperability suites.

## Passed locally

- Seven Node.js relay/channel tests: HTTP/static content and restrictive headers, no secret-file exposure, host enrollment and duplicate IDs, cross-origin WebSocket rejection, encrypted packet routing, unavailable/busy devices and disconnect cleanup, malformed/oversized messages, wrong-key/tamper/reflection/replay rejection.
- Six Python host tests: crypto rejection, HTTPS URL rules, Windows `INPUT` structure layout and malformed event rejection, authenticated-but-unapproved input blocking, view-only input blocking, wrong-key request rejection before an approval prompt, JPEG streaming after approval and frame acknowledgement backpressure, teardown releasing input state.
- JavaScript → Python → JavaScript encrypted handshake interoperability using the actual browser/host protocol modules.
- Actual Windows capture: **1920 × 1080, RGB**. The image was not saved or sent externally.
- Tk host UI construction and offline startup. The source starts without a network connection until Go online.
- Browser integration in the in-app Chromium browser at `http://localhost:8787`: connected to a separate Python synthetic host; authenticated; displayed **1280 × 720** encrypted JPEG screen; showed remote-control mode; transmitted `KeyA` down/up; disconnected and returned to the connection form. The fixture records input and does not operate Windows. Preview: `screenshots/encrypted-session.png`.
- Windows x64 executable built with Python 3.12 and PyInstaller. Packaging includes Pillow, cryptography, Tk and websocket-client. No host enrollment token, ID or access key is embedded.
- Final executable installation check executed successfully: `frozen: true`, `offline: true`, native Windows `INPUT` size **40 bytes**, primary monitor **1920 × 1080**, Tk requested layout **646 × 852** inside the configured **690 × 900** window. Report: `artifacts/host-installation-check.json`. This checks bundled startup dependencies, not an outside session.
- `npm audit --omit=dev`: **0 known vulnerabilities** for the pinned dependency set at validation time.
- Official `cloudflared` 2026.10.3 Windows x64 connector downloaded, SHA-256 matched to the official GitHub release digest, and `--version` ran successfully. No public tunnel was started.

## Not established

- An outside-network session, campus tunnel permission or college egress filtering behavior.
- Internet throughput or 1 Gbps streaming capability, session capacity, latency under load, security penetration testing or long-duration soak testing.
- Real remote input into a second Windows computer, different keyboard layouts, locked/elevated desktops or other Windows versions. Input packet transmission, validation and native ABI structure have been checked; an external host/viewer acceptance test remains necessary.
- Production TLS/domain configuration or a permanent public tunnel. The server remains loopback-only until the user starts an outbound connector.
- Code signing, installer trust reputation or independent security review.

The synthetic test fixture and test credentials in `tests/mock_host.py` are separate from the production host. There is no auto-approval option in the delivered host.

## Repeatable checks

```powershell
npm.cmd test
node tests/cross_runtime.mjs
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_host.py -v
npm.cmd audit --omit=dev
```

For browser QA, start the local relay and then run `.\.venv\Scripts\python.exe tests/mock_host.py`. Use the disposable ID/key specified in that test file. Stop that test process after QA. Never use those credentials as production credentials.

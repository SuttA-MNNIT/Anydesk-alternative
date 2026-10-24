# Validation — 23 October 2026

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

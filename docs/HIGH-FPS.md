# Higher frame rates

The original host offers 5, 10 and 15 fps and permits only one unacknowledged JPEG at a time. Selecting a bigger number alone cannot remove the network round-trip wait or capture overhead.

The High FPS build changes three things:

1. Adds **Smooth — 30 fps target / 1600 px** and **Fast — 60 fps target / 960 px**. JPEG quality is 60 and 50 respectively. These presets use faster nearest-neighbor resizing and, where possible, pixel decimation before RGB conversion. Text and fine lines may look rougher. The original lower-rate presets retain bilinear resizing.
2. Uses **DXGI Desktop Duplication via DXcam** where supported, with a Pillow compatibility fallback. Only the primary screen is captured. Desktop capture is created only after host approval, and released on teardown.
3. Allows up to **4 outstanding frames at 30 fps** or **8 at 60 fps**, with a **2 MiB** outstanding JPEG budget. Frame acknowledgements still bound the stream; a slow viewer stalls the producer instead of allowing unlimited queued frames. The original low-rate presets keep a one-frame window. The encrypted packet format and original browser ACK format are preserved.

## Switch without restarting your relay or tunnel

1. When ready to end the current session, stop/close the original Windows host.
2. Open `START-HOST-HIGHFPS.cmd`. The original `dist/CampusLinkHost.exe` is preserved. The new executable is `dist/CampusLinkHost-HighFPS.exe`.
3. Enter the same currently running public HTTPS tunnel URL in Office relay URL, and Go online.
4. Choose Smooth 30 first, then Fast 60 if the connection remains responsive.
5. On the outside browser, use the same URL with the new host's ID/key and approve again. No new viewer installation or router change is needed.

The browser displays measured resolution/fps/Mbps in the desktop toolbar on a sufficiently wide window. This counter measures decoded/drawn JPEG frames, not unique Windows desktop updates or monitor presentation rate. On the host, the session log identifies DXGI versus compatibility capture.

## Local measurements on this office PC

Thirty samples per preset on the current desktop, after three warm-up samples, including capture, resize, JPEG encoding and AES-GCM, with no network transmission:

| Preset | DXGI local processing time | Local processing ceiling | Estimated JPEG payload at target |
|---|---:|---:|---:|
| Smooth: 30 target, max width 1600 | 24.69 ms/frame | 40.5 frames/s | 35.88 Mbps |
| Fast: 60 target, max width 960 | 10.69 ms/frame | 93.6 frames/s | 29.09 Mbps |

These figures come from `artifacts/capture-benchmark-fast.json`. They show local processing headroom for these targets on the sampled desktop. They do **not** establish displayed 30/60 fps through your tunnel, and they omit the cursor marker, packet framing, browser decode, OS scheduling and network costs. Fast uses a lower resolution and may repeat unchanged desktop content. Images were neither saved nor sent externally. Motion and other screen content can alter the measurements considerably.

With the original compatibility capture, this same test measured only 16.7 fps of local processing headroom at Smooth settings and 19.1 fps at Fast settings. If the host log reports compatibility capture, the 30/60 target is unlikely to be reached on this PC with that path.

## What the target means

60 fps gives the host about **16.7 ms** per frame; 30 fps gives about **33.3 ms**. Capture, resizing, JPEG encoding, encryption, transport, tunnel bandwidth, packet loss and browser decoding all matter. Eight frames in flight can improve throughput on higher-delay links but can also add visible delay when the viewer is slow. Start at 30 if latency matters more than frame count.

At an illustrative **100 KB per JPEG**, 30 fps needs approximately **24 Mbps** and 60 fps approximately **48 Mbps**, before protocol overhead. Actual JPEG size changes greatly with screen content. Your Ethernet's 1 Gbps link speed does not establish usable upload speed or tunnel capacity.

`scripts/benchmark-stream.py` measures capture/resize/JPEG/AES-GCM processing on this PC, without saving images or sending them anywhere. Its results are a local processing ceiling on the current desktop, not proof of end-to-end 30/60 fps. More than 60 fps and a dependable high-motion 1080p60 stream should be treated as a separate video-transport upgrade using hardware video encoding (for example H.264) and an appropriate low-latency transport. This build still uses JPEG over the existing encrypted WebSocket relay and tunnel.

## Source changes

- `host/app.py`: higher-rate profiles and pipelined streaming.
- `host/streaming.py`: frame/byte window and ACK timeout.
- `host/capture.py`: accelerated capture with compatibility fallback.
- `host/requirements.lock.txt`: pinned DXcam/numpy/comtypes dependencies.
- `scripts/build-host.ps1`: builds a distinct High FPS executable.

References: [Microsoft Desktop Duplication](https://learn.microsoft.com/windows/win32/direct3ddxgi/desktop-dup-api), [DXcam](https://github.com/ra1nty/DXcam).

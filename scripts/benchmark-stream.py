"""Local capture/encode/encrypt benchmark. No images are saved or sent over a network."""
import argparse
import ctypes
import io
import json
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "host"))
from capture import DesktopCapture
from protocol import Channel
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument("--frames", type=int, default=40)
parser.add_argument("--output", default="artifacts/capture-benchmark.json")
args = parser.parse_args()
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass
results = []
for accelerated in (False, True):
    for target, width, quality in ((30, 1600, 60), (60, 960, 50)):
        capture = DesktopCapture(accelerated=accelerated)
        cipher = Channel("a" * 32, "b" * 32)
        timings, captures, encodes, sizes = [], [], [], []
        try:
            for index in range(args.frames + 3):
                start = time.perf_counter()
                with capture.grab(max_width=width, fast=target >= 30) as image:
                    after_capture = time.perf_counter()
                    image.thumbnail((width, width), Image.Resampling.NEAREST)
                    out = io.BytesIO(); image.save(out, format="JPEG", quality=quality)
                    frame = out.getvalue(); cipher.seal(2, frame)
                    end = time.perf_counter()
                if index >= 3:
                    timings.append(end - start); captures.append(after_capture - start); encodes.append(end - after_capture); sizes.append(len(frame))
            results.append({"requestedAccelerated": accelerated, "backend": capture.backend, "targetFps": target, "maxWidth": width, "jpegQuality": quality,
                "samples": len(timings), "meanCaptureMs": round(statistics.mean(captures) * 1000, 2), "meanResizeEncodeEncryptMs": round(statistics.mean(encodes) * 1000, 2),
                "meanTotalMs": round(statistics.mean(timings) * 1000, 2), "localProcessingCeilingFps": round(1 / statistics.mean(timings), 1),
                "meanJpegBytes": round(statistics.mean(sizes)), "estimatedPayloadMbpsAtTarget": round(statistics.mean(sizes) * 8 * target / 1e6, 2)})
        finally:
            capture.close()
report = {"scope": "Local capture, resize, JPEG encode and AES-GCM only. Static/current desktop; not a network or displayed-FPS measurement.", "results": results}
destination = Path(args.output); destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))

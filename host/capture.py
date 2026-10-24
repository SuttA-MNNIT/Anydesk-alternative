"""Primary-monitor DXGI capture with a Pillow compatibility fallback."""
import ctypes
import re
from PIL import ImageGrab, Image


class DesktopCapture:
    def __init__(self, accelerated=True):
        self.camera = None
        self.backend = "Pillow compatibility capture"
        if accelerated:
            try:
                import dxcam
                primary = re.search(r"Device\[(\d+)\] Output\[(\d+)\]:[^\n]*Primary:True", dxcam.output_info())
                device, output = (int(primary[1]), int(primary[2])) if primary else (0, 0)
                # BGRA needs no OpenCV conversion dependency.
                self.camera = dxcam.create(device_idx=device, output_idx=output, output_color="BGRA", max_buffer_len=2)
                self.backend = "DXGI accelerated capture"
            except Exception:
                self.camera = None

    def grab(self, max_width=0, fast=False):
        if self.camera is not None:
            try:
                frame = self.camera.grab(copy=False, new_frame_only=False)
                if frame is not None:
                    # Decimate before RGB conversion for the fast preset; avoid copying
                    # full-resolution pixel buffers that will immediately be discarded.
                    step = max(1, frame.shape[1] // max_width) if fast and max_width else 1
                    if step > 1:
                        frame = frame[::step, ::step]
                    height, width = frame.shape[:2]
                    return Image.frombytes("RGB", (width, height), frame.tobytes(), "raw", "BGRX")
            except Exception:
                self.close()
                self.backend = "Pillow compatibility capture"
        width = ctypes.windll.user32.GetSystemMetrics(0)
        height = ctypes.windll.user32.GetSystemMetrics(1)
        return ImageGrab.grab(bbox=(0, 0, width, height), all_screens=True).convert("RGB")

    def close(self):
        camera, self.camera = self.camera, None
        if camera is not None:
            try:
                camera.release()
            except Exception:
                pass

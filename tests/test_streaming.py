import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "host"))
from streaming import FrameWindow
from capture import DesktopCapture
from PIL import Image


class StreamingTests(unittest.TestCase):
    def test_byte_budget_blocks_even_with_frame_slots_available(self):
        window = FrameWindow(max_bytes=100)
        window.sent(80)
        outcome = []
        waiter = threading.Thread(target=lambda: outcome.append(window.wait(60, threading.Event(), 50)), daemon=True)
        waiter.start(); time.sleep(.06)
        self.assertTrue(waiter.is_alive())
        window.acknowledge(); waiter.join(1)
        self.assertEqual(outcome, [True]); self.assertEqual(window.pending_bytes, 0)
        self.assertFalse(window.acknowledge(), "Extra ACKs cannot create new credits")

    def test_missing_ack_times_out_and_close_wakes_waiters(self):
        window = FrameWindow(timeout=.05); window.sent(10)
        with self.assertRaises(TimeoutError):
            window.wait(10, threading.Event())
        window = FrameWindow()
        for _ in range(8):
            window.sent(10)
        result = []
        thread = threading.Thread(target=lambda: result.append(window.wait(60, threading.Event())), daemon=True)
        thread.start(); time.sleep(.05); window.close(); thread.join(1)
        self.assertEqual(result, [False]); self.assertEqual(window.pending_bytes, 0)

    def test_capture_failure_releases_dxgi_and_uses_compatibility_path(self):
        capture = DesktopCapture(accelerated=False)
        class FailedCamera:
            released = False
            def grab(self, **kwargs):
                raise OSError("DXGI unavailable")
            def release(self):
                self.released = True
        camera = FailedCamera(); capture.camera = camera
        with patch("capture.ImageGrab.grab", return_value=Image.new("RGB", (320, 180), "green")):
            with capture.grab() as image:
                self.assertEqual(image.size, (320, 180))
        self.assertTrue(camera.released); self.assertIsNone(capture.camera)
        self.assertIn("compatibility", capture.backend)


if __name__ == "__main__":
    unittest.main()

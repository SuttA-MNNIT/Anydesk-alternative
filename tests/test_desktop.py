import io
import json
from pathlib import Path
import queue
import secrets
import sys
import threading
import time
import tkinter as tk
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image
from desktop.invitation import Invitation
from desktop.peer import NativePeer
from desktop.runtime import ManagedRuntime
from desktop.app import DesktopApp, DesktopWindow


class RecordedController:
    def __init__(self):
        self.events = []
    def handle(self, value):
        self.events.append(value)
    def release(self):
        self.events.append({"type": "release"})


class SyntheticCapture:
    backend = "synthetic test capture"
    count = 0
    def grab(self, **kwargs):
        type(self).count += 1
        return Image.new("RGB", (320, 180), "#315030")
    def close(self):
        pass


def wait_event(events, kind, timeout=5, acknowledge=False):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            category, value = events.get(timeout=.1)
        except queue.Empty:
            continue
        if category == "peer":
            peer, event, data = value
            if event == "frame" and acknowledge:
                peer.ack(data[0], data[1])
            if event == kind:
                return data
        elif category == kind:
            return value
        elif category == "runtime-error":
            raise AssertionError(value[1])
    raise AssertionError("Timed out waiting for " + kind)


class InvitationTests(unittest.TestCase):
    def test_roundtrip_and_reject_unsafe_or_malformed_invites(self):
        invite = Invitation("https://test.trycloudflare.com", "1234567890", "a" * 32)
        self.assertEqual(Invitation.decode(invite.encode()), invite)
        for value in ("", "CL3.bad", "https://example.com", "CL3." + "a" * 3000):
            with self.assertRaises(ValueError):
                Invitation.decode(value)
        for url in ("http://example.com", "https://user:pass@example.com", "https://example.com/path", "https://example.com?x=1", "file:///C:/test"):
            with self.assertRaises(ValueError):
                Invitation(url, "1234567890", "a" * 32).encode()


class NativeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.runtime_events = queue.Queue()
        self.runtime = ManagedRuntime(self.runtime_events)
        threading.Thread(target=self.runtime.start, kwargs={"tunnel": False}, daemon=True).start()
        wait_event(self.runtime_events, "runtime-ready", 20)
        self.host_events, self.viewer_events = queue.Queue(), queue.Queue()
        key = secrets.token_hex(16)
        self.hc, self.vc = RecordedController(), RecordedController()
        self.host = NativePeer(self.host_events, "host", "1234567890", key, "Host QA", self.hc, SyntheticCapture)
        self.viewer = NativePeer(self.viewer_events, "viewer", "1234567890", key, "Viewer QA", self.vc, SyntheticCapture)
        self.host.connect(self.runtime.url, self.runtime.token)
        wait_event(self.host_events, "online")
        self.viewer.connect(self.runtime.url)
        self.request = wait_event(self.host_events, "approval")

    def tearDown(self):
        self.viewer.stop(wait=True); self.host.stop(wait=True); self.runtime.stop()

    def approve(self, control=False):
        self.host.approve(self.request[0], True, control)
        wait_event(self.viewer_events, "viewing")

    def test_approval_view_only_control_revocation_and_frames(self):
        before = SyntheticCapture.count
        self.assertFalse(self.host.current.approved)
        self.viewer.input({"type": "key", "code": "KeyA", "down": True})
        time.sleep(.05)
        self.assertEqual(SyntheticCapture.count, before)
        self.assertFalse(any(e.get("type") == "key" for e in self.hc.events))
        self.approve(False)
        frame = wait_event(self.viewer_events, "frame", acknowledge=True)
        self.assertTrue(frame[2].startswith(b"\xff\xd8"))
        self.viewer.input({"type": "key", "code": "KeyA", "down": True})
        self.assertFalse(any(e.get("type") == "key" for e in self.hc.events))
        self.host.set_control(True); wait_event(self.viewer_events, "viewing", acknowledge=True)
        self.viewer.input({"type": "key", "code": "KeyA", "down": True})
        deadline = time.monotonic() + 2
        while not any(e.get("type") == "key" for e in self.hc.events) and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(any(e.get("code") == "KeyA" for e in self.hc.events))
        self.host.set_control(False); wait_event(self.viewer_events, "viewing", acknowledge=True)
        self.assertFalse(self.host.current.control); self.assertEqual(self.hc.events[-1]["type"], "release")

    def test_switch_direction_uses_same_relay_and_requires_both_sides(self):
        self.approve(True)
        wait_event(self.viewer_events, "frame", acknowledge=True)
        self.viewer.reverse(False)
        offer = wait_event(self.host_events, "reverse-offer")
        self.assertEqual(self.viewer.current.mode, "viewing")
        self.assertEqual(self.host.current.mode, "sharing")
        self.host.accept_reverse(*offer[:2], True, offer[2])
        wait_event(self.host_events, "viewing")
        wait_event(self.viewer_events, "sharing", acknowledge=True)
        frame = wait_event(self.host_events, "frame", acknowledge=True)
        self.assertTrue(frame[2].startswith(b"\xff\xd8"))
        self.assertEqual(self.viewer.current.mode, "sharing")
        self.assertEqual(self.host.current.mode, "viewing")
        self.assertFalse(self.host.current.control)
        # Reverse back, still on the original relay and with no new invitation.
        self.host.reverse(True)
        second = wait_event(self.viewer_events, "reverse-offer")
        self.viewer.accept_reverse(*second[:2], True, second[2])
        wait_event(self.viewer_events, "viewing", acknowledge=True)
        wait_event(self.host_events, "sharing", acknowledge=True)
        self.assertTrue(self.host.current.control)
        self.assertEqual(self.host.current.session_id, self.viewer.current.session_id)

    def test_declined_switch_and_old_stream_ack_cannot_credit_new_stream(self):
        self.approve(True)
        old = wait_event(self.viewer_events, "frame", acknowledge=True)
        self.viewer.reverse(True)
        offer = wait_event(self.host_events, "reverse-offer")
        self.host.accept_reverse(*offer[:2], False, offer[2])
        wait_event(self.viewer_events, "status", acknowledge=True)
        self.assertEqual(self.host.current.mode, "sharing")
        window = self.host.current.frames
        count = len(window.pending)
        self.host.command(self.host.current, {"type": "ack", "streamId": "f" * 16})
        self.assertEqual(len(window.pending), count)

    def test_decline_never_starts_screen_sharing(self):
        before = SyntheticCapture.count
        self.host.approve(self.request[0], False)
        wait_event(self.viewer_events, "ended")
        self.assertEqual(SyntheticCapture.count, before)
        self.assertIsNone(self.host.current)

    def test_owned_helpers_are_removed_on_stop(self):
        children = list(self.runtime.children)
        self.viewer.stop(wait=True); self.host.stop(wait=True); self.runtime.stop()
        self.assertTrue(all(child.poll() is not None for child in children))
        self.runtime.stop()  # Repeated stop must be safe.


class NativeGuiTests(unittest.TestCase):
    def test_offline_startup_and_native_jpeg_render_ack(self):
        root = tk.Tk(); root.withdraw()
        app = DesktopApp(root)
        self.assertIsNone(app.runtime); self.assertIsNone(app.peer)
        class Session:
            session_id = "test"
            stream_id = "1" * 16
            mode = "viewing"
            remote_name = "Synthetic desktop"
            control = False
            native = True
            reverse_out = None
        class Peer:
            current = Session()
            acknowledged = []
            def ack(self, *args):
                self.acknowledged.append(args)
            def input(self, value):
                pass
            def disconnect(self, message):
                raise AssertionError(message)
        peer = Peer()
        window = DesktopWindow(app, peer); window.root.withdraw()
        root.update_idletasks()
        image = Image.new("RGB", (320, 180), "green"); out = io.BytesIO(); image.save(out, format="JPEG")
        window.refresh(peer.current); window.frame("test", "1" * 16, out.getvalue())
        self.assertIsNotNone(window.photo)
        self.assertEqual(peer.acknowledged, [("test", "1" * 16)])
        window.close(); root.destroy()


if __name__ == "__main__":
    unittest.main()

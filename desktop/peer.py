"""Encrypted native host/viewer, including explicitly approved direction changes."""
import ctypes
import io
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit
from PIL import Image, ImageDraw
import websocket
from host.protocol import Channel
from host.capture import DesktopCapture
from host.streaming import FrameWindow
from host.native_input import Controller

PROFILES = {
    "Economy · 5 fps": (5, 1280, 50),
    "Balanced · 10 fps": (10, 1600, 65),
    "Sharper · 15 fps": (15, 1920, 78),
    "Smooth · 30 fps target": (30, 1600, 60),
    "Fast · 60 fps target": (60, 960, 50),
}


@dataclass
class Session:
    session_id: str
    channel: Channel
    authenticated: bool = False
    approved: bool = False
    mode: str = "pending"
    control: bool = False
    remote_name: str = "Remote computer"
    native: bool = False
    stopped: threading.Event = field(default_factory=threading.Event)
    stream_stop: threading.Event = field(default_factory=threading.Event)
    frames: FrameWindow = field(default_factory=FrameWindow)
    lock: threading.RLock = field(default_factory=threading.RLock)
    reverse_out: str | None = None
    reverse_control: bool = False
    reverse_in: str | None = None
    stream_id: str | None = None


class NativePeer:
    def __init__(self, events, role, device_id, key, name=None, controller=None, capture_factory=None):
        self.events, self.role, self.device_id, self.key = events, role, device_id, key
        self.name = name or os.environ.get("COMPUTERNAME", "Windows computer")
        self.controller = controller or Controller()
        self.capture_factory = capture_factory or DesktopCapture
        self.ws = None
        self.current = None
        self.profile = "Smooth · 30 fps target"
        self.closed = False
        self.send_lock = threading.RLock()
        self.network_thread = None

    def event(self, kind, data=None):
        self.events.put(("peer", (self, kind, data)))

    def connect(self, url, token=None):
        parsed = urlsplit(url)
        target = urlunsplit(("wss" if parsed.scheme == "https" else "ws", parsed.netloc, "/ws", "", ""))
        def opened(ws):
            ws.sock.settimeout(5)
            value = {"type": "register-host", "deviceId": self.device_id, "token": token} if self.role == "host" else {"type": "connect", "deviceId": self.device_id}
            ws.send(json.dumps(value))
        self.ws = websocket.WebSocketApp(target, on_open=opened, on_message=self.on_message, on_close=self.on_close,
                                         on_error=lambda *_: self.event("status", "Connection interrupted; check the other computer and Internet connection."))
        ws = self.ws
        self.network_thread = threading.Thread(target=lambda: ws.run_forever(suppress_origin=True, ping_interval=20, ping_timeout=10), daemon=True)
        self.network_thread.start()

    def plain(self, value):
        failed = False
        with self.send_lock:
            if self.ws and not self.closed:
                try:
                    self.ws.send(json.dumps(value))
                except (websocket.WebSocketException, OSError):
                    failed = True
        if failed:
            self.end_current(); self.event("offline", "The connection closed. Reconnect when the other computer is ready.")

    def secure(self, value=None, frame=None, session=None):
        session = session or self.current
        if session is None:
            return
        with session.lock, self.send_lock:
            if session is not self.current or session.stopped.is_set() or self.closed:
                return
            if frame is not None and (session.mode != "sharing" or session.stream_stop.is_set()):
                return
            data = session.channel.seal(2 if frame is not None else 1, frame if frame is not None else json.dumps(value).encode())
            try:
                self.ws.send(data, opcode=websocket.ABNF.OPCODE_BINARY)
            except (websocket.WebSocketException, OSError):
                self.end_current(); self.event("offline", "The connection closed. Reconnect when the other computer is ready.")

    def on_message(self, ws, data):
        if self.closed or ws is not self.ws:
            return
        try:
            if isinstance(data, str):
                message = json.loads(data)
                kind = message.get("type")
                if kind == "registered":
                    self.event("online")
                elif kind == "session":
                    self.end_current()
                    session = Session(message["sessionId"], Channel(self.key, message["sessionId"], self.role))
                    self.current = session
                    if self.role == "viewer":
                        self.secure({"type": "auth", "name": self.name, "control": True, "features": ["native-switch-v1"]})
                elif kind in ("error", "session-ended"):
                    self.end_current(); self.event("ended", message.get("message") or message.get("reason") or "Session ended.")
                return
            session = self.current
            if session is None:
                return
            kind, payload = session.channel.open(data)
            if kind == 2:
                if not session.approved or session.mode != "viewing":
                    return
                self.event("frame", (session.session_id, session.stream_id, payload))
                return
            if kind != 1 or len(payload) > 8192:
                raise ValueError("Invalid command")
            message = json.loads(payload)
            if not isinstance(message, dict):
                raise ValueError("Invalid command")
            command = message.get("type")
            if command == "auth" and self.role == "host" and not session.authenticated:
                if not isinstance(message.get("name"), str) or type(message.get("control")) is not bool:
                    raise ValueError("Invalid authentication")
                session.authenticated = True
                session.remote_name = "".join(c for c in message["name"] if c.isprintable())[:60] or "Guest"
                session.native = "native-switch-v1" in message.get("features", [])
                self.event("approval", (session.session_id, session.remote_name, message["control"]))
            elif command == "approved" and self.role == "viewer" and not session.approved:
                session.authenticated = session.approved = True
                session.mode, session.control = "viewing", message.get("control") is True
                session.remote_name = str(message.get("name", "Remote computer"))[:80]
                session.native = "native-switch-v1" in message.get("features", [])
                if session.native:
                    self.secure({"type": "quality", "profile": self.profile})
                self.event("viewing", session)
            elif command in ("denied", "error"):
                self.disconnect("The other computer declined or ended the session.")
            elif session.approved:
                self.command(session, message)
        except Exception:
            self.disconnect("Session authentication failed or an invalid packet was rejected.")

    def command(self, session, message):
        command = message.get("type")
        with session.lock:
            if session.stopped.is_set():
                return
            if command == "ack" and session.mode == "sharing":
                if not session.native or message.get("streamId") == session.stream_id:
                    session.frames.acknowledge()
            elif command == "stream" and session.mode == "viewing":
                stream_id = message.get("streamId", "")
                if not isinstance(stream_id, str) or not re.fullmatch(r"[a-f0-9]{16}", stream_id):
                    raise ValueError("Invalid stream identity")
                session.stream_id = stream_id
            elif command in ("move", "button", "wheel", "key", "release") and session.mode == "sharing" and session.control:
                try:
                    self.controller.handle(message)
                except OSError:
                    self.set_control(False)
                    self.event("status", "Windows blocked input. Sharing continues in view-only mode.")
            elif command == "control" and session.mode == "viewing":
                session.control = message.get("enabled") is True; self.event("viewing", session)
            elif command == "request-control" and session.mode == "sharing" and not session.control:
                self.event("control-request", (session.session_id, session.remote_name))
            elif command == "quality" and message.get("profile") in PROFILES:
                self.profile = message["profile"]
            elif command == "reverse-request" and session.native and session.mode == "sharing":
                request_id = message.get("requestId", "")
                if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id) or session.reverse_in:
                    raise ValueError("Invalid direction request")
                session.reverse_in = request_id
                self.event("reverse-offer", (session.session_id, request_id, message.get("control") is True))
            elif command == "reverse-accepted" and session.mode == "viewing":
                if not session.reverse_out or message.get("requestId") != session.reverse_out:
                    raise ValueError("Direction switch has no local approval")
                session.reverse_out = None
                self.start_sharing(session, session.reverse_control)
            elif command == "reverse-denied" and message.get("requestId") == session.reverse_out:
                session.reverse_out = None; self.event("status", "The direction switch was declined or timed out.")

    def approve(self, session_id, allow, control=False):
        session = self.current
        if not session or session.session_id != session_id or session.approved or not session.authenticated:
            return
        if not allow:
            self.secure({"type": "denied"}); self.disconnect("Connection declined."); return
        self.plain({"type": "ready"})
        session.approved = True
        self.secure({"type": "approved", "control": control, "name": self.name, "features": ["native-switch-v1"]})
        self.start_sharing(session, control)

    def start_sharing(self, session, control):
        with session.lock:
            if session is not self.current or session.stopped.is_set():
                return
            session.mode, session.control = "sharing", control
            session.stream_stop = threading.Event(); session.frames = FrameWindow()
            session.stream_id = secrets.token_hex(8)
            stream_stop, frames = session.stream_stop, session.frames
            if session.native:
                self.secure({"type": "stream", "streamId": session.stream_id})
        self.event("sharing", session)
        threading.Thread(target=self.stream, args=(session, stream_stop, frames), daemon=True).start()

    def stream(self, session, stream_stop, frames):
        capture = None
        try:
            capture = self.capture_factory()
            self.event("capture", capture.backend)
            while session is self.current and not session.stopped.is_set() and not stream_stop.is_set():
                fps, width, quality = PROFILES[self.profile]
                if not frames.wait(fps, stream_stop):
                    break
                started = time.monotonic()
                with capture.grab(max_width=width, fast=fps >= 30) as image:
                    # Cursor is rendered in captured-image coordinates, including decimation.
                    point = ctypes.wintypes.POINT()
                    primary_w, primary_h = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
                    if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)) and 0 <= point.x < primary_w and 0 <= point.y < primary_h:
                        x, y = round(point.x * image.width / primary_w), round(point.y * image.height / primary_h)
                        ImageDraw.Draw(image).polygon([(x, y), (x + 3, y + 17), (x + 8, y + 11), (x + 15, y + 10)], fill="white", outline="black")
                    image.thumbnail((width, width), Image.Resampling.NEAREST if fps >= 30 else Image.Resampling.BILINEAR)
                    output = io.BytesIO(); image.save(output, format="JPEG", quality=quality); jpeg = output.getvalue()
                if not frames.wait(fps, stream_stop, len(jpeg)) or not frames.sent(len(jpeg)):
                    break
                self.secure(frame=jpeg, session=session)
                stream_stop.wait(max(0, 1 / fps - (time.monotonic() - started)))
        except Exception:
            if session is self.current and not stream_stop.is_set() and not session.stopped.is_set():
                self.disconnect("Screen capture stopped. Check that Windows is awake and unlocked.")
        finally:
            if capture:
                capture.close()

    def set_control(self, enabled):
        session = self.current
        if not session or not session.approved or session.mode != "sharing":
            return
        with session.lock:
            session.control = bool(enabled)
            if not enabled:
                self.controller.release()
            self.secure({"type": "control", "enabled": session.control})
        self.event("sharing", session)

    def reverse(self, allow_control):
        # Called only by the local Share my screen action, after a local confirmation.
        session = self.current
        if not session or not session.approved or not session.native or session.mode != "viewing" or session.reverse_out:
            return
        request_id = secrets.token_hex(16)
        session.reverse_out, session.reverse_control = request_id, bool(allow_control)
        self.secure({"type": "release"})
        self.secure({"type": "reverse-request", "requestId": request_id, "control": bool(allow_control)})
        def expire():
            if session is self.current and session.reverse_out == request_id:
                session.reverse_out = None; self.event("status", "Direction switch timed out; your screen was not shared.")
        timer = threading.Timer(30, expire); timer.daemon = True; timer.start()

    def accept_reverse(self, session_id, request_id, allow, control):
        session = self.current
        if not session or session.session_id != session_id or session.reverse_in != request_id or session.mode != "sharing":
            return
        with session.lock:
            session.reverse_in = None
            if not allow:
                self.secure({"type": "reverse-denied", "requestId": request_id}); return
            session.stream_stop.set(); session.frames.close(); self.controller.release()
            session.mode, session.control = "viewing", control
            if self.role == "host":
                self.plain({"type": "allow-reverse"})
            self.secure({"type": "reverse-accepted", "requestId": request_id})
        self.event("viewing", session)

    def ack(self, session_id, stream_id=None):
        session = self.current
        if session and session.session_id == session_id and session.mode == "viewing" and session.approved and stream_id == session.stream_id:
            self.secure({"type": "ack", "streamId": stream_id})

    def input(self, value):
        session = self.current
        if session and session.approved and session.mode == "viewing" and session.control:
            self.secure(value)

    def end_current(self):
        session, self.current = self.current, None
        if session:
            with session.lock:
                session.stopped.set(); session.stream_stop.set(); session.frames.close(); session.control = False
                self.controller.release()

    def disconnect(self, reason="Disconnected."):
        self.end_current()
        try:
            self.plain({"type": "end"})
        except Exception:
            pass
        self.event("ended", reason)

    def on_close(self, ws, *_):
        if not self.closed and ws is self.ws:
            self.end_current(); self.event("offline", "The connection closed. Start sharing or reconnect again.")

    def stop(self, wait=False):
        self.closed = True; self.end_current()
        if self.ws:
            ws, self.ws = self.ws, None
            def close():
                ws.close(timeout=1)
                if self.network_thread and self.network_thread is not threading.current_thread():
                    self.network_thread.join(timeout=3)
            if wait:
                close()
            else:
                threading.Thread(target=close, daemon=True).start()

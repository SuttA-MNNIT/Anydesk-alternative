"""CampusLink attended Windows host. Starts only when the user clicks Go online."""
import ctypes
import io
import json
import os
import queue
import secrets
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageDraw
import websocket
from protocol import Channel
from native_input import Controller
from capture import DesktopCapture
from streaming import FrameWindow

ROOT = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
CONFIG_ROOT = Path(os.environ.get("CAMPUSLINK_CONFIG_DIR", ROOT / "config"))
BG, PANEL, TEXT, MUTED, ACCENT = "#101515", "#192121", "#ecf4ed", "#91a4a0", "#c4f277"
PRESETS = {
    "Economy · 5 fps / 1280 px": (5, 1280, 50),
    "Balanced · 10 fps / 1600 px": (10, 1600, 65),
    "Sharper · 15 fps / 1920 px": (15, 1920, 78),
    "Smooth · 30 fps target / 1600 px": (30, 1600, 60),
    "Fast · 60 fps target / 960 px": (60, 960, 50),
}


def server_url(value):
    parsed = urlsplit(value.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Enter a relay URL such as https://desk.example.edu (no path or credentials).")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Outside localhost, the relay must use HTTPS.")
    return urlunsplit(("wss" if parsed.scheme == "https" else "ws", parsed.netloc, "/ws", "", ""))


@dataclass
class RemoteSession:
    session_id: str
    channel: Channel
    authenticated: bool = False
    approved: bool = False
    control: bool = False
    stopped: threading.Event = field(default_factory=threading.Event)
    frames: FrameWindow = field(default_factory=FrameWindow)
    guard: threading.RLock = field(default_factory=threading.RLock)


class HostApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CampusLink — High FPS Host")
        self.root.geometry("690x900")
        self.root.minsize(650, 860)
        self.root.configure(bg=BG)
        self.events = queue.Queue()
        self.ws = None
        self.current = None
        self.controller = Controller()
        self.running = False
        self.prompt = None
        self.device_id = "".join(secrets.choice("0123456789") for _ in range(10))
        self.access_key = secrets.token_hex(16)
        self.url_var = tk.StringVar(value="http://localhost:8787")
        self.token_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Offline — your screen is private")
        self.id_var = tk.StringVar(value=f"{self.device_id[:3]} {self.device_id[3:6]} {self.device_id[6:]}")
        self.secret_var = tk.StringVar(value=self.access_key)
        self.control_var = tk.BooleanVar(value=False)
        self.quality_var = tk.StringVar(value="Smooth · 30 fps target / 1600 px")
        self.settings = PRESETS[self.quality_var.get()]
        self.load_config()
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(75, self.poll)

    def load_config(self):
        for location in (CONFIG_ROOT / "host.json", CONFIG_ROOT / "relay.json"):
            try:
                config = json.loads(location.read_text(encoding="utf-8"))
                self.token_var.set(config.get("enrollmentToken", ""))
                self.url_var.set(config.get("serverUrl", "http://localhost:8787"))
                return
            except (OSError, ValueError):
                pass

    def build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=BG, background=PANEL, foreground=TEXT, arrowcolor=ACCENT)
        outer = tk.Frame(self.root, bg=BG, padx=32, pady=25)
        outer.pack(fill="both", expand=True)
        top = tk.Frame(outer, bg=BG); top.pack(fill="x")
        tk.Label(top, text="C", bg=ACCENT, fg=BG, font=("Segoe UI", 21, "bold"), width=2).pack(side="left", padx=(0, 12))
        tk.Label(top, text="CampusLink", bg=BG, fg=TEXT, font=("Segoe UI", 22, "bold")).pack(side="left")
        tk.Label(top, text="WINDOWS HOST", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="right")
        tk.Label(outer, text="Your desktop, within reach.", bg=BG, fg=TEXT, font=("Segoe UI", 22)).pack(anchor="w", pady=(25, 4))
        tk.Label(outer, text="Each connection needs your approval. Closing this app ends access.", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")
        card = tk.Frame(outer, bg=PANEL, padx=20, pady=15); card.pack(fill="x", pady=20)
        tk.Label(card, text="THIS DESKTOP", bg=PANEL, fg=ACCENT, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        id_row = tk.Frame(card, bg=PANEL); id_row.pack(fill="x", pady=(2, 7))
        tk.Label(id_row, textvariable=self.id_var, bg=PANEL, fg=TEXT, font=("Consolas", 27)).pack(side="left")
        self.button(id_row, "Copy ID", lambda: self.copy(self.device_id), quiet=True).pack(side="right")
        tk.Label(card, text="ACCESS KEY — share privately with your viewer", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        key_row = tk.Frame(card, bg=PANEL); key_row.pack(fill="x", pady=(5, 0))
        key_entry = tk.Entry(key_row, textvariable=self.secret_var, font=("Consolas", 11), readonlybackground=PANEL, fg=TEXT, relief="flat", state="readonly", width=34)
        key_entry.pack(side="left", fill="x", expand=True)
        self.button(key_row, "Copy key", lambda: self.copy(self.access_key), quiet=True).pack(side="right")
        self.label(outer, "Office relay URL")
        self.url_entry = self.entry(outer, self.url_var)
        self.label(outer, "Host enrollment token · supplied by your relay administrator")
        self.token_entry = self.entry(outer, self.token_var, show="•")
        self.label(outer, "Screen quality · target FPS depends on hardware and network")
        quality = ttk.Combobox(outer, textvariable=self.quality_var, state="readonly", values=list(PRESETS))
        quality.pack(fill="x", ipady=5)
        quality.bind("<<ComboboxSelected>>", lambda _: self.update_quality())
        self.control_check = tk.Checkbutton(outer, text="Allow keyboard and mouse for the current approved session", variable=self.control_var, command=self.toggle_control, bg=BG, fg=TEXT, activebackground=BG, activeforeground=TEXT, selectcolor=PANEL, font=("Segoe UI", 10))
        self.control_check.pack(anchor="w", pady=(16, 8))
        buttons = tk.Frame(outer, bg=BG); buttons.pack(fill="x", pady=(4, 8))
        self.online_button = self.button(buttons, "Go online", self.start); self.online_button.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.stop_button = self.button(buttons, "Stop / disconnect", self.stop, quiet=True); self.stop_button.pack(side="left", fill="x", expand=True)
        tk.Label(outer, textvariable=self.status_var, bg=BG, fg=ACCENT, font=("Segoe UI", 10), wraplength=590, justify="left").pack(anchor="w", pady=(7, 4))
        self.log_box = tk.Text(outer, height=4, bg=PANEL, fg=MUTED, font=("Consolas", 9), relief="flat", padx=10, pady=7, state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, pady=(5, 0))

    def label(self, parent, text):
        tk.Label(parent, text=text, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(11, 5))

    def entry(self, parent, variable, **kwargs):
        entry = tk.Entry(parent, textvariable=variable, bg=PANEL, fg=TEXT, insertbackground=ACCENT, relief="flat", font=("Segoe UI", 11), **kwargs)
        entry.pack(fill="x", ipady=8)
        return entry

    def button(self, parent, text, command, quiet=False):
        return tk.Button(parent, text=text, command=command, bg=PANEL if quiet else ACCENT, fg=TEXT if quiet else BG, activebackground="#a9d56a", activeforeground=BG, relief="flat", padx=14, pady=8, font=("Segoe UI", 10, "bold"), cursor="hand2")

    def copy(self, value):
        self.root.clipboard_clear(); self.root.clipboard_append(value)

    def log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", time.strftime("%H:%M:%S ") + text + "\n")
        self.log_box.see("end"); self.log_box.configure(state="disabled")

    def update_quality(self):
        self.settings = PRESETS.get(self.quality_var.get(), (30, 1600, 60))

    def start(self):
        if self.running:
            return
        try:
            url = server_url(self.url_var.get())
            token = self.token_var.get().strip()
            if len(token) < 32 or len(token) > 256:
                raise ValueError("Paste the host enrollment token from config/relay.json.")
        except ValueError as exc:
            messagebox.showerror("Relay settings", str(exc)); return
        self.running = True
        self.online_button.configure(state="disabled")
        self.url_entry.configure(state="disabled"); self.token_entry.configure(state="disabled")
        self.status_var.set("Connecting to office relay…")
        ws = websocket.WebSocketApp(url, on_open=lambda socket: socket.send(json.dumps({"type": "register-host", "deviceId": self.device_id, "token": token})), on_message=self.on_message, on_error=lambda _, error: self.events.put(("log", f"Relay error: {type(error).__name__}. Check the URL, token and connection.")), on_close=lambda socket, code, reason: self.on_close(socket, reason))
        self.ws = ws
        threading.Thread(target=lambda: ws.run_forever(suppress_origin=True, ping_interval=20, ping_timeout=10), daemon=True).start()

    def send_json(self, msg):
        if self.ws:
            self.ws.send(json.dumps(msg))

    def send_secure(self, session, msg=None, frame=None):
        with session.channel.lock:
            if session is not self.current or session.stopped.is_set() or not self.ws:
                return
            packet = session.channel.seal(2 if frame is not None else 1, frame if frame is not None else json.dumps(msg).encode())
            self.ws.send(packet, opcode=websocket.ABNF.OPCODE_BINARY)

    def on_close(self, ws, reason):
        if self.ws is ws:
            self.end_current()
            self.events.put(("offline", reason or "Relay disconnected. Click Go online to reconnect."))

    def on_message(self, ws, data):
        if ws is not self.ws:
            return
        try:
            if isinstance(data, str):
                msg = json.loads(data)
                if msg.get("type") == "registered":
                    self.events.put(("status", "Online — waiting for an approved connection"))
                    self.events.put(("log", "Registered with office relay. No screen is being shared."))
                elif msg.get("type") == "session":
                    self.end_current()
                    self.current = RemoteSession(msg["sessionId"], Channel(self.access_key, msg["sessionId"]))
                elif msg.get("type") == "session-ended":
                    self.end_current()
                    self.events.put(("status", "Online — session ended, screen sharing stopped"))
                    self.events.put(("dismiss", None))
            else:
                session = self.current
                if not session or session.stopped.is_set():
                    return
                kind, payload = session.channel.open(data)
                if kind != 1 or len(payload) > 8192:
                    raise ValueError("Invalid control packet")
                msg = json.loads(payload)
                if not isinstance(msg, dict):
                    raise ValueError("Invalid command")
                if not session.authenticated:
                    if msg.get("type") != "auth" or not isinstance(msg.get("name"), str) or type(msg.get("control")) is not bool:
                        raise ValueError("Authentication required")
                    session.authenticated = True
                    name = "".join(c for c in msg["name"] if c.isprintable())[:60] or "Guest"
                    self.events.put(("approve", (session, name, msg["control"])))
                elif session.approved:
                    with session.guard:
                        if session.stopped.is_set():
                            return
                        if msg.get("type") == "ack":
                            session.frames.acknowledge()
                        elif session.control:
                            try:
                                self.controller.handle(msg)
                            except OSError:
                                session.control = False
                                self.controller.release()
                                self.send_secure(session, {"type": "control", "enabled": False})
                                self.events.put(("input-blocked", None))
        except Exception:
            self.events.put(("log", "Rejected an invalid or unauthenticated session packet."))
            self.end_session()

    def approval(self, session, name, requested_control):
        if session is not self.current or session.stopped.is_set():
            return
        prompt = tk.Toplevel(self.root); self.prompt = prompt
        prompt.title("CampusLink — connection request")
        prompt.configure(bg=BG); prompt.geometry("480x300"); prompt.resizable(False, False)
        prompt.transient(self.root); prompt.attributes("-topmost", True)
        frame = tk.Frame(prompt, bg=BG, padx=26, pady=23); frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Allow this connection?", bg=BG, fg=TEXT, font=("Segoe UI", 20)).pack(anchor="w")
        tk.Label(frame, text=f"{name} knows the access key and requests\n{'keyboard and mouse control' if requested_control else 'view-only access'}.", bg=BG, fg=MUTED, font=("Segoe UI", 11), justify="left", wraplength=420).pack(anchor="w", pady=16)
        tk.Label(frame, text="Your primary screen will be visible until you disconnect.\nThis request expires after 40 seconds.", bg=BG, fg=MUTED, font=("Segoe UI", 10), justify="left").pack(anchor="w", pady=(0, 15))

        def decide(allow, control=False):
            if prompt.winfo_exists():
                prompt.destroy()
            self.prompt = None
            if session is not self.current or session.stopped.is_set():
                return
            if not allow:
                self.send_secure(session, {"type": "denied"}); self.end_session(); return
            self.begin_approved_session(session, name, control)

        row = tk.Frame(frame, bg=BG); row.pack(fill="x")
        self.button(row, "Decline", lambda: decide(False), quiet=True).pack(side="left")
        self.button(row, "View only", lambda: decide(True)).pack(side="right", padx=(6, 0))
        if requested_control:
            self.button(row, "Allow control", lambda: decide(True, True)).pack(side="right", padx=(6, 0))
        prompt.protocol("WM_DELETE_WINDOW", lambda: decide(False))
        prompt.after(40_000, lambda: decide(False) if prompt.winfo_exists() else None)
        prompt.lift(); prompt.focus_force(); self.root.bell()

    def begin_approved_session(self, session, name, control):
        if session is not self.current or session.stopped.is_set() or not session.authenticated:
            return
        with session.guard:
            session.control = control; session.approved = True
        self.control_var.set(control)
        self.send_json({"type": "ready"})
        self.send_secure(session, {"type": "approved", "control": control, "name": os.environ.get("COMPUTERNAME", "Windows desktop")})
        self.status_var.set(f"Sharing primary screen with {name} — {'REMOTE CONTROL' if control else 'VIEW ONLY'}")
        self.log("Screen sharing started after local approval.")
        threading.Thread(target=self.stream, args=(session,), daemon=True).start()

    def stream(self, session):
        capture = None
        try:
            capture = DesktopCapture()
            self.events.put(("log", capture.backend + ". Frame rate shown in the viewer is measured, not the selected target."))
            while session is self.current and not session.stopped.is_set():
                fps, max_width, quality = self.settings
                if not session.frames.wait(fps, session.stopped):
                    break
                started = time.monotonic()
                with capture.grab(max_width=max_width, fast=fps >= 30) as image:
                    width, height = image.size
                    # Include a small pointer marker; the Windows GDI capture omits the cursor.
                    point = ctypes.wintypes.POINT()
                    primary_width = ctypes.windll.user32.GetSystemMetrics(0)
                    primary_height = ctypes.windll.user32.GetSystemMetrics(1)
                    if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)) and 0 <= point.x < primary_width and 0 <= point.y < primary_height:
                        point.x = round(point.x * width / primary_width)
                        point.y = round(point.y * height / primary_height)
                        draw = ImageDraw.Draw(image)
                        draw.polygon([(point.x, point.y), (point.x + 3, point.y + 17), (point.x + 8, point.y + 11), (point.x + 15, point.y + 10)], fill="white", outline="black")
                    image.thumbnail((max_width, max_width), Image.Resampling.NEAREST if fps >= 30 else Image.Resampling.BILINEAR)
                    output = io.BytesIO(); image.save(output, format="JPEG", quality=quality)
                    jpeg = output.getvalue()
                    if not session.frames.wait(fps, session.stopped, len(jpeg)):
                        break
                    if not session.frames.sent(len(jpeg)):
                        break
                    self.send_secure(session, frame=jpeg)
                session.stopped.wait(max(0, 1 / fps - (time.monotonic() - started)))
        except Exception:
            if not session.stopped.is_set():
                self.events.put(("log", "Screen stream stopped. The viewer may be disconnected or Windows may be locked."))
                if session is self.current:
                    self.end_session()
        finally:
            if capture is not None:
                capture.close()

    def toggle_control(self):
        session = self.current
        if not session or not session.approved:
            self.control_var.set(False); return
        with session.guard:
            session.control = self.control_var.get()
            if not session.control:
                self.controller.release()
            self.send_secure(session, {"type": "control", "enabled": session.control})
        self.status_var.set("Sharing primary screen — " + ("REMOTE CONTROL" if session.control else "VIEW ONLY"))

    def end_current(self):
        session = self.current
        self.current = None
        if session:
            with session.guard:
                session.stopped.set(); session.frames.close(); session.control = False
                self.controller.release()

    def end_session(self):
        self.end_current()
        try:
            self.send_json({"type": "end"})
        except Exception:
            pass
        self.events.put(("dismiss", None))

    def stop(self):
        self.end_session()
        ws = self.ws; self.ws = None
        if ws:
            threading.Thread(target=ws.close, daemon=True).start()
        self.set_offline("Offline — your screen is private")

    def set_offline(self, text):
        self.running = False; self.control_var.set(False)
        self.status_var.set(text)
        self.online_button.configure(state="normal")
        self.url_entry.configure(state="normal"); self.token_entry.configure(state="normal")

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "log":
                    self.log(data)
                elif kind == "status":
                    self.status_var.set(data)
                elif kind == "offline":
                    self.set_offline(data)
                elif kind == "approve":
                    self.approval(*data)
                elif kind == "input-blocked":
                    self.control_var.set(False)
                    self.status_var.set("Sharing screen — view only (Windows blocked input)")
                elif kind == "dismiss":
                    self.control_var.set(False)
                    if self.prompt and self.prompt.winfo_exists():
                        self.prompt.destroy()
                    self.prompt = None
        except queue.Empty:
            pass
        self.root.after(75, self.poll)

    def close(self):
        self.stop(); self.root.destroy()


def main():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    root = tk.Tk()
    if len(sys.argv) == 3 and sys.argv[1] == "--check-installation":
        root.withdraw()
        instance = HostApp(root)
        root.update_idletasks()
        from native_input import INPUT
        result = {"status": "ok", "frozen": bool(getattr(sys, "frozen", False)), "offline": not instance.running and instance.ws is None,
                  "uiRequestedSize": [root.winfo_reqwidth(), root.winfo_reqheight()], "nativeInputSize": ctypes.sizeof(INPUT),
                  "primaryScreen": [ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)]}
        capture = DesktopCapture()
        try:
            with capture.grab() as frame:
                result["captureDimensions"] = list(frame.size)
            result["captureBackend"] = capture.backend
        finally:
            capture.close()
        root.destroy()
        Path(sys.argv[2]).write_text(json.dumps(result, indent=2), encoding="utf-8")
        return
    HostApp(root); root.mainloop()


if __name__ == "__main__":
    main()

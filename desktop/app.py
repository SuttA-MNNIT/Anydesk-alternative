"""One executable: managed office relay, attended sharing and a native Windows viewer."""
import ctypes
import io
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from desktop.invitation import Invitation
from desktop.peer import NativePeer, PROFILES
from desktop.runtime import ManagedRuntime, ASSETS, NO_WINDOW, node_path, identity
from host.native_input import KEYS

BG, PANEL, TEXT, MUTED, GREEN = "#101515", "#1b2521", "#edf4ed", "#91a79a", "#c4f277"
VK_CODES = {}
for code, vk in KEYS.items():
    VK_CODES.setdefault(vk, code)
VK_CODES[27] = "Escape"


def label(parent, text="", **kwargs):
    return tk.Label(parent, text=text, bg=kwargs.pop("bg", BG), fg=kwargs.pop("fg", TEXT), font=kwargs.pop("font", ("Segoe UI", 10)), **kwargs)


def button(parent, text, command, secondary=False):
    return tk.Button(parent, text=text, command=command, bg=PANEL if secondary else GREEN, fg=TEXT if secondary else BG,
                     activebackground="#a9d868", activeforeground=BG, relief="flat", padx=16, pady=10, font=("Segoe UI", 10, "bold"), cursor="hand2")


class DesktopWindow:
    def __init__(self, app, peer):
        self.app, self.peer = app, peer
        self.root = tk.Toplevel(app.root)
        self.root.title("CampusLink — Remote desktop")
        self.root.geometry("1100x760"); self.root.minsize(720, 450); self.root.configure(bg=BG)
        toolbar = tk.Frame(self.root, bg=BG, padx=12, pady=9); toolbar.pack(fill="x")
        self.title = tk.StringVar(value="Connecting…")
        self.stats = tk.StringVar(value="Waiting for the first frame…")
        label(toolbar, textvariable=self.title, font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 14))
        button(toolbar, "Disconnect", app.disconnect, True).pack(side="right", padx=4)
        button(toolbar, "Full screen", self.fullscreen, True).pack(side="right", padx=4)
        self.reverse_button = button(toolbar, "Share my screen instead", self.reverse, True); self.reverse_button.pack(side="right", padx=4)
        self.control_button = button(toolbar, "Request control", self.request_control, True); self.control_button.pack(side="right", padx=4)
        self.canvas = tk.Canvas(self.root, background="#080c0a", highlightthickness=0, takefocus=True)
        self.canvas.pack(fill="both", expand=True)
        footer = tk.Frame(self.root, bg=BG, padx=12, pady=8); footer.pack(fill="x")
        label(footer, textvariable=self.stats, fg=MUTED, font=("Consolas", 9)).pack(side="left")
        label(footer, text="F11: full screen · click the image to control", fg=MUTED, font=("Segoe UI", 9)).pack(side="right")
        self.photo = None; self.image_item = None; self.rect = (0, 0, 1, 1)
        self.count = self.bytes = 0; self.since = time.monotonic(); self.last_move = 0
        self.root.protocol("WM_DELETE_WINDOW", app.disconnect)
        self.canvas.bind("<Motion>", self.motion)
        for number in (1, 2, 3):
            self.canvas.bind(f"<ButtonPress-{number}>", lambda event, n=number: self.mouse(event, n, True))
            self.canvas.bind(f"<ButtonRelease-{number}>", lambda event, n=number: self.mouse(event, n, False))
        self.canvas.bind("<MouseWheel>", lambda e: self.peer.input({"type": "wheel", "delta": max(-1200, min(1200, int(e.delta)))}))
        self.canvas.bind("<KeyPress>", lambda e: self.key(e, True))
        self.canvas.bind("<KeyRelease>", lambda e: self.key(e, False))
        self.canvas.bind("<FocusOut>", lambda _: self.peer.input({"type": "release"}))
        self.canvas.focus_set()

    def refresh(self, session):
        self.title.set(session.remote_name + (" · Control" if session.control else " · View only"))
        self.reverse_button.configure(state="normal" if session.native and not session.reverse_out else "disabled")
        self.control_button.configure(state="disabled" if session.control or not session.native else "normal")

    def frame(self, session_id, stream_id, jpeg):
        session = self.peer.current
        if not session or session.session_id != session_id or session.mode != "viewing" or session.stream_id != stream_id:
            return
        try:
            with Image.open(io.BytesIO(jpeg)) as original:
                if original.width * original.height > 16_777_216:
                    raise ValueError("Screen image exceeds the supported size")
                image = original.convert("RGB")
            source_size = image.size
            width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
            scale = min(width / image.width, height / image.height)
            draw_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            if draw_size != image.size:
                image = image.resize(draw_size, Image.Resampling.NEAREST)
            left, top = (width - draw_size[0]) // 2, (height - draw_size[1]) // 2
            self.rect = (left, top, *draw_size)
            if self.photo is None or self.photo.width() != draw_size[0] or self.photo.height() != draw_size[1]:
                self.photo = ImageTk.PhotoImage(image)
                if self.image_item is None:
                    self.image_item = self.canvas.create_image(left, top, image=self.photo, anchor="nw")
                else:
                    self.canvas.itemconfigure(self.image_item, image=self.photo)
            else:
                self.photo.paste(image)
            self.canvas.coords(self.image_item, left, top)
            self.count += 1; self.bytes += len(jpeg)
            elapsed = time.monotonic() - self.since
            if elapsed >= 1:
                self.stats.set(f"{source_size[0]} × {source_size[1]}   {self.count / elapsed:.0f} fps   {self.bytes * 8 / elapsed / 1e6:.1f} Mbps   encrypted")
                self.count = self.bytes = 0; self.since = time.monotonic()
            self.peer.ack(session_id, stream_id)
        except Exception:
            self.peer.disconnect("Unable to decode the remote screen.")

    def coordinates(self, event):
        left, top, width, height = self.rect
        return {"x": max(0, min(1, (event.x - left) / width)), "y": max(0, min(1, (event.y - top) / height))}

    def motion(self, event):
        if time.monotonic() - self.last_move >= .016:
            self.last_move = time.monotonic(); self.peer.input({"type": "move", **self.coordinates(event)})

    def mouse(self, event, number, down):
        self.canvas.focus_set()
        left, top, width, height = self.rect
        if down and not (left <= event.x <= left + width and top <= event.y <= top + height):
            return
        self.peer.input({"type": "button", "button": {1: 0, 2: 1, 3: 2}[number], "down": down, **self.coordinates(event)})

    def key(self, event, down):
        if event.keysym == "F11":
            if down:
                self.fullscreen()
            return "break"
        if event.keysym == "Escape" and self.root.attributes("-fullscreen"):
            if down:
                self.root.attributes("-fullscreen", False); self.peer.input({"type": "release"})
            return "break"
        special = {"Shift_L": "ShiftLeft", "Shift_R": "ShiftRight", "Control_L": "ControlLeft", "Control_R": "ControlRight", "Alt_L": "AltLeft", "Alt_R": "AltRight", "KP_Enter": "NumpadEnter"}
        code = special.get(event.keysym) or VK_CODES.get(event.keycode)
        if code:
            self.peer.input({"type": "key", "code": code, "down": down})
        return "break"

    def fullscreen(self):
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))

    def reverse(self):
        self.app.ask("Share your screen instead?", "The other computer will see your primary screen. Choose the permission you want to grant.",
                     [("Cancel", lambda: None), ("View only", lambda: self.peer.reverse(False)), ("Allow control", lambda: self.peer.reverse(True))])

    def request_control(self):
        self.peer.secure({"type": "request-control"})
        self.app.status.set("Asked the other computer to allow keyboard and mouse control.")

    def close(self):
        if self.root.winfo_exists():
            self.root.destroy()


class DesktopApp:
    def __init__(self, root):
        self.root = root
        root.title("CampusLink — Share & Connect")
        root.geometry("970x850"); root.minsize(850, 800); root.configure(bg=BG)
        self.events = queue.Queue()
        self.runtime = self.peer = self.viewer = self.prompt = None
        self.invitation = None
        self.device_id = identity()
        self.status = tk.StringVar(value="Ready. Choose Share this computer or enter a connection code.")
        self.profile = tk.StringVar(value="Smooth · 30 fps target")
        self.control = tk.BooleanVar(value=False)
        self.build_ui()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(8, self.poll)

    def build_ui(self):
        style = ttk.Style(); style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=TEXT, arrowcolor=GREEN)
        outer = tk.Frame(self.root, bg=BG, padx=28, pady=24); outer.pack(fill="both", expand=True)
        heading = tk.Frame(outer, bg=BG); heading.pack(fill="x")
        label(heading, " C ", bg=GREEN, fg=BG, font=("Segoe UI", 24, "bold")).pack(side="left", padx=(0, 12))
        label(heading, "CampusLink", font=("Segoe UI", 25, "bold")).pack(side="left")
        label(heading, "DESKTOP 0.3", fg=MUTED).pack(side="right")
        label(outer, "Your computers. One app.", font=("Segoe UI", 23)).pack(anchor="w", pady=(20, 3))
        label(outer, "Share and connect directly in this app. No browser or command windows.", fg=MUTED).pack(anchor="w")
        panels = tk.Frame(outer, bg=BG); panels.pack(fill="x", pady=22)
        panels.columnconfigure(0, weight=1); panels.columnconfigure(1, weight=1)
        share = tk.Frame(panels, bg=PANEL, padx=20, pady=18); share.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        connect = tk.Frame(panels, bg=PANEL, padx=20, pady=18); connect.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        label(share, "01 / SHARE", bg=PANEL, fg=GREEN, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        label(share, "This computer", bg=PANEL, font=("Segoe UI", 18)).pack(anchor="w", pady=(9, 2))
        label(share, self.device_id, bg=PANEL, fg=MUTED, font=("Consolas", 18)).pack(anchor="w", pady=3)
        label(share, "Start once. Send the generated connection\ncode to the person connecting.", bg=PANEL, fg=MUTED, justify="left").pack(anchor="w", pady=10)
        self.share_button = button(share, "Share this computer", self.share); self.share_button.pack(fill="x", pady=7)
        actions = tk.Frame(share, bg=PANEL); actions.pack(fill="x", pady=(4, 0))
        self.copy_button = button(actions, "Copy code", self.copy_invitation, True); self.copy_button.pack(side="left", expand=True, fill="x", padx=(0, 5)); self.copy_button.configure(state="disabled")
        self.save_button = button(actions, "Save invitation", self.save_invitation, True); self.save_button.pack(side="left", expand=True, fill="x", padx=(5, 0)); self.save_button.configure(state="disabled")
        label(connect, "02 / CONNECT", bg=PANEL, fg=GREEN, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        label(connect, "Another computer", bg=PANEL, font=("Segoe UI", 18)).pack(anchor="w", pady=(9, 2))
        label(connect, "Paste its connection code or open\nan invitation file.", bg=PANEL, fg=MUTED, justify="left").pack(anchor="w", pady=10)
        self.code = tk.Text(connect, height=3, width=33, bg=BG, fg=TEXT, insertbackground=GREEN, relief="flat", font=("Consolas", 9), wrap="char")
        self.code.pack(fill="x", pady=5)
        row = tk.Frame(connect, bg=PANEL); row.pack(fill="x", pady=(8, 0))
        button(row, "Connect", self.connect).pack(side="left", fill="x", expand=True, padx=(0, 5))
        button(row, "Open invitation", self.open_invitation, True).pack(side="left", fill="x", expand=True, padx=(5, 0))
        options = tk.Frame(outer, bg=BG); options.pack(fill="x")
        label(options, "Screen quality", fg=MUTED).pack(side="left", padx=(0, 10))
        quality = ttk.Combobox(options, textvariable=self.profile, values=list(PROFILES), state="readonly", width=26); quality.pack(side="left", ipady=5)
        quality.bind("<<ComboboxSelected>>", lambda _: self.change_quality())
        button(options, "Stop / disconnect", self.disconnect, True).pack(side="right")
        self.control_check = tk.Checkbutton(outer, text="Allow keyboard and mouse for the current approved viewer", variable=self.control, command=self.change_control,
            bg=BG, fg=TEXT, activebackground=BG, activeforeground=TEXT, selectcolor=PANEL, font=("Segoe UI", 10))
        self.control_check.pack(anchor="w", pady=(16, 4))
        label(outer, textvariable=self.status, fg=GREEN, wraplength=880, justify="left").pack(anchor="w", pady=9)
        self.logs = tk.Text(outer, height=4, bg=PANEL, fg=MUTED, relief="flat", font=("Consolas", 9), state="disabled", padx=10, pady=8, wrap="word")
        self.logs.pack(fill="both", expand=True, pady=(4, 8))
        footer = tk.Frame(outer, bg=BG); footer.pack(fill="x")
        label(footer, "Every incoming session needs approval. Closing the app removes its hosted connection.", fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        tk.Button(footer, text="About / licenses", command=self.about, bg=BG, fg=MUTED, relief="flat", font=("Segoe UI", 9), cursor="hand2").pack(side="right")

    def about(self):
        window = tk.Toplevel(self.root); window.title("CampusLink — About and licenses"); window.geometry("850x650"); window.configure(bg=BG)
        label(window, "CampusLink Desktop 0.3.0", font=("Segoe UI", 20)).pack(anchor="w", padx=20, pady=15)
        text = tk.Text(window, bg=PANEL, fg=TEXT, relief="flat", wrap="word", font=("Consolas", 9)); text.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        text.insert("end", "Independent attended remote desktop. Temporary tunnels have no uptime guarantee. The server runs on the sharing computer; VPS hosting is a future migration.\n\n")
        folder = ASSETS / "licenses"
        if not folder.exists():
            folder = ASSETS / "build/desktop-notices"
        for file in sorted(folder.rglob("*")):
            if file.is_file():
                text.insert("end", "\n\n===== " + str(file.relative_to(folder)) + " =====\n\n" + file.read_text(encoding="utf-8", errors="replace"))
        text.configure(state="disabled")

    def log(self, text):
        self.logs.configure(state="normal"); self.logs.insert("end", time.strftime("%H:%M:%S ") + str(text) + "\n")
        self.logs.see("end"); self.logs.configure(state="disabled")

    def share(self):
        if self.peer or self.runtime:
            messagebox.showinfo("CampusLink", "Stop the current connection before starting a new hosted connection."); return
        self.runtime = ManagedRuntime(self.events)
        self.share_button.configure(state="disabled")
        threading.Thread(target=self.runtime.start, daemon=True).start()

    def connect(self):
        if self.peer or self.runtime:
            messagebox.showinfo("CampusLink", "Stop the current connection before connecting to a different computer."); return
        try:
            invitation = Invitation.decode(self.code.get("1.0", "end"))
        except ValueError as error:
            messagebox.showerror("Connection code", str(error)); return
        self.peer = NativePeer(self.events, "viewer", invitation.device_id, invitation.key)
        self.peer.profile = self.profile.get(); self.peer.connect(invitation.url)
        self.status.set("Connecting… Waiting for the other computer to approve.")
        self.code.delete("1.0", "end")

    def copy_invitation(self):
        if self.invitation:
            self.root.clipboard_clear(); self.root.clipboard_append(self.invitation.encode())
            self.status.set("Connection code copied. Share it privately with your intended viewer.")

    def save_invitation(self):
        if not self.invitation:
            return
        path = filedialog.asksaveasfilename(title="Save connection invitation", defaultextension=".campuslink", filetypes=[("CampusLink invitation", "*.campuslink")], initialfile="Connect-to-my-computer.campuslink")
        if path:
            Path(path).write_text(self.invitation.encode(), encoding="utf-8")
            self.status.set("Invitation saved. It contains the access key; share it privately. Local approval is still required.")

    def open_invitation(self):
        path = filedialog.askopenfilename(title="Open CampusLink invitation", filetypes=[("CampusLink invitation", "*.campuslink"), ("Text files", "*.txt")])
        if path:
            try:
                if Path(path).stat().st_size > 4096:
                    raise ValueError("Invitation file is too large.")
                value = Path(path).read_text(encoding="utf-8")
                Invitation.decode(value)
                self.code.delete("1.0", "end"); self.code.insert("1.0", value); self.connect()
            except (OSError, ValueError) as error:
                messagebox.showerror("Invitation", str(error))

    def ask(self, title, text, actions, timeout=40):
        if self.prompt and self.prompt.winfo_exists():
            return
        prompt = tk.Toplevel(self.root); self.prompt = prompt
        prompt.title("CampusLink — " + title); prompt.geometry("540x245"); prompt.configure(bg=BG); prompt.resizable(False, False)
        prompt.transient(self.root); prompt.attributes("-topmost", True)
        frame = tk.Frame(prompt, bg=BG, padx=24, pady=20); frame.pack(fill="both", expand=True)
        label(frame, title, font=("Segoe UI", 19)).pack(anchor="w")
        label(frame, text, fg=MUTED, wraplength=485, justify="left").pack(anchor="w", pady=(13, 18))
        row = tk.Frame(frame, bg=BG); row.pack(fill="x")
        def choose(callback):
            if not prompt.winfo_exists():
                return
            prompt.destroy(); self.prompt = None; callback()
        for index, (name, callback) in enumerate(actions):
            button(row, name, lambda c=callback: choose(c), index == 0).pack(side="left", padx=(0, 8))
        prompt.protocol("WM_DELETE_WINDOW", lambda: choose(actions[0][1]))
        prompt.after(timeout * 1000, lambda: choose(actions[0][1]) if prompt.winfo_exists() else None)
        prompt.lift(); self.root.bell()

    def change_quality(self):
        if self.peer:
            self.peer.profile = self.profile.get()
            session = self.peer.current
            if session and session.approved and session.mode == "viewing" and session.native:
                self.peer.secure({"type": "quality", "profile": self.profile.get()})

    def change_control(self):
        if self.peer and self.peer.current and self.peer.current.mode == "sharing":
            self.peer.set_control(self.control.get())
        else:
            self.control.set(False)

    def peer_event(self, peer, kind, data):
        if peer is not self.peer:
            return
        if kind == "online":
            if self.invitation:
                self.copy_button.configure(state="normal"); self.save_button.configure(state="normal")
            self.status.set("Ready to share. Send a connection code or invitation; approve each incoming request here.")
        elif kind == "approval":
            session_id, name, requested = data
            actions = [("Decline", lambda: peer.approve(session_id, False)), ("View only", lambda: peer.approve(session_id, True))]
            if requested:
                actions.append(("Allow control", lambda: peer.approve(session_id, True, True)))
            self.ask("Allow this connection?", f"{name} knows the connection code and wants to see your primary screen.", actions)
        elif kind == "viewing":
            self.control.set(False)
            if not self.viewer:
                self.viewer = DesktopWindow(self, peer)
            self.viewer.refresh(data)
            self.status.set("Viewing " + data.remote_name + (" with remote control." if data.control else " in view-only mode."))
        elif kind == "sharing":
            if self.viewer:
                self.viewer.close(); self.viewer = None
            self.control.set(data.control)
            self.status.set("Sharing your screen with " + data.remote_name + (" — REMOTE CONTROL" if data.control else " — VIEW ONLY"))
        elif kind == "frame":
            if self.viewer:
                self.viewer.frame(*data)
        elif kind == "control-request":
            session_id, name = data
            self.ask("Allow remote control?", f"{name} requests keyboard and mouse access for this session.", [("Keep view only", lambda: None), ("Allow control", lambda: peer.set_control(True) if peer.current and peer.current.session_id == session_id else None)])
        elif kind == "reverse-offer":
            session_id, request_id, control = data
            self.ask("Switch connection direction?", "The other person offers to share their screen instead. Your current screen sharing will stop if you accept.",
                     [("Keep sharing", lambda: peer.accept_reverse(session_id, request_id, False, control)), ("Accept switch", lambda: peer.accept_reverse(session_id, request_id, True, control))], timeout=25)
        elif kind in ("ended", "offline"):
            if self.viewer:
                self.viewer.close(); self.viewer = None
            if self.prompt and self.prompt.winfo_exists():
                self.prompt.destroy(); self.prompt = None
            self.control.set(False); self.status.set(str(data)); self.log(data)
            if peer.role == "viewer":
                peer.stop(); self.peer = None
        elif kind in ("capture", "status"):
            self.log(data)
            if kind == "status":
                self.status.set(str(data))

    def poll(self):
        try:
            for _ in range(12):
                kind, data = self.events.get_nowait()
                if kind == "peer":
                    self.peer_event(*data)
                elif kind == "runtime-status" and data[0] is self.runtime:
                    self.status.set(data[1])
                elif kind == "runtime-ready" and data is self.runtime and not data.stopped.is_set():
                    key = secrets.token_hex(16)
                    self.invitation = Invitation(data.url, self.device_id, key)
                    self.peer = NativePeer(self.events, "host", self.device_id, key)
                    self.peer.profile = self.profile.get()
                    self.peer.connect(f"http://127.0.0.1:{data.port}", data.token)
                elif kind == "runtime-error" and data[0] is self.runtime:
                    self.status.set(data[1]); self.log(data[1]); self.disconnect(keep_status=True)
        except queue.Empty:
            pass
        self.root.after(8, self.poll)

    def disconnect(self, keep_status=False):
        if self.prompt and self.prompt.winfo_exists():
            self.prompt.destroy(); self.prompt = None
        if self.viewer:
            self.viewer.close(); self.viewer = None
        if self.peer:
            peer, self.peer = self.peer, None; peer.stop()
        if self.runtime:
            runtime, self.runtime = self.runtime, None
            threading.Thread(target=runtime.stop, daemon=True).start()
        self.invitation = None; self.control.set(False)
        self.copy_button.configure(state="disabled"); self.save_button.configure(state="disabled"); self.share_button.configure(state="normal")
        if not keep_status:
            self.status.set("Stopped. Your screen is private and this app's hosted outside connection is closed.")

    def close(self):
        runtime = self.runtime
        self.disconnect()
        if runtime:
            runtime.stop()
        self.root.destroy()


def main():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    root = tk.Tk()
    if len(sys.argv) == 3 and sys.argv[1] == "--check-installation":
        root.withdraw(); app = DesktopApp(root); root.update_idletasks()
        helpers = {}
        for name, command in (("node", [node_path(), "--version"]), ("tunnel", [ASSETS / "tools/cloudflared.exe", "--version"])):
            process = subprocess.run([str(value) for value in command], capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW)
            helpers[name] = {"ok": process.returncode == 0, "version": process.stdout.strip()}
        result = {"status": "ok", "frozen": bool(getattr(sys, "frozen", False)), "offline": app.peer is None and app.runtime is None, "nativeViewer": True, "uiRequestedSize": [root.winfo_reqwidth(), root.winfo_reqheight()], "helpers": helpers}
        root.destroy(); Path(sys.argv[2]).write_text(json.dumps(result, indent=2), encoding="utf-8"); return
    DesktopApp(root); root.mainloop()


if __name__ == "__main__":
    main()

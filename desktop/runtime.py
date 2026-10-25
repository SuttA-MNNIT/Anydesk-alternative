"""Managed, hidden relay/tunnel helpers bundled inside CampusLink.exe."""
import ctypes
import json
import os
from pathlib import Path
import queue
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
ASSETS = Path(getattr(sys, "_MEIPASS", ROOT))
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def settings_dir():
    result = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "CampusLink"
    result.mkdir(parents=True, exist_ok=True)
    return result


def identity():
    path = settings_dir() / "desktop.json"
    try:
        value = json.loads(path.read_text())
        device_id = value.get("deviceId", "")
        if re.fullmatch(r"\d{10}", device_id):
            return device_id
    except (OSError, ValueError):
        pass
    device_id = "".join(secrets.choice("0123456789") for _ in range(10))
    path.write_text(json.dumps({"deviceId": device_id}), encoding="utf-8")
    return device_id


def node_path():
    candidate = ASSETS / "runtime/node.exe"
    if candidate.is_file():
        return candidate
    import shutil
    installed = shutil.which("node")
    if not installed:
        raise RuntimeError("The bundled relay runtime is missing. Re-download CampusLink.exe.")
    return Path(installed)


class ManagedRuntime:
    def __init__(self, events):
        self.events = events
        self.children = []
        self.stopped = threading.Event()
        self.lock = threading.RLock()
        self.config_dir = None
        self.url = None
        self.token = secrets.token_hex(32)
        self.port = None
        self.job = None
        self._create_job()

    def _create_job(self):
        # A Windows Job Object removes the owned helpers even if the GUI crashes.
        if os.name != "nt":
            return
        try:
            from ctypes import wintypes
            class BASIC(ctypes.Structure):
                _fields_ = [("perProcess", ctypes.c_int64), ("perJob", ctypes.c_int64), ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t), ("active", wintypes.DWORD), ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]
            class IO(ctypes.Structure):
                _fields_ = [(name, ctypes.c_uint64) for name in ("readOps", "writeOps", "otherOps", "readBytes", "writeBytes", "otherBytes")]
            class EXTENDED(ctypes.Structure):
                _fields_ = [("basic", BASIC), ("io", IO), ("processMemory", ctypes.c_size_t), ("jobMemory", ctypes.c_size_t), ("peakProcess", ctypes.c_size_t), ("peakJob", ctypes.c_size_t)]
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]; kernel.CreateJobObjectW.restype = wintypes.HANDLE
            kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            job = kernel.CreateJobObjectW(None, None)
            limits = EXTENDED(); limits.basic.flags = 0x2000
            if job and kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                self.job, self.kernel = job, kernel
            elif job:
                kernel.CloseHandle(job)
        except Exception:
            self.job = None

    def spawn(self, arguments, env=None):
        with self.lock:
            if self.stopped.is_set():
                raise RuntimeError("Startup cancelled.")
            child = subprocess.Popen([str(value) for value in arguments], cwd=ASSETS, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
            self.children.append(child)
            if self.job:
                self.kernel.AssignProcessToJobObject(self.job, int(child._handle))
            return child

    def start(self, tunnel=True):
        try:
            self.events.put(("runtime-status", (self, "Starting the private office relay…")))
            self.config_dir = tempfile.TemporaryDirectory(prefix="CampusLink-")
            config = Path(self.config_dir.name) / "relay.json"
            config.write_text(json.dumps({"listenHost": "127.0.0.1", "port": 0, "enrollmentToken": self.token}), encoding="utf-8")
            env = dict(os.environ, CAMPUSLINK_RELAY_CONFIG=str(config))
            relay = self.spawn([node_path(), ASSETS / "server/index.mjs"], env)
            lines = queue.Queue()
            def read_lines(process, target):
                try:
                    for line in process.stdout:
                        target.put(line)
                except (OSError, ValueError):
                    pass
                finally:
                    target.put(None)
            threading.Thread(target=read_lines, args=(relay, lines), daemon=True).start()
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not self.stopped.is_set():
                try:
                    line = lines.get(timeout=.2)
                except queue.Empty:
                    continue
                if line is None:
                    raise RuntimeError("The office relay could not start.")
                match = re.search(r"CampusLink relay: http://127\.0\.0\.1:(\d+)", line)
                if match:
                    self.port = int(match[1]); break
            if self.port is None:
                raise RuntimeError("The office relay startup timed out.")
            local = f"http://127.0.0.1:{self.port}"
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(local + "/healthz", timeout=4) as response:
                if json.load(response).get("status") != "ok":
                    raise RuntimeError("The office relay health check failed.")
            if not tunnel:
                self.url = local
            else:
                self.events.put(("runtime-status", (self, "Creating your secure outside connection…")))
                connector = ASSETS / "tools/cloudflared.exe"
                if not connector.is_file():
                    raise RuntimeError("The bundled tunnel connector is missing. Re-download CampusLink.exe.")
                cloud = self.spawn([connector, "tunnel", "--protocol", "http2", "--url", local, "--no-autoupdate"])
                cloud_lines = queue.Queue()
                threading.Thread(target=read_lines, args=(cloud, cloud_lines), daemon=True).start()
                deadline = time.monotonic() + 75
                route, connected = None, False
                while time.monotonic() < deadline and not self.stopped.is_set():
                    try:
                        line = cloud_lines.get(timeout=.2)
                    except queue.Empty:
                        continue
                    if line is None:
                        raise RuntimeError("The outside connector stopped. Check your Internet connection.")
                    match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                    if match:
                        route = match[0]
                    if "Registered tunnel connection" in line:
                        connected = True
                    if route and connected:
                        self.url = route; break
                if not self.url:
                    raise RuntimeError("The outside connection timed out. The campus network may be blocking the connector.")
            if self.stopped.is_set():
                return
            self.events.put(("runtime-ready", self))
            while not self.stopped.wait(1):
                if any(child.poll() is not None for child in self.children):
                    raise RuntimeError("A connection helper stopped. Stop sharing and try again.")
        except Exception as error:
            if not self.stopped.is_set():
                self.events.put(("runtime-error", (self, str(error))))
            self.stop()

    def stop(self):
        self.stopped.set()
        with self.lock:
            children, self.children = self.children, []
            job, self.job = self.job, None
            config_dir, self.config_dir = self.config_dir, None
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=3)
            if child.stdout:
                child.stdout.close()
        if job:
            self.kernel.CloseHandle(job)
        if config_dir:
            try:
                config_dir.cleanup()
            except OSError:
                pass

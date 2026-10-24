"""Local-only browser QA fixture. Synthetic image and recorded inputs; never captures or controls Windows.

This is separate from the production host; the production host has no auto-approve mode.
"""
import base64
import io
import json
import sys
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "host"))
from protocol import Channel
from PIL import Image, ImageDraw, ImageFont
import websocket

ROOT = Path(__file__).resolve().parent.parent
TOKEN = json.loads((ROOT / "config/relay.json").read_text())["enrollmentToken"]
DEVICE = "9998887776"
SECRET = "0123456789abcdef0123456789abcdef"
current = None
frame_index = 0
lock = threading.RLock()
image = Image.new("RGB", (1280, 720), "#12201c")
draw = ImageDraw.Draw(image)
font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 32)
small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 20)
draw.rounded_rectangle((55, 55, 1225, 665), 25, fill="#1e3328", outline="#7eac5a", width=2)
draw.text((100, 105), "CampusLink / encrypted screen test", font=font, fill="#c4f277")
draw.text((100, 180), "Synthetic desktop - no real screen or Windows input exposed", font=small, fill="#dbe9da")
draw.text((100, 230), "1280 x 720 / browser JPEG decoding / authenticated session", font=small, fill="#94b9a5")
draw.rounded_rectangle((100, 320, 1180, 570), 14, fill="#101c18")
draw.text((135, 360), "Local QA fixture", font=font, fill="#e9f3e8")
draw.text((135, 420), "Keyboard and pointer events are recorded only in the test log.", font=small, fill="#94b9a5")
out = io.BytesIO(); image.save(out, format="JPEG", quality=80); FRAME = out.getvalue()


def log(event, **data):
    print(json.dumps({"event": event, **data}), flush=True)


def send(ws, value=None, frame=False):
    with lock:
        if current:
            ws.send(current.seal(2 if frame else 1, FRAME if frame else json.dumps(value).encode()), opcode=websocket.ABNF.OPCODE_BINARY)


def message(ws, data):
    global current, frame_index
    if isinstance(data, str):
        msg = json.loads(data)
        if msg["type"] == "registered":
            log("registered", deviceId=DEVICE)
        elif msg["type"] == "session":
            current = Channel(SECRET, msg["sessionId"]); frame_index = 0
        elif msg["type"] == "session-ended":
            log("ended"); current = None
        return
    try:
        kind, payload = current.open(data)
        msg = json.loads(payload)
        if msg["type"] == "auth":
            log("authenticated", name=msg["name"])
            ws.send(json.dumps({"type": "ready"}))
            send(ws, {"type": "approved", "control": msg.get("control", False), "name": "CampusLink QA desktop"})
            send(ws, frame=True)
        elif msg["type"] == "ack":
            frame_index += 1
            if frame_index < 50:
                timer = threading.Timer(0.1, lambda: send(ws, frame=True))
                timer.daemon = True; timer.start()
        else:
            log("input", type=msg["type"], code=msg.get("code"), down=msg.get("down"))
    except Exception:
        log("authentication_rejected"); ws.send(json.dumps({"type": "end"}))


ws = websocket.WebSocketApp("ws://localhost:8787/ws", on_open=lambda ws: ws.send(json.dumps({"type": "register-host", "token": TOKEN, "deviceId": DEVICE})), on_message=message)
try:
    ws.run_forever(suppress_origin=True)
finally:
    ws.close()

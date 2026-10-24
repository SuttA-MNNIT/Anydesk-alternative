"""CampusLink v1 authenticated duplex channel; matches web/protocol.js."""
import os
import re
import struct
import threading
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class Channel:
    def __init__(self, secret: str, session_id: str, role: str = "host"):
        if not re.fullmatch(r"[a-fA-F0-9]{32}", secret) or not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise ValueError("Invalid session credentials")
        if role not in ("host", "viewer"):
            raise ValueError("Invalid channel role")
        material = PBKDF2HMAC(algorithm=hashes.SHA256(), length=64, salt=f"CampusLink/1/{session_id}".encode(), iterations=150000).derive(secret.lower().encode())
        viewer, host = AESGCM(material[:32]), AESGCM(material[32:])
        self.sender, self.receiver = (host, viewer) if role == "host" else (viewer, host)
        self.send_suffix = (session_id + role).encode()
        self.receive_suffix = (session_id + ("viewer" if role == "host" else "host")).encode()
        self.sequence = 0
        self.received = -1
        self.lock = threading.RLock()

    def seal(self, kind: int, payload: bytes) -> bytes:
        with self.lock:
            header = bytes([1]) + struct.pack(">Q", self.sequence)
            self.sequence += 1
            nonce = os.urandom(12)
            cipher = self.sender.encrypt(nonce, bytes([kind]) + payload, header + self.send_suffix)
            return header + nonce + cipher

    def open(self, packet: bytes):
        if len(packet) < 38 or packet[0] != 1:
            raise ValueError("Invalid encrypted packet")
        sequence = struct.unpack(">Q", packet[1:9])[0]
        if sequence <= self.received:
            raise ValueError("Replayed packet rejected")
        plain = self.receiver.decrypt(packet[9:21], packet[21:], packet[:9] + self.receive_suffix)
        self.received = sequence
        return plain[0], plain[1:]

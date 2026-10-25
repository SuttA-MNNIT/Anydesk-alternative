"""Self-contained connection codes; no public directory or embedded office secrets."""
import base64
import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Invitation:
    url: str
    device_id: str
    key: str

    def validate(self):
        parsed = urlsplit(self.url)
        if len(self.url) > 512 or parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError("Invalid connection address in this invitation.")
        if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("Connections outside this computer must use HTTPS.")
        if not re.fullmatch(r"\d{10}", self.device_id) or not re.fullmatch(r"[a-f0-9]{32}", self.key):
            raise ValueError("Invalid device ID or access key in this invitation.")
        return self

    def encode(self):
        self.validate()
        raw = json.dumps({"v": 3, "u": self.url, "d": self.device_id, "k": self.key}, separators=(",", ":")).encode()
        return "CL3." + base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @classmethod
    def decode(cls, text):
        value = "".join(text.split())
        if not value.startswith("CL3.") or len(value) > 2048 or not re.fullmatch(r"CL3\.[A-Za-z0-9_-]+", value):
            raise ValueError("Paste a CampusLink connection code beginning with CL3.")
        try:
            raw = value[4:]
            data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
            if data.get("v") != 3 or set(data) != {"v", "u", "d", "k"}:
                raise ValueError()
            if not all(isinstance(data[field], str) for field in ("u", "d", "k")):
                raise ValueError()
            return cls(data["u"], data["d"], data["k"]).validate()
        except (ValueError, TypeError, KeyError, UnicodeError) as error:
            raise ValueError("This connection code is invalid or incomplete.") from error

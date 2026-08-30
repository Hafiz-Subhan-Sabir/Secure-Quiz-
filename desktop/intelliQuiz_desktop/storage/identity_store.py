"""Encrypted on-device face identity templates (per student email)."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import numpy as np
from cryptography.fernet import Fernet


def _safe_email(email: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", email.strip().lower())


class IdentityStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "identity"
        self.root.mkdir(parents=True, exist_ok=True)
        key_path = self.root / ".key"
        if key_path.exists():
            key = key_path.read_bytes()
        else:
            key = Fernet.generate_key()
            key_path.write_bytes(key)
        self._fernet = Fernet(key)
        self._lock = threading.RLock()

    def _path_for(self, email: str) -> Path:
        return self.root / f"{_safe_email(email)}.enc"

    def is_enrolled(self, email: str) -> bool:
        return self._path_for(email).exists()

    def save(self, email: str, embedding: np.ndarray) -> None:
        payload = {"embedding": embedding.astype(np.float64).tolist()}
        blob = self._fernet.encrypt(json.dumps(payload).encode())
        with self._lock:
            self._path_for(email).write_bytes(blob)

    def load(self, email: str) -> np.ndarray | None:
        path = self._path_for(email)
        if not path.exists():
            return None
        with self._lock:
            raw = self._fernet.decrypt(path.read_bytes())
        data = json.loads(raw.decode())
        return np.asarray(data["embedding"], dtype=np.float64)

import hashlib
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class StoredObject:
    storage_key: str
    sha256: str
    size_bytes: int


class LocalObjectStore:
    def __init__(self, root: str):
        self.root = root
        os.makedirs(self.root, exist_ok=True)

    def put(self, data: bytes, suffix: str = "") -> StoredObject:
        digest = hashlib.sha256(data).hexdigest()
        storage_key = f"{digest}{suffix}"
        path = os.path.join(self.root, storage_key)
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(data)
        return StoredObject(storage_key=storage_key, sha256=digest, size_bytes=len(data))

    def get(self, storage_key: str) -> bytes:
        with open(os.path.join(self.root, storage_key), "rb") as f:
            return f.read()

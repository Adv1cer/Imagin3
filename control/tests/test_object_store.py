import hashlib
from imagin.object_store import LocalObjectStore


def test_put_then_get_round_trips_bytes(tmp_path):
    store = LocalObjectStore(str(tmp_path))
    data = b"hello imagin"

    stored = store.put(data, suffix=".txt")

    assert stored.sha256 == hashlib.sha256(data).hexdigest()
    assert stored.size_bytes == len(data)
    assert store.get(stored.storage_key) == data


def test_put_is_idempotent_by_content_hash(tmp_path):
    store = LocalObjectStore(str(tmp_path))
    data = b"same bytes twice"

    first = store.put(data)
    second = store.put(data)

    assert first.storage_key == second.storage_key

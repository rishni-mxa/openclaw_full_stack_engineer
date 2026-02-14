import os
from estimates_monitor import storage

def test_state_read_write(tmp_path):
    p = tmp_path / "state.json"
    storage.STATE_PATH = p
    state = storage.load_state()
    assert isinstance(state, dict)
    storage.mark_seen("id1", {"title":"t"})
    assert storage.is_seen("id1")

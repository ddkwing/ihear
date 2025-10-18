from pathlib import Path

from ihear.storage import Storage, StorageError


def test_add_and_retrieve_transcript(tmp_path):
    db_path = tmp_path / "store.db"
    storage = Storage(db_path=db_path)

    record = storage.add_transcript("Meeting", "Discussed roadmap", audio_path=tmp_path / "meeting.wav")

    fetched = storage.get_transcript(record.id)
    assert fetched.title == "Meeting"
    assert fetched.transcript == "Discussed roadmap"
    assert fetched.audio_path == tmp_path / "meeting.wav"


def test_update_summary(tmp_path):
    storage = Storage(db_path=tmp_path / "store.db")
    record = storage.add_transcript("Sync", "Talked about plans")

    updated = storage.update_summary(record.id, "Plans summary")
    assert updated.summary == "Plans summary"


def test_delete_transcript(tmp_path):
    storage = Storage(db_path=tmp_path / "store.db")
    record = storage.add_transcript("Note", "Content")
    storage.delete_transcript(record.id)

    try:
        storage.get_transcript(record.id)
    except StorageError:
        pass
    else:
        raise AssertionError("Transcript should have been removed")

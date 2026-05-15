import json
import os
import sys
import unittest.mock as mock
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class TestNormalizeNote:
    def test_missing_fields_get_defaults(self):
        note = {"title": "only title"}
        result = main._normalize_note(note)
        assert result["content"] == ""
        assert result["tags"] == []
        assert result["type"] == "note"
        assert result["url"] == ""
        assert result["review_count"] == 0
        assert result["reviewed_at"] is None

    def test_existing_fields_not_overwritten(self):
        note = {
            "title": "hello", "content": "world", "tags": ["a", "b"],
            "type": "link", "url": "http://x.com",
            "reviewed_at": "2026-01-01", "review_count": 3,
        }
        result = main._normalize_note(note)
        assert result["title"] == "hello"
        assert result["content"] == "world"
        assert result["tags"] == ["a", "b"]
        assert result["type"] == "link"
        assert result["review_count"] == 3

    def test_non_list_tags_reset_to_empty(self):
        for bad_value in ("tagstring", 42, None, {"a": 1}):
            note = {"tags": bad_value}
            result = main._normalize_note(note)
            assert result["tags"] == [], f"tags should be [] for {bad_value!r}"

    def test_missing_timestamps_filled_with_valid_iso(self):
        note = {}
        before = datetime.now().isoformat(timespec="seconds")
        result = main._normalize_note(note)
        after = datetime.now().isoformat(timespec="seconds")
        assert before <= result["created_at"] <= after
        assert before <= result["updated_at"] <= after
        datetime.fromisoformat(result["created_at"])  # 파싱 가능해야 함

    def test_empty_timestamps_filled(self):
        note = {"created_at": "", "updated_at": ""}
        result = main._normalize_note(note)
        assert result["created_at"] != ""
        assert result["updated_at"] != ""
        datetime.fromisoformat(result["created_at"])


class TestSaveLoadData:
    def _full_note(self, title="Test"):
        return {
            "id": "abc-123", "title": title, "content": "내용",
            "tags": ["태그"], "type": "note", "url": "",
            "reviewed_at": None, "review_count": 0,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }

    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "DATA_FILE", str(tmp_path / "brain.json"))
        data = {"notes": [self._full_note("저장 테스트")]}
        main.save_data(data)
        loaded = main.load_data()
        assert len(loaded["notes"]) == 1
        assert loaded["notes"][0]["title"] == "저장 테스트"

    def test_load_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "DATA_FILE", str(tmp_path / "nonexistent.json"))
        result = main.load_data()
        assert result == {"notes": []}

    def test_load_normalizes_incomplete_notes(self, tmp_path, monkeypatch):
        path = tmp_path / "brain.json"
        monkeypatch.setattr(main, "DATA_FILE", str(path))
        path.write_text(
            json.dumps({"notes": [{"title": "minimal"}]}), encoding="utf-8"
        )
        result = main.load_data()
        note = result["notes"][0]
        assert note["content"] == ""
        assert note["tags"] == []
        assert note["review_count"] == 0
        assert note["title"] == "minimal"

    def test_load_corrupt_file_returns_empty(self, tmp_path, monkeypatch):
        path = tmp_path / "brain.json"
        monkeypatch.setattr(main, "DATA_FILE", str(path))
        path.write_text("{ not valid json {{{{", encoding="utf-8")
        with mock.patch("tkinter.messagebox.showerror"):
            result = main.load_data()
        assert result == {"notes": []}


class TestSaveLoadConfig:
    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "CONFIG_FILE", str(tmp_path / "config.json"))
        config = {"api_key": "test-key-abc", "last_briefing_date": "2026-05-15"}
        main.save_config(config)
        loaded = main.load_config()
        assert loaded["api_key"] == "test-key-abc"
        assert loaded["last_briefing_date"] == "2026-05-15"

    def test_load_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "CONFIG_FILE", str(tmp_path / "nonexistent.json"))
        result = main.load_config()
        assert result == {}


class TestFetchUrlSummary:
    def test_unreachable_url_returns_error_tuple(self):
        title, body, err = main.fetch_url_summary("http://localhost:0/no-such-page")
        assert title == ""
        assert body == ""
        assert err is not None
        assert isinstance(err, str)

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

    def test_tags_list_is_independent_per_note(self):
        """H-2 회귀: 태그 없는 두 노트를 각각 정규화하면 tags는 서로 다른 객체여야 한다.

        수정 전: _NOTE_DEFAULTS["tags"]( = [] )를 그대로 할당 → 두 노트가 같은 [] 공유
        수정 후: v.copy() 로 독립 객체 생성 → 한쪽 수정이 다른 쪽에 영향 없음
        """
        note_a = {"title": "A"}
        note_b = {"title": "B"}
        main._normalize_note(note_a)
        main._normalize_note(note_b)
        assert note_a["tags"] is not note_b["tags"], \
            "두 노트의 tags가 같은 객체를 공유하면 한쪽 수정이 다른 쪽에 영향을 줌"
        note_a["tags"].append("추가태그")
        assert note_b["tags"] == [], \
            "note_a의 tags 변경이 note_b에 전파되면 안 됨"


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


class TestNoteIdLookup:
    """H-1 회귀: 존재하지 않는 note_id 탐색 시 StopIteration 방지.

    select_note() / save_note() 는 Tkinter 앱 인스턴스가 필요해 직접 호출이 불가하므로
    두 함수가 공통으로 사용하는 next((n …), None) 패턴을 데이터 레이어에서 검증한다.
    수정 전: next(n for n in notes if …)  → 미존재 ID 시 StopIteration
    수정 후: next((n for n in notes if …), None) → None 반환, 예외 없음
    """

    def _make_notes(self):
        return [
            {"id": "aaa-111", "title": "노트A"},
            {"id": "bbb-222", "title": "노트B"},
        ]

    def test_existing_id_returns_note(self):
        notes = self._make_notes()
        result = next((n for n in notes if n["id"] == "aaa-111"), None)
        assert result is not None
        assert result["title"] == "노트A"

    def test_missing_id_returns_none_not_stopiteration(self):
        """존재하지 않는 ID 탐색 시 StopIteration 대신 None을 반환해야 한다."""
        notes = self._make_notes()
        result = next((n for n in notes if n["id"] == "nonexistent-id"), None)
        assert result is None

    def test_empty_notes_returns_none(self):
        """노트 목록이 비어 있어도 예외 없이 None을 반환해야 한다."""
        result = next((n for n in [] if n["id"] == "any-id"), None)
        assert result is None


class TestFetchUrlSummary:
    def test_unreachable_url_returns_error_tuple(self):
        title, body, err = main.fetch_url_summary("http://localhost:0/no-such-page")
        assert title == ""
        assert body == ""
        assert err is not None
        assert isinstance(err, str)

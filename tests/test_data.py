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

    def test_save_data_shows_error_on_failure(self, tmp_path, monkeypatch):
        """Fix-1 회귀: os.replace 실패 시 showerror 팝업을 1회 호출해야 한다."""
        monkeypatch.setattr(main, "DATA_FILE", str(tmp_path / "brain.json"))
        monkeypatch.setattr("os.replace", mock.Mock(side_effect=OSError("디스크 꽉 참")))
        data = {"notes": [self._full_note("실패 테스트")]}
        with mock.patch("tkinter.messagebox.showerror") as mocked:
            main.save_data(data)
        assert mocked.call_count == 1
        assert "저장 실패" in mocked.call_args[0][0]


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

    def test_save_config_logs_on_failure(self, tmp_path, monkeypatch):
        """save_config() 실패 경로 회귀: 저장 실패 시 logging.error를 1회 호출해야 한다."""
        monkeypatch.setattr(main, "CONFIG_FILE", str(tmp_path / "config.json"))
        with mock.patch("builtins.open", side_effect=OSError("권한 없음")):
            with mock.patch("main.logging") as mock_log:
                main.save_config({"api_key": "test"})
        mock_log.error.assert_called_once()


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


class TestFetchYoutubeTranscript:
    """_fetch_youtube_transcript() — YouTubeTranscriptApi 1.x 인스턴스 방식 mock 검증."""

    _SEGMENTS_KO = [{"text": "안녕하세요"}, {"text": "반갑습니다"}]
    _SEGMENTS_FB = [{"text": "hello"}, {"text": "world"}]

    def test_ko_en_success_returns_joined_text(self):
        """ko/en 자막이 있으면 세그먼트를 공백으로 합쳐 반환한다."""
        with mock.patch("youtube_transcript_api.YouTubeTranscriptApi") as MockClass:
            mock_fetched = mock.Mock()
            mock_fetched.to_raw_data.return_value = self._SEGMENTS_KO
            MockClass.return_value.fetch.return_value = mock_fetched
            result = main._fetch_youtube_transcript("dQw4w9WgXcQ")
        MockClass.return_value.fetch.assert_called_once_with("dQw4w9WgXcQ", languages=["ko", "en"])
        assert result == "안녕하세요 반갑습니다"

    def test_fallback_used_when_ko_en_unavailable(self):
        """ko/en 자막 실패 시 list() 폴백으로 전환하고 logging.warning을 1회 기록한다."""
        with mock.patch("youtube_transcript_api.YouTubeTranscriptApi") as MockClass:
            mock_instance = MockClass.return_value
            mock_instance.fetch.side_effect = Exception("No transcript")
            # 폴백: api.list() → iter() → next() → .fetch() → .to_raw_data()
            mock_fb_fetched = mock.Mock()
            mock_fb_fetched.to_raw_data.return_value = self._SEGMENTS_FB
            mock_transcript = mock.Mock()
            mock_transcript.fetch.return_value = mock_fb_fetched
            mock_instance.list.return_value = [mock_transcript]
            with mock.patch("main.logging") as mock_log:
                result = main._fetch_youtube_transcript("dQw4w9WgXcQ")
        assert result == "hello world"
        mock_log.warning.assert_called_once()


class TestBackup:
    """BrainApp._backup() — self 미사용 메서드이므로 MagicMock으로 Tkinter 없이 검증."""

    def test_backup_shows_error_on_failure(self, tmp_path, monkeypatch):
        """shutil.copy2 실패 시 showerror를 1회 호출해야 한다."""
        path = tmp_path / "brain.json"
        path.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(main, "DATA_FILE", str(path))
        with mock.patch("main.shutil.copy2", side_effect=OSError("디스크 꽉 참")):
            with mock.patch("tkinter.messagebox.showerror") as mock_err:
                main.BrainApp._backup(mock.MagicMock())
        assert mock_err.call_count == 1
        assert "백업 실패" in mock_err.call_args[0][0]

    def test_backup_shows_info_on_success(self, tmp_path, monkeypatch):
        """백업 성공 시 showinfo를 1회 호출하고 showerror는 호출하지 않아야 한다."""
        path = tmp_path / "brain.json"
        path.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(main, "DATA_FILE", str(path))
        with mock.patch("tkinter.messagebox.showinfo") as mock_info:
            with mock.patch("tkinter.messagebox.showerror") as mock_err:
                main.BrainApp._backup(mock.MagicMock())
        assert mock_info.call_count == 1
        assert mock_err.call_count == 0


class TestFindNonOverlappingPair:
    """BrainApp._find_non_overlapping_pair() — self.data만 사용하므로 MagicMock으로 검증."""

    def _make_self(self, notes):
        app = mock.MagicMock()
        app.data = {"notes": notes}
        return app

    def test_returns_no_overlap_true_when_tags_differ(self):
        """태그가 겹치지 않는 노트 쌍이 있으면 no_overlap=True를 반환해야 한다."""
        notes = [
            {"id": "a", "title": "A", "tags": ["python"]},
            {"id": "b", "title": "B", "tags": ["cooking"]},
        ]
        a, b, no_overlap = main.BrainApp._find_non_overlapping_pair(self._make_self(notes))
        assert no_overlap is True
        assert set(a["tags"]) & set(b["tags"]) == set()

    def test_fallback_returns_no_overlap_false_when_all_tags_overlap(self):
        """100회 시도 후 태그 겹치지 않는 쌍을 못 찾으면 no_overlap=False를 반환해야 한다."""
        notes = [
            {"id": "a", "title": "A", "tags": ["공통태그"]},
            {"id": "b", "title": "B", "tags": ["공통태그"]},
        ]
        _, _, no_overlap = main.BrainApp._find_non_overlapping_pair(self._make_self(notes))
        assert no_overlap is False


class TestFetchUrlSummary:
    def test_unreachable_url_returns_error_tuple(self):
        title, body, err = main.fetch_url_summary("http://localhost:0/no-such-page")
        assert title == ""
        assert body == ""
        assert err is not None
        assert isinstance(err, str)

    def test_http_error_returns_error_tuple(self):
        """raise_for_status() 회귀: 4xx/5xx 응답은 err 문자열을 반환해야 한다."""
        import requests as req
        mock_resp = mock.Mock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("404 Client Error")
        with mock.patch("requests.get", return_value=mock_resp):
            title, body, err = main.fetch_url_summary("https://example.com/not-found")
        assert title == ""
        assert body == ""
        assert err is not None
        assert "404" in err

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


class TestDataLocation:
    """init_data_location() — 노트를 앱 폴더가 아닌 데이터 폴더(기본: 문서 아래 SecondBrain 폴더)에 저장."""

    def _patch_paths(self, tmp_path, monkeypatch):
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        monkeypatch.setattr(main, "LEGACY_DATA_FILE", str(app_dir / "brain.json"))
        monkeypatch.setattr(main, "CONFIG_FILE", str(app_dir / "config.json"))
        monkeypatch.setattr(main, "DATA_FILE", str(app_dir / "brain.json"))
        monkeypatch.setattr(main, "_documents_dir", lambda: str(tmp_path / "docs"))
        return app_dir

    def test_default_location_is_documents_secondbrain(self, tmp_path, monkeypatch):
        self._patch_paths(tmp_path, monkeypatch)
        config = {}
        data_dir = main.init_data_location(config)
        assert data_dir == str(tmp_path / "docs" / "SecondBrain")
        assert main.DATA_FILE == os.path.join(data_dir, "brain.json")
        assert config["data_dir"] == data_dir           # config에 기록
        assert main.load_config()["data_dir"] == data_dir

    def test_custom_data_dir_from_config(self, tmp_path, monkeypatch):
        self._patch_paths(tmp_path, monkeypatch)
        custom = tmp_path / "my-notes"
        main.init_data_location({"data_dir": str(custom)})
        assert main.DATA_FILE == str(custom / "brain.json")

    def test_legacy_file_migrated_and_original_kept(self, tmp_path, monkeypatch):
        app_dir = self._patch_paths(tmp_path, monkeypatch)
        legacy = app_dir / "brain.json"
        legacy.write_text('{"notes": [{"title": "옛 노트"}]}', encoding="utf-8")
        main.init_data_location({})
        assert "옛 노트" in open(main.DATA_FILE, encoding="utf-8").read()
        assert not legacy.exists()
        assert (app_dir / "brain.json.migrated").exists()   # 원본은 지우지 않고 보존

    def test_existing_data_not_overwritten_by_legacy(self, tmp_path, monkeypatch):
        app_dir = self._patch_paths(tmp_path, monkeypatch)
        (app_dir / "brain.json").write_text('{"notes": [{"title": "옛"}]}', encoding="utf-8")
        new_dir = tmp_path / "docs" / "SecondBrain"
        new_dir.mkdir(parents=True)
        (new_dir / "brain.json").write_text('{"notes": [{"title": "새"}]}', encoding="utf-8")
        main.init_data_location({})
        assert '"새"' in (new_dir / "brain.json").read_text(encoding="utf-8")
        assert (app_dir / "brain.json").exists()            # 판단이 애매하면 손대지 않음


class TestAutoBackup:
    def _setup(self, tmp_path, monkeypatch):
        data = tmp_path / "brain.json"
        data.write_text('{"notes": []}', encoding="utf-8")
        monkeypatch.setattr(main, "DATA_FILE", str(data))
        return tmp_path / "backups"

    def test_creates_one_backup_per_day(self, tmp_path, monkeypatch):
        folder = self._setup(tmp_path, monkeypatch)
        from datetime import date
        first = main.auto_backup(today=date(2026, 10, 15))
        again = main.auto_backup(today=date(2026, 10, 15))
        assert first == again == str(folder / "brain_20261015.json")
        assert len(os.listdir(folder)) == 1

    def test_keeps_only_recent_days_and_manual_backups(self, tmp_path, monkeypatch):
        folder = self._setup(tmp_path, monkeypatch)
        folder.mkdir()
        from datetime import date, timedelta
        start = date(2026, 1, 1)
        for i in range(main.BACKUP_KEEP_DAYS + 5):
            (folder / f"brain_{start + timedelta(days=i):%Y%m%d}.json").write_text("{}")
        (folder / "brain_backup_20250101_000000.json").write_text("{}")   # 수동 백업
        main.auto_backup(today=start + timedelta(days=main.BACKUP_KEEP_DAYS + 5))
        daily = [f for f in os.listdir(folder) if f.startswith("brain_2")]
        assert len(daily) == main.BACKUP_KEEP_DAYS
        assert "brain_20260101.json" not in daily                    # 가장 오래된 것부터 정리
        assert (folder / "brain_backup_20250101_000000.json").exists()  # 수동 백업은 유지

    def test_no_data_file_no_backup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "DATA_FILE", str(tmp_path / "none.json"))
        assert main.auto_backup() is None


class TestSaveRetry:
    def test_retries_when_file_temporarily_locked(self, tmp_path, monkeypatch):
        """OneDrive 동기화 중 PermissionError가 잠깐 나도 재시도로 저장에 성공해야 한다."""
        monkeypatch.setattr(main, "DATA_FILE", str(tmp_path / "brain.json"))
        real_replace = os.replace
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError("locked by sync")
            return real_replace(src, dst)

        monkeypatch.setattr("os.replace", flaky)
        monkeypatch.setattr(main.time, "sleep", lambda s: None)
        with mock.patch("tkinter.messagebox.showerror") as err:
            main.save_data({"notes": [{"title": "ok"}]})
        assert err.call_count == 0
        assert calls["n"] == 3
        assert "ok" in (tmp_path / "brain.json").read_text(encoding="utf-8")


class TestRunAiAsync:
    """_run_ai_async() — google.genai 클라이언트 호출을 동기 실행으로 검증."""

    class _ImmediateThread:
        def __init__(self, target, daemon=None):
            self._target = target

        def start(self):
            self._target()

    def _run(self, monkeypatch, client):
        monkeypatch.setattr(main, "_ai_client", client)
        monkeypatch.setattr(main.threading, "Thread", self._ImmediateThread)
        parent = mock.MagicMock()
        parent.after.side_effect = lambda ms, fn: fn()
        ok, err = mock.Mock(), mock.Mock()
        main._run_ai_async(parent, "시스템 지시", "질문", on_success=ok, on_error=err)
        return ok, err

    def test_success_passes_text_with_model_and_ms_timeout(self, monkeypatch):
        client = mock.MagicMock()
        client.models.generate_content.return_value.text = "답변"
        ok, err = self._run(monkeypatch, client)
        ok.assert_called_once_with("답변")
        err.assert_not_called()
        kwargs = client.models.generate_content.call_args.kwargs
        assert kwargs["model"] == main.GEMINI_MODEL
        assert kwargs["contents"] == "질문"
        assert kwargs["config"].system_instruction == "시스템 지시"
        assert kwargs["config"].http_options.timeout == 60_000   # 단위 ms

    def test_empty_response_reported_as_error(self, monkeypatch):
        client = mock.MagicMock()
        client.models.generate_content.return_value.text = None
        ok, err = self._run(monkeypatch, client)
        ok.assert_not_called()
        assert "빈 응답" in err.call_args[0][0]

    def test_without_client_reports_error(self, monkeypatch):
        ok, err = self._run(monkeypatch, None)
        ok.assert_not_called()
        assert "API 키" in err.call_args[0][0]

    def test_default_model_is_not_restricted_legacy(self):
        assert main.GEMINI_MODEL == "gemini-3.5-flash-lite"


class TestConfirmLeaveEditor:
    """저장하지 않은 변경 확인 로직 — 예(저장)/아니요(버림)/취소(계속 편집)."""

    def _app(self, dirty=True, save_ok=True):
        app = mock.MagicMock()
        app._has_unsaved_changes.return_value = dirty
        app.save_note.return_value = save_ok
        return app

    def test_clean_editor_leaves_without_asking(self):
        app = self._app(dirty=False)
        with mock.patch("main.messagebox.askyesnocancel") as ask:
            assert main.BrainApp._confirm_leave_editor(app) is True
        ask.assert_not_called()

    @pytest.mark.parametrize("answer,save_ok,expected,saved", [
        (None, True, False, False),    # 취소 → 머무름
        (False, True, True, False),    # 아니요 → 저장 없이 이동
        (True, True, True, True),      # 예 → 저장 후 이동
        (True, False, False, True),    # 예지만 저장 실패(제목 없음 등) → 머무름
    ])
    def test_dirty_editor_answers(self, answer, save_ok, expected, saved):
        app = self._app(dirty=True, save_ok=save_ok)
        with mock.patch("main.messagebox.askyesnocancel", return_value=answer):
            assert main.BrainApp._confirm_leave_editor(app) is expected
        assert app.save_note.called is saved

    def test_new_note_cancelled_keeps_current_note(self):
        app = mock.MagicMock()
        app.selected_id = "keep-me"
        app._confirm_leave_editor.return_value = False
        assert main.BrainApp.new_note(app) is False
        assert app.selected_id == "keep-me"
        app.title_var.set.assert_not_called()


@pytest.fixture(scope="module")
def _gui_app_shared(tmp_path_factory):
    """트레이·클립보드·API 키 창을 끈 실제 BrainApp — 모듈에서 1개만 생성.

    Windows venv에서 Tk 인스턴스를 반복 생성하면 'Can't find a usable tk.tcl'이
    간헐적으로 나므로 하나를 공유한다. 화면이 없는 환경에서는 skip.
    """
    import tkinter as tk
    try:
        probe = tk.Tk(); probe.destroy()
    except tk.TclError as e:
        pytest.skip(f"디스플레이 없음: {e}")
    tmp = tmp_path_factory.mktemp("gui")
    mp = pytest.MonkeyPatch()
    mp.setattr(main, "CONFIG_FILE", str(tmp / "config.json"))
    mp.setattr(main, "LEGACY_DATA_FILE", str(tmp / "legacy.json"))
    mp.setattr(main, "_documents_dir", lambda: str(tmp / "docs"))
    for name in ("_init_api", "_start_tray", "_start_clipboard_monitor", "_run_briefing"):
        mp.setattr(main.BrainApp, name, lambda self: None)
    app = main.BrainApp()
    app.withdraw()
    yield app, tmp
    app.destroy()
    mp.undo()


@pytest.fixture
def gui_app(_gui_app_shared, monkeypatch):
    app, tmp = _gui_app_shared
    # 공유 앱의 DATA_FILE이 다른 테스트의 monkeypatch에 영향받지 않도록 테스트마다 고정
    monkeypatch.setattr(main, "DATA_FILE", str(tmp / "docs" / "SecondBrain" / "brain.json"))
    app.data = {"notes": []}
    # 공유 앱이라 이전 테스트의 검색어·예약된 검색·펼친 개수를 초기화
    app.search_var.set("")
    if app._search_after_id is not None:
        app.after_cancel(app._search_after_id)
        app._search_after_id = None
    app._list_limit = main.LIST_PAGE_SIZE
    app.new_note(confirm=False)
    app.refresh_list()
    return app


class TestUnsavedChangesGui:
    def _add_note(self, app, title, content=""):
        app.new_note(confirm=False)
        app.title_var.set(title)
        app.content_box.insert("1.0", content)
        assert app.save_note() is True
        return app.selected_id

    def test_switching_note_with_edits_asks_and_cancel_keeps_text(self, gui_app):
        first = self._add_note(gui_app, "첫 노트", "원래 내용")
        second = self._add_note(gui_app, "둘째 노트")
        gui_app.select_note(first)
        gui_app.content_box.insert("end", " + 고친 내용")
        with mock.patch("main.messagebox.askyesnocancel", return_value=None) as ask:
            gui_app.select_note(second)
        ask.assert_called_once()
        assert gui_app.selected_id == first
        assert "고친 내용" in gui_app.content_box.get("1.0", "end")

    def test_answer_yes_saves_before_switching(self, gui_app):
        first = self._add_note(gui_app, "첫 노트", "원래")
        second = self._add_note(gui_app, "둘째 노트")
        gui_app.select_note(first)
        gui_app.content_box.insert("end", " 추가")
        with mock.patch("main.messagebox.askyesnocancel", return_value=True):
            gui_app.select_note(second)
        assert gui_app.selected_id == second
        saved = next(n for n in gui_app.data["notes"] if n["id"] == first)
        assert saved["content"] == "원래 추가"

    def test_no_prompt_when_nothing_changed(self, gui_app):
        first = self._add_note(gui_app, "첫 노트")
        second = self._add_note(gui_app, "둘째 노트")
        with mock.patch("main.messagebox.askyesnocancel") as ask:
            gui_app.select_note(first)
            gui_app.select_note(second)
            gui_app.new_note()
        ask.assert_not_called()

    def test_delete_does_not_prompt(self, gui_app):
        self._add_note(gui_app, "지울 노트")
        gui_app.content_box.insert("end", "편집 중")
        with mock.patch("main.messagebox.askyesno", return_value=True), \
             mock.patch("main.messagebox.askyesnocancel") as ask:
            gui_app.delete_note()
        ask.assert_not_called()
        assert gui_app.data["notes"] == []


class TestSimilarCandidates:
    def _note(self, nid, tags, updated):
        return {"id": nid, "title": nid, "tags": tags, "updated_at": updated}

    def test_recent_notes_not_dropped(self):
        """저장 순서(오래된 순)로 앞 30개만 보내 최근 노트가 빠지던 문제 회귀."""
        notes = [self._note(f"n{i:03d}", [], f"2026-01-01T00:00:{i % 60:02d}".replace(
            "00:00:", f"{i // 60:02d}:00:")) for i in range(40)]
        picked = main._similar_candidates(notes, None, [], 30)
        assert len(picked) == 30
        assert picked[0]["id"] == "n039"                 # 가장 최근
        assert "n000" not in [n["id"] for n in picked]   # 가장 오래된 것부터 제외

    def test_shared_tags_ranked_first_and_current_excluded(self):
        notes = [
            self._note("cur", ["ai"], "2026-05-01"),
            self._note("recent-no-tag", ["요리"], "2026-09-01"),
            self._note("old-shared", ["ai", "글쓰기"], "2026-01-01"),
        ]
        picked = main._similar_candidates(notes, "cur", ["ai", "글쓰기"], 30)
        assert [n["id"] for n in picked] == ["old-shared", "recent-no-tag"]


class TestListWheelGui:
    def test_wheel_over_note_card_scrolls_list(self, gui_app):
        """노트 카드 위에서 휠을 굴려도 목록이 스크롤되어야 한다 (이전엔 캔버스에만 바인딩)."""
        gui_app.new_note(confirm=False)
        gui_app.title_var.set("휠 테스트")
        assert gui_app.save_note()
        card_label = gui_app.scroll_inner.winfo_children()[0].winfo_children()[1].winfo_children()[0]
        assert isinstance(card_label, __import__("tkinter").Label)
        # 숨긴(withdrawn) 창에는 휠 이벤트가 전달되지 않으므로 잠깐 표시
        gui_app.deiconify(); gui_app.update()
        try:
            with mock.patch.object(gui_app.canvas, "yview_scroll") as scroll:
                card_label.event_generate("<MouseWheel>", delta=-120, when="now")
        finally:
            gui_app.withdraw()
        scroll.assert_called_once_with(1, "units")


class TestListPagingGui:
    def _fill(self, app, count):
        app.data = {"notes": [main._normalize_note({
            "id": f"id-{i:04d}", "title": f"노트 {i}", "content": "내용", "tags": [],
            "updated_at": f"2026-01-01T{i // 3600:02d}:{i // 60 % 60:02d}:{i % 60:02d}"})
            for i in range(count)]}
        app._list_limit = main.LIST_PAGE_SIZE
        app.refresh_list()

    def test_renders_first_page_then_more(self, gui_app):
        self._fill(gui_app, 450)
        assert len(gui_app._cards) == 200
        assert "id-0449" in gui_app._cards                      # 가장 최근 노트부터
        assert "250개 남음" in gui_app._more_btn.cget("text")
        gui_app._show_more_notes()
        assert len(gui_app._cards) == 400
        gui_app._show_more_notes()
        assert len(gui_app._cards) == 450 and gui_app._more_btn is None

    def test_search_covers_all_notes_and_resets_page(self, gui_app):
        self._fill(gui_app, 450)
        gui_app._show_more_notes()
        gui_app.search_var.set("노트 3")
        gui_app._run_search_refresh()                           # 디바운스 없이 즉시 실행
        assert gui_app._list_limit == main.LIST_PAGE_SIZE
        assert "id-0003" in gui_app._cards                      # 오래된(목록 뒤쪽) 노트도 검색됨

    def test_save_keeps_expanded_page(self, gui_app):
        self._fill(gui_app, 450)
        gui_app._show_more_notes()
        gui_app.new_note(confirm=False)
        gui_app.title_var.set("새 노트")
        assert gui_app.save_note()
        assert len(gui_app._cards) == 400


class TestSelectionRepaintGui:
    def test_select_repaints_without_rebuilding_list(self, gui_app):
        gui_app.data = {"notes": [main._normalize_note({"id": f"n{i}", "title": f"t{i}"}) for i in range(3)]}
        gui_app.refresh_list()
        with mock.patch.object(gui_app, "refresh_list") as rebuild:
            gui_app.select_note("n1")
            gui_app.select_note("n2")
        rebuild.assert_not_called()
        assert gui_app._cards["n2"][0].cget("bg") == main.SEL
        assert gui_app._cards["n1"][0].cget("bg") == main.BG2


class TestPostToUi:
    def test_forwards_to_after(self):
        widget = mock.MagicMock()
        cb = mock.Mock()
        main._post_to_ui(widget, cb)
        widget.after.assert_called_once_with(0, cb)

    @pytest.mark.parametrize("exc", [RuntimeError("main thread is not in main loop"),
                                     __import__("tkinter").TclError("application has been destroyed")])
    def test_ignores_closed_app(self, exc):
        widget = mock.MagicMock()
        widget.after.side_effect = exc
        main._post_to_ui(widget, mock.Mock())   # 예외가 백그라운드 스레드로 새지 않아야 함


class TestYoutubeErrorCallback:
    def test_error_message_delivered_after_except_block(self, monkeypatch):
        """except 변수 e를 지연 lambda에서 참조해 NameError가 나던 문제 회귀 — 오류 안내가 전달돼야 한다."""
        app = mock.MagicMock()
        app._extract_youtube_id.return_value = "dQw4w9WgXcQ"
        app._check_api.return_value = True
        monkeypatch.setattr(main, "_fetch_youtube_transcript",
                            mock.Mock(side_effect=RuntimeError("자막 없음")))
        monkeypatch.setattr(main.threading, "Thread", TestRunAiAsync._ImmediateThread)
        # 실제 Tk처럼 콜백을 나중에(except 블록이 끝난 뒤) 실행해야 버그가 재현된다
        pending = []
        app.after.side_effect = lambda ms, fn: pending.append(fn)
        main.BrainApp._youtube_summary(app)
        for fn in pending:
            fn()
        app._youtube_error.assert_called_once_with("자막 없음")

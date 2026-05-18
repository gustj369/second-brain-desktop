# Changelog

모든 주요 변경사항을 이 파일에 기록합니다.

---

## [v8.6] - 2026-05-18
### Refactored
- 🔧 **`_run_ai_async()` 모듈 헬퍼 추출**: genai 모델 생성 · 백그라운드 스레드 · `after(0, 콜백)` 패턴을 모듈 레벨 순수 함수로 통합
- 🔧 **`BriefingDialog._fetch()`**: 직접 `genai` + `threading` 호출 → `_run_ai_async` 위임
- 🔧 **`IdeaColliderDialog._fetch()`**: 동일하게 `_run_ai_async` 위임
- 🔧 **`ThreadsDraftDialog._fetch()`**: 직접 `genai` + `threading` 호출 → `_run_ai_async` 위임
- 🔧 **`BrainApp._call_ai_async()`**: 내부 로직 제거 → `_run_ai_async` 위임으로 2줄 단순화

## [v8.5] - 2026-05-18
### Fixed
- 🛡️ **`_backup()` 예외 처리**: `shutil.copy2()` 실패 시 `logging.error` + `showerror` 팝업 — 디스크 풀·권한 오류 시 앱 비정상 종료 방지
- 🛡️ **`fetch_url_summary()` HTTP 오류 처리**: `res.raise_for_status()` 추가 — 4xx/5xx 응답을 오류로 처리, 오류 페이지 HTML이 노트에 저장되던 문제 수정
- 🔧 **`_ai_error()` 버튼 복원 책임 분산**: 하드코딩된 버튼 복원 제거 → `_find_keywords` · `_find_similar` 각 호출부의 `on_error` 콜백에서 자신의 버튼 복원
- 🔧 **`_fetch_youtube_transcript()` 1.x 호환성**: `get_transcript()` 클래스 메서드 → `YouTubeTranscriptApi()` 인스턴스 + `fetch()` + `to_raw_data()` 방식으로 교체 — YouTube 자막 요약 기능 실제 동작 복원
### Tests
- ✅ **`save_config()` 실패 경로 회귀 테스트**: `test_save_config_logs_on_failure` — `builtins.open` monkeypatch로 `logging.error` 1회 호출 검증
- ✅ **`fetch_url_summary()` HTTP 오류 회귀 테스트**: `test_http_error_returns_error_tuple` — mock 404 응답 시 `err` 반환 검증 — 총 21개 테스트

## [v8.4] - 2026-05-18
### Fixed
- 🛡️ **`save_data()` 예외 처리**: 저장 실패 시 `logging.error` + `showerror` 팝업으로 사용자에게 명시적 알림
- 🛡️ **`save_config()` 예외 처리**: 설정 저장 실패 시 `logging.error` (비치명적, UI 팝업 없음)
- 🛡️ **`_mark_reviewed()` 방어 코드**: `for/break` → `next(..., None)` + Early return + `logging.error` — 없는 note_id 탐색 시 크래시 방지
- 🔍 **`_fetch_youtube_transcript()` 폴백 로깅**: ko/en 자막 미존재 시 `except Exception as e` + `logging.warning` 추가
### Refactored
- 🔧 **매직 넘버 상수화**: `ASK_BRAIN_MAX_NOTES = 200`, `COLLISION_CONTEXT_LIMIT = 30` — `_ask_brain()` · `_find_similar()` 하드코딩 제거
### Tests
- ✅ **`save_data` 실패 경로 회귀 테스트**: `test_save_data_shows_error_on_failure` — `os.replace` monkeypatch로 예외 경로 강제 진입, `showerror` 1회 호출 검증 — 총 17개 테스트

## [v8.3] - 2026-05-17
### Fixed
- 🛡️ **mutable default 버그**: `_normalize_note()` 에서 `tags: []` 를 모든 노트가 공유하던 문제 → `v.copy()` 로 노트마다 독립 객체 할당
- 🛡️ **StopIteration 크래시**: `select_note()` / `save_note()` 에서 없는 note_id 탐색 시 앱 종료 → `next(..., None)` + Early return 으로 방어
- 🛡️ **토스트 Toplevel 부모 미지정**: `tk.Toplevel()` → `tk.Toplevel(self)` 로 메인 창과 생명주기 연동, 앱 종료 시 `TclError` 방어
### Refactored
- 🔧 **AI 공통 헬퍼 추출**: `_call_ai_async()` — `_find_keywords` / `_find_similar` / `_ask_brain` 세 함수의 genai 모델 생성·스레드·콜백 패턴 통합
- 🔧 **유튜브 자막 추출 분리**: `_fetch_youtube_transcript(vid)` 모듈 레벨 순수 함수로 분리 → UI 없이 단독 테스트 가능
### Tests
- ✅ **회귀 테스트 추가**: `test_tags_list_is_independent_per_note` (H-2), `TestNoteIdLookup` 3종 (H-1) — 총 16개 테스트

## [v8.2] - 2026-05-15
### Improved
- 🔧 **AI 모델명 상수화**: `GEMINI_MODEL = "gemini-2.5-flash"` — 7곳 하드코딩 제거, 모델 변경 시 한 줄만 수정
- 🔧 **파일 로깅 추가**: `RotatingFileHandler` (5 MB × 2개) → `brain.log` 기록, 모든 예외 블록에 스택트레이스 포함
- 🔧 **예외 처리 정리**: `except (json.JSONDecodeError, Exception)` → `except Exception` 중복 제거, 기존 무시 블록 9곳 로깅 추가
- 🛡️ **노트 제목 필수화**: 제목 없이 저장 불가 (기존: 제목·본문 모두 비어야 경고)
- ✨ **클립보드 자동 제목**: 클립보드 저장 시 첫 줄(최대 50자, 단어 경계)을 제목으로 자동 채움
- 🔧 **UI 타이밍·임계값 상수화**: `TOAST_TIMEOUT_MS = 8000`, `CLIPBOARD_MIN_LEN = 50`

## [v8.1] - 2026-04-25
### Fixed
- 🛡️ **원자적 저장**: 임시 파일 → `os.replace()` 교체 방식으로 저장 중 데이터 손상 방지
- 🛡️ **JSON 복구**: `brain.json` / `config.json` 파싱 오류 시 자동 백업 후 빈 데이터로 재시작
- 🛡️ **노트 스키마 보정**: 오래된 노트의 누락 필드를 로드 시 자동으로 채워 앱 오류 방지
- 🛡️ **스레드 안전**: 클립보드 감시 스레드에서 Tkinter 변수 대신 plain bool 사용
- 🛡️ **URL 스레드 분리**: `_fetch_summary()` 네트워크 요청을 백그라운드 스레드에서 실행
### Docs
- ABOUT-ME, docs/glossary.md, docs/plan.md 템플릿 내용 작성 완료

## [v8.0] - 2026-04-24
### Added
- 🕸️ **지식 그래프**: 공통 태그로 노트 연결 · 노드 클릭 시 해당 노트 열기 (networkx + matplotlib)
- 엣지 굵기 = 공통 태그 수 · 노드 크기 = 연결 수 기반
- 📈 **관심사 트래킹**: 월별 태그 사용 빈도 누적 막대 차트 (상위 10개 태그)
- "이번 달 가장 많이 생각한 주제: #태그명" 자동 문구 생성
- 🟩 **생산성 히트맵**: GitHub 잔디밭 스타일 최근 1년 히트맵
- 최다 작성일 / 최장 연속 작성 기록 통계 자동 표시

## [v7.0] - 2026-04-24
### Added
- 📱 **Threads 초안 생성**: "드라마틱 라이프" 페르소나 스타일 Gemini 포스트 초안 · 클립보드 복사
- 📋 **클립보드 자동 캡처**: 50자 이상 복사 시 토스트 알림 → 노트 즉시 저장
- 🖥️ **시스템 트레이**: 앱 최소화 시 트레이 상주 · 클립보드 캡처 ON/OFF 토글
- 🎬 **유튜브 자막 요약**: YouTube URL 감지 시 버튼 자동 표시 → 자막 추출 + Gemini 요약

## [v6.0] - 2026-04-24
### Added
- 💥 **아이디어 충돌기**: 태그 비중첩 노트 2개 → Gemini로 창의적 아이디어 3가지 생성
- 💥 충돌 결과를 "노트로 저장" 버튼 한 번으로 바로 저장 가능
- 🧠 **나에게 묻기**: 전체 노트를 컨텍스트로 질문 → 내 사고방식 기반 AI 답변
- 🧠 답변에 근거로 사용된 노트 제목 `📎 참고 노트:` 자동 표시
- 노트 200개 초과 시 최근 200개만 사용 + 안내 문구 표시

## [v5.0] - 2026-04-24
### Added
- ☀️ **일일 브리핑**: 앱 시작 시 랜덤 노트 3개 기반 AI 질문 팝업 (하루 1회, 노트 10개 이상)
- 🔁 **망각 방지 복습**: 7일 이상 된 노트에 🔁 아이콘 표시
- 노트 열람 시 "마지막으로 본 지 N일 됐어요" 안내 바 표시
- ✅ 복습 완료 버튼 → `reviewed_at` / `review_count` 필드 갱신

## [v4.0] - 2026-04-24
### Added
- 🔍 **전체 검색**: 제목 · 본문 · 태그 동시 검색
- 🏷 **태그 클라우드**: 자주 쓴 태그일수록 크게, 클릭 시 검색 연동
- 📊 헤더 통계: 노트 / 링크 개수 실시간 표시
- 💾 **백업 버튼**: `brain_backup_날짜시각.json` 자동 저장

## [v3.0] - 2026-04-24
### Added
- 🔗 **연결고리 찾기**: 현재 노트 키워드 5개 + 이유 (Gemini API)
- 🔍 **비슷한 노트 찾기**: 유사 노트 3개 추천, 클릭 시 이동
- Gemini API 연동 (`google-generativeai`)

## [v2.0] - 2026-04-24
### Added
- 노트 타입 선택 (📝 노트 / 🔗 링크)
- **URL 요약 가져오기**: 제목·본문 자동 추출 (`requests` + `BeautifulSoup`)

## [v1.0] - 2026-04-24
### Added
- 기본 노트 작성 · 편집 · 삭제 (확인 팝업)
- 태그 · 노트 목록 · 클릭 선택
- `brain.json` 로컬 저장
- 다크 테마 UI (Tkinter)

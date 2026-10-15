# 🧠 Second Brain Desktop

Claude와 Codex로 함께 바이브 코딩으로 만든 개인 지식 관리 시스템

## 💡 만든 이유

글감, 아이디어, 참고 자료가 여러 곳에 흩어지면 나중에 다시 보기 힘들다고 느꼈습니다.<br>
이 프로젝트는 단순히 자료를 저장하는 공간이 아니라, 생각을 모으고<br>
다시 분류하고 컨텐츠로 연결하기 위한 개인 시스템입니다.

## ✨ 주요 기능

- 📝 노트 작성 · 태그 · 저장 · 검색 (제목 · 본문 · 태그 동시 검색)
- 🔗 링크 타입 노트 + URL 자동 요약 가져오기
- 🤖 AI 연결고리 찾기 · 비슷한 노트 추천 · 나에게 묻기 (Gemini API)
- 💥 아이디어 충돌기 — 전혀 다른 노트 2개를 AI가 창의적으로 연결
- ☀️ 일일 브리핑 팝업 · 🔁 망각 방지 복습 알림
- 🏷 태그 클라우드 · 📊 노트/링크 통계 · 💾 백업 기능
- 📱 Threads 초안 생성 · 📋 클립보드 자동 캡처 · 🖥️ 시스템 트레이 상주
- 🎬 유튜브 자막 요약 (youtube-transcript-api + Gemini)
- 🕸️ 지식 그래프 — 공통 태그로 노트 연결 · 노드 클릭 시 바로 열기
- 📈 관심사 트래킹 — 월별 태그 빈도 차트 · 🟩 GitHub 스타일 생산성 히트맵

## 📁 파일 구조

```
second-brain-desktop/
├── main.py              # 앱 본체
├── requirements.txt     # 운영 의존성
├── requirements-dev.txt # 개발 의존성 (pytest)
├── tests/
│   └── test_data.py     # 단위 테스트
├── brain.log            # 에러 로그 (자동 생성, git 제외)
└── config.json          # API 키·설정 (자동 생성, git 제외 — 클라우드 동기화 안 함)

문서\SecondBrain\        # 노트 데이터 폴더 (기본값, Windows에선 OneDrive\문서로 자동 백업)
├── brain.json           # 노트 데이터
└── backups\             # 하루 1회 자동 백업(최근 30일) + 💾 수동 백업
```

노트 저장 위치는 `config.json`의 `data_dir`로 바꿀 수 있습니다.

## ▶️ 실행

```bash
.venv\Scripts\pythonw.exe main.py          # 창과 함께 실행 (콘솔 창 없음)
.venv\Scripts\pythonw.exe main.py --tray   # 트레이에 숨긴 채 실행 (PC 시작 시 자동 실행용)
```

- 이미 실행 중이면 새로 뜨지 않고 기존 창을 앞으로 불러옵니다.
- 창의 X는 트레이로 숨기기, 완전 종료는 트레이 아이콘 → **종료**.
이전 버전처럼 앱 폴더에 `brain.json`이 있으면 처음 실행할 때 데이터 폴더로 옮기고, 원본은 `brain.json.migrated`로 남깁니다.

## 🗺 로드맵

- [x] **Phase 1** — 노트 작성 · 태그 · 저장 · 다크 테마 UI
- [x] **Phase 2** — 노트 타입 (노트/링크) · URL 자동 요약
- [x] **Phase 3** — Gemini AI 연결: 연결고리 찾기 · 비슷한 노트 추천
- [x] **Phase 4** — 전체 검색 · 태그 클라우드 · 통계 · 백업
- [x] **Phase 5** — 일일 브리핑 · 망각 방지 복습 알림 시스템
- [x] **Phase 6** — 아이디어 충돌기 · 나에게 묻기 (내 노트 기반 Q&A)
- [x] **Phase 7** — Threads 초안 생성 · 클립보드 캡처 · 시스템 트레이 · 유튜브 자막 요약
- [x] **Phase 8** — 지식 그래프 시각화 · 관심사 트래킹 · 생산성 히트맵

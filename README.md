# 🧠 Second Brain Desktop

> 비개발자가 Claude와 함께 바이브 코딩으로 만든 개인 지식 관리 데스크탑 앱

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat&logo=python&logoColor=white)
![Tkinter](https://img.shields.io/badge/GUI-Tkinter-FF6B35?style=flat)
![Gemini](https://img.shields.io/badge/AI-Gemini_API-4285F4?style=flat&logo=google&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green?style=flat)
![Version](https://img.shields.io/badge/version-v8.2-blueviolet?style=flat)

<!-- screenshot here -->

## ✨ 현재 기능

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

## 🛠 설치 방법

**요구사항**: Python 3.9+ (tested on 3.14.2), Windows

```bash
# 1. 저장소 클론
git clone https://github.com/gustj258/second-brain-desktop.git
cd second-brain-desktop

# 2. 패키지 설치
pip install -r requirements.txt

# 3. 실행
python main.py
```

> **API 키**: [Google AI Studio](https://aistudio.google.com)에서 무료 발급 후 앱 첫 실행 시 입력창에 입력하면 자동 저장됩니다.

## 📁 파일 구조

```
second-brain-desktop/
├── main.py              # 앱 본체
├── requirements.txt     # 운영 의존성
├── requirements-dev.txt # 개발 의존성 (pytest)
├── tests/
│   └── test_data.py     # 단위 테스트
├── brain.json           # 노트 데이터 (자동 생성, git 제외)
├── brain.log            # 에러 로그 (자동 생성, git 제외)
└── config.json          # API 키 (자동 생성, git 제외)
```

## 🗺 로드맵

- [x] **Phase 1** — 노트 작성 · 태그 · 저장 · 다크 테마 UI
- [x] **Phase 2** — 노트 타입 (노트/링크) · URL 자동 요약
- [x] **Phase 3** — Gemini AI 연결: 연결고리 찾기 · 비슷한 노트 추천
- [x] **Phase 4** — 전체 검색 · 태그 클라우드 · 통계 · 백업
- [x] **Phase 5** — 일일 브리핑 · 망각 방지 복습 알림 시스템
- [x] **Phase 6** — 아이디어 충돌기 · 나에게 묻기 (내 노트 기반 Q&A)
- [x] **Phase 7** — Threads 초안 생성 · 클립보드 캡처 · 시스템 트레이 · 유튜브 자막 요약
- [x] **Phase 8** — 지식 그래프 시각화 · 관심사 트래킹 · 생산성 히트맵

## 💡 만든 이유

코딩을 몰라도 AI와 대화하며 내가 쓰고 싶은 도구를 직접 만들 수 있다는 걸 보여주고 싶었습니다.
Notion, Obsidian 같은 툴이 있지만, 내 사고방식에 맞게 기능을 고르고 조합하는 경험이 달랐습니다.
이 저장소는 "비개발자도 만들 수 있다"는 증거이자, 비슷한 시도를 하려는 사람들을 위한 참고 예시입니다.

## 📄 License

MIT

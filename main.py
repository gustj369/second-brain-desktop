import tkinter as tk
from tkinter import ttk, messagebox
import json, uuid, os, threading, re, shutil, random, time, logging
from logging.handlers import RotatingFileHandler
from typing import Optional
from datetime import datetime, date, timedelta
from collections import Counter, defaultdict

DATA_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain.json")
CONFIG_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
GEMINI_MODEL = "gemini-2.5-flash"
LOG_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain.log")
_log_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(funcName)s: %(message)s"))
logging.getLogger().addHandler(_log_handler)
logging.getLogger().setLevel(logging.ERROR)

BG       = "#1e1e1e"
BG2      = "#252526"
BG3      = "#2d2d2d"
ACCENT   = "#4fc3f7"
TEXT     = "#d4d4d4"
TEXT_DIM = "#858585"
BORDER   = "#3c3c3c"
SEL      = "#094771"

TOAST_TIMEOUT_MS  = 8000
CLIPBOARD_MIN_LEN = 50

_NOTE_DEFAULTS = {
    "title": "", "content": "", "tags": [], "type": "note",
    "url": "", "reviewed_at": None, "review_count": 0,
}

def _normalize_note(note):
    """오래된·손상된 노트 필드를 안전하게 보정."""
    for k, v in _NOTE_DEFAULTS.items():
        if k not in note:
            note[k] = v
    if not isinstance(note.get("tags"), list):
        note["tags"] = []
    for ts in ("created_at", "updated_at"):
        if ts not in note or not note[ts]:
            note[ts] = datetime.now().isoformat(timespec="seconds")
    return note

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            raw["notes"] = [_normalize_note(n) for n in raw.get("notes", [])]
            return raw
        except Exception as e:
            logging.error(e, exc_info=True)
            # 손상된 파일 백업 후 빈 데이터로 시작
            backup = DATA_FILE + ".corrupt." + datetime.now().strftime("%Y%m%d%H%M%S")
            try:
                shutil.copy2(DATA_FILE, backup)
            except Exception as e:
                logging.error(e, exc_info=True)
            import tkinter.messagebox as _mb
            _mb.showerror(
                "데이터 파일 오류",
                f"brain.json을 읽을 수 없습니다.\n\n"
                f"손상된 파일을 백업했습니다:\n{backup}\n\n"
                f"새 데이터로 시작합니다."
            )
    return {"notes": []}

def save_data(data: dict) -> None:
    """임시 파일 저장 후 원자적 교체 — 저장 중 앱 종료 시 데이터 손상 방지."""
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(e, exc_info=True)
            return {}
    return {}

def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def fetch_url_summary(url: str) -> tuple[str, str, Optional[str]]:
    try:
        import requests
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=8)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")
        title = soup.title.string.strip() if soup.title else ""
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        body_text = " ".join(soup.get_text(separator=" ").split())[:500]
        return title, body_text, None
    except Exception as e:
        logging.error(e, exc_info=True)
        return "", "", str(e)

# ── API 키 다이얼로그 ──────────────────────────────────
class ApiKeyDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self.title("Gemini API 키 설정")
        self.geometry("520x230")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        tk.Label(self, text="🔑 Gemini API 키 입력",
                 bg=BG, fg=ACCENT, font=("Segoe UI", 13, "bold")).pack(pady=(24, 4))
        tk.Label(self, text="aistudio.google.com 에서 발급받은 키를 입력하세요.",
                 bg=BG, fg=TEXT_DIM, font=("Segoe UI", 9)).pack()
        self.entry = tk.Entry(self, show="*", bg=BG3, fg=TEXT,
                              insertbackground=TEXT, font=("Segoe UI", 11),
                              relief="flat", bd=8, width=46)
        self.entry.pack(pady=16, ipady=6)
        self.entry.bind("<Return>", lambda e: self._ok())
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack()
        tk.Button(btn_row, text="나중에", bg=BG3, fg=TEXT_DIM,
                  font=("Segoe UI", 10), relief="flat",
                  command=self.destroy).pack(side="left", ipadx=12, ipady=6, padx=(0, 8))
        tk.Button(btn_row, text="저장", bg=ACCENT, fg="#000",
                  font=("Segoe UI", 10, "bold"), relief="flat",
                  command=self._ok).pack(side="left", ipadx=18, ipady=6)
        self.grab_set()
        self.entry.focus()
        self.wait_window()

    def _ok(self):
        self.result = self.entry.get().strip()
        self.destroy()

# ── 일일 브리핑 다이얼로그 ────────────────────────────
class BriefingDialog(tk.Toplevel):
    def __init__(self, parent, notes):
        super().__init__(parent)
        self.title("☀️ 오늘의 브리핑")
        self.geometry("620x500")
        self.configure(bg=BG)
        self.resizable(False, True)
        self.transient(parent)
        self._parent = parent
        tk.Label(self, text="☀️ 오늘의 브리핑", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 14, "bold")).pack(pady=(22, 4))
        tk.Label(self, text="오늘 다시 생각해볼 노트 3개 — AI가 질문을 준비했어요",
                 bg=BG, fg=TEXT_DIM, font=("Segoe UI", 9)).pack()
        text_frame = tk.Frame(self, bg=BG3)
        text_frame.pack(fill="both", expand=True, padx=20, pady=14)
        self.result_box = tk.Text(text_frame, bg=BG3, fg=TEXT,
                                   font=("Segoe UI", 10), relief="flat", bd=0,
                                   wrap="word", padx=14, pady=12)
        vsb = ttk.Scrollbar(text_frame, command=self.result_box.yview)
        self.result_box.configure(yscrollcommand=vsb.set)
        self.result_box.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.result_box.insert("1.0", "AI가 질문을 만드는 중입니다...\n잠시 기다려주세요 ☕")
        self.result_box.configure(state="disabled")
        tk.Button(self, text="오늘 브리핑 닫기", bg=ACCENT, fg="#000",
                  font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
                  command=self.destroy).pack(pady=(0, 18), ipadx=24, ipady=8)
        self.grab_set()
        threading.Thread(target=lambda: self._fetch(notes), daemon=True).start()

    def _fetch(self, notes):
        try:
            import google.generativeai as genai
            model = genai.GenerativeModel(
                GEMINI_MODEL,
                system_instruction="당신은 지적 성장을 돕는 코치입니다. 반드시 한국어로 답변하세요."
            )
            notes_text = "\n\n".join(
                f"[노트 {i+1}] 제목: {n['title']}\n내용: {n['content'][:300]}"
                for i, n in enumerate(notes)
            )
            response = model.generate_content(
                f"다음 노트 {len(notes)}개를 읽고, 각각에 대해 오늘 다시 생각해볼 질문 1개씩을 한국어로 만들어줘.\n\n"
                f"형식: [노트 1] 제목\n질문: (내용)\n\n노트 목록:\n{notes_text}"
            )
            result = response.text
        except Exception as e:
            logging.error(e, exc_info=True)
            result = f"AI 연결 오류: {str(e)}"
        self._parent.after(0, lambda: self._update(result))

    def _update(self, text):
        if not self.winfo_exists(): return
        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", text)
        self.result_box.configure(state="disabled")

# ── 아이디어 충돌기 다이얼로그 ────────────────────────
class IdeaColliderDialog(tk.Toplevel):
    def __init__(self, parent, note_a, note_b, no_overlap):
        super().__init__(parent)
        self._parent_app = parent
        self._note_a = note_a
        self._note_b = note_b
        self._result_text = ""
        self.title("💥 아이디어 충돌기")
        self.geometry("640x560")
        self.configure(bg=BG)
        self.resizable(False, True)
        self.transient(parent)
        tk.Label(self, text="💥 아이디어 충돌기", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 14, "bold")).pack(pady=(20, 2))
        if not no_overlap:
            tk.Label(self, text="⚠️ 태그가 겹치지 않는 노트를 찾지 못해 임의로 선택했습니다.",
                     bg=BG, fg="#f48771", font=("Segoe UI", 8)).pack()
        notes_frame = tk.Frame(self, bg=BG3)
        notes_frame.pack(fill="x", padx=20, pady=10)
        tk.Label(notes_frame, text=f"📝  {note_a['title']}", bg=BG3, fg=TEXT,
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(notes_frame, text="⚡ vs ⚡", bg=BG3, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack()
        tk.Label(notes_frame, text=f"📝  {note_b['title']}", bg=BG3, fg=TEXT,
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=14, pady=(2, 10))
        text_frame = tk.Frame(self, bg=BG3)
        text_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        self.result_box = tk.Text(text_frame, bg=BG3, fg=TEXT,
                                   font=("Segoe UI", 10), relief="flat", bd=0,
                                   wrap="word", padx=12, pady=12)
        vsb = ttk.Scrollbar(text_frame, command=self.result_box.yview)
        self.result_box.configure(yscrollcommand=vsb.set)
        self.result_box.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.result_box.insert("1.0", "AI가 창의적인 아이디어를 만드는 중입니다... ⚡")
        self.result_box.configure(state="disabled")
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(pady=(0, 18))
        tk.Button(btn_row, text="닫기", bg=BG3, fg=TEXT_DIM,
                  font=("Segoe UI", 10), relief="flat", cursor="hand2",
                  command=self.destroy).pack(side="left", ipadx=14, ipady=6, padx=(0, 10))
        self.save_btn = tk.Button(btn_row, text="💾 이 아이디어 노트로 저장",
                                   bg=ACCENT, fg="#000",
                                   font=("Segoe UI", 10, "bold"), relief="flat",
                                   cursor="hand2", state="disabled",
                                   command=self._save_idea)
        self.save_btn.pack(side="left", ipadx=14, ipady=6)
        self.grab_set()
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            import google.generativeai as genai
            model = genai.GenerativeModel(
                GEMINI_MODEL,
                system_instruction=(
                    "당신은 창의적인 아이디어 전문가입니다. "
                    "전혀 다른 두 개념을 연결하여 혁신적인 아이디어를 만들어냅니다. "
                    "반드시 한국어로 답변하세요."
                )
            )
            prompt = (
                "다음 두 노트는 전혀 다른 주제입니다.\n"
                "억지로라도 연결해서 새로운 아이디어나 인사이트를 한국어로 3가지 제시해줘.\n"
                "창의적일수록 좋아.\n\n"
                f"[노트 A] {self._note_a['title']}\n{self._note_a['content'][:400]}\n\n"
                f"[노트 B] {self._note_b['title']}\n{self._note_b['content'][:400]}"
            )
            response = model.generate_content(prompt)
            self._result_text = response.text
        except Exception as e:
            logging.error(e, exc_info=True)
            self._result_text = f"오류: {str(e)}"
        self._parent_app.after(0, lambda: self._update(self._result_text))

    def _update(self, text):
        if not self.winfo_exists(): return
        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", text)
        self.result_box.configure(state="disabled")
        if not text.startswith("오류:"):
            self.save_btn.configure(state="normal")

    def _save_idea(self):
        title = f"💥 {self._note_a['title']} × {self._note_b['title']}"
        self._parent_app.new_note()
        self._parent_app.title_var.set(title[:80])
        self._parent_app.tags_var.set("아이디어충돌, AI생성")
        self._parent_app.content_box.delete("1.0", "end")
        self._parent_app.content_box.insert("1.0", self._result_text)
        self.destroy()

# ── Threads 초안 다이얼로그 ───────────────────────────
class ThreadsDraftDialog(tk.Toplevel):
    def __init__(self, parent, title, content):
        super().__init__(parent)
        self._parent = parent
        self._result_text = ""
        self.title("📱 Threads 초안")
        self.geometry("580x520")
        self.configure(bg=BG)
        self.resizable(False, True)
        self.transient(parent)
        tk.Label(self, text="📱 Threads 초안", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 13, "bold")).pack(pady=(20, 4))
        tk.Label(self, text="드라마틱 라이프 스타일로 생성된 포스트 초안",
                 bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8)).pack()
        text_frame = tk.Frame(self, bg=BG3)
        text_frame.pack(fill="both", expand=True, padx=20, pady=12)
        self.result_box = tk.Text(text_frame, bg=BG3, fg=TEXT,
                                   font=("Segoe UI", 11), relief="flat", bd=0,
                                   wrap="word", padx=14, pady=12)
        vsb = ttk.Scrollbar(text_frame, command=self.result_box.yview)
        self.result_box.configure(yscrollcommand=vsb.set)
        self.result_box.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.result_box.insert("1.0", "초안을 생성하는 중입니다... ✍️")
        self.result_box.configure(state="disabled")
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(pady=(0, 16))
        tk.Button(btn_row, text="닫기", bg=BG3, fg=TEXT_DIM,
                  font=("Segoe UI", 10), relief="flat", cursor="hand2",
                  command=self.destroy).pack(side="left", ipadx=14, ipady=6, padx=(0, 8))
        self.copy_btn = tk.Button(btn_row, text="📋 클립보드에 복사",
                                   bg=ACCENT, fg="#000",
                                   font=("Segoe UI", 10, "bold"), relief="flat",
                                   cursor="hand2", state="disabled",
                                   command=self._copy)
        self.copy_btn.pack(side="left", ipadx=14, ipady=6)
        self.grab_set()
        threading.Thread(target=lambda: self._fetch(title, content), daemon=True).start()

    def _fetch(self, title, content):
        try:
            import google.generativeai as genai
            model = genai.GenerativeModel(
                GEMINI_MODEL,
                system_instruction=(
                    "당신은 '드라마틱 라이프'라는 직장인 대상 Threads 계정 운영자입니다. "
                    "반드시 한국어로 답변하세요."
                )
            )
            note_content = f"제목: {title}\n\n{content[:1500]}"
            response = model.generate_content(
                "아래 노트를 바탕으로 Threads 포스트 초안을 작성해주세요.\n\n"
                "스타일 규칙:\n"
                "- 첫 줄은 멈춰서 읽게 만드는 후킹 문장\n"
                "- 말투: ~었어요, ~이에요, ~더라고요 (편안한 구어체)\n"
                "- ~합니다 체 절대 금지\n"
                "- 결론에서 교훈 강요 금지\n"
                "- 개인 경험을 자연스럽게 녹일 것\n"
                "- 3~5문단, 각 문단 2~3줄\n"
                "- 마지막 줄: 질문이나 여운을 남기는 문장\n\n"
                f"[노트 내용]\n{note_content}"
            )
            self._result_text = response.text
        except Exception as e:
            logging.error(e, exc_info=True)
            self._result_text = f"오류: {str(e)}"
        self._parent.after(0, lambda: self._update(self._result_text))

    def _update(self, text):
        if not self.winfo_exists(): return
        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", text)
        self.result_box.configure(state="disabled")
        if not text.startswith("오류:"):
            self.copy_btn.configure(state="normal")

    def _copy(self):
        try:
            import pyperclip
            pyperclip.copy(self._result_text)
        except ImportError:
            self.clipboard_clear()
            self.clipboard_append(self._result_text)
        self.copy_btn.configure(text="✓ 복사됨!")
        if self.winfo_exists():
            self.after(2000, lambda: self.copy_btn.configure(
                text="📋 클립보드에 복사") if self.winfo_exists() else None)

# ── 지식 그래프 창 ────────────────────────────────────
class KnowledgeGraphWindow(tk.Toplevel):
    def __init__(self, parent_app, notes):
        super().__init__(parent_app)
        self._app = parent_app
        self._fig = None
        self.title("🕸️ 지식 그래프")
        self.geometry("980x740")
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 헤더
        hdr = tk.Frame(self, bg=BG2, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="🕸️ 지식 그래프", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=16, pady=12)
        tk.Label(hdr,
                 text=f"노트 {len(notes)}개  ·  공통 태그로 연결  ·  노드 클릭 → 노트 열기",
                 bg=BG2, fg=TEXT_DIM, font=("Segoe UI", 8)).pack(side="left", padx=4)

        if len(notes) < 50:
            tk.Label(self,
                     text=f"💡 노트가 더 쌓이면 그래프가 풍성해져요 (현재 {len(notes)}개)",
                     bg=BG, fg=TEXT_DIM, font=("Segoe UI", 9)).pack(pady=(8, 0))

        try:
            self._build_graph(notes)
        except ImportError:
            tk.Label(self,
                     text="pip install networkx matplotlib\n을 실행한 뒤 앱을 재시작하세요.",
                     bg=BG, fg="#f48771", font=("Segoe UI", 12),
                     justify="center").pack(expand=True)

    def _build_graph(self, notes):
        import networkx as nx
        import matplotlib
        if matplotlib.get_backend().lower() != "tkagg":
            matplotlib.use("TkAgg")
        matplotlib.rcParams["font.family"] = ["Malgun Gothic", "sans-serif"]
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        # 그래프 구성
        G = nx.Graph()
        for note in notes:
            G.add_node(note["id"], title=note["title"])

        for i, n1 in enumerate(notes):
            for n2 in notes[i+1:]:
                common = len(set(n1["tags"]) & set(n2["tags"]))
                if common:
                    G.add_edge(n1["id"], n2["id"], weight=common)

        # 고립 노드 제거 (노트 많을 때)
        if len(notes) > 60:
            isolates = list(nx.isolates(G))
            G.remove_nodes_from(isolates)

        if len(G.nodes()) == 0:
            tk.Label(self,
                     text="공통 태그로 연결된 노트가 없어요.\n태그를 더 활용해보세요!",
                     bg=BG, fg=TEXT_DIM, font=("Segoe UI", 12),
                     justify="center").pack(expand=True)
            return

        # 레이아웃
        try:
            pos = nx.kamada_kawai_layout(G)
        except Exception as e:
            logging.error(e, exc_info=True)
            pos = nx.spring_layout(G, k=1.8, seed=42, iterations=60)

        # Figure
        fig = Figure(figsize=(11, 8.2), facecolor="#1e1e1e")
        ax = fig.add_subplot(111)
        ax.set_facecolor("#252526")
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

        # 엣지 그리기 (굵기 = 공통 태그 수)
        if G.edges():
            weights = [G[u][v].get("weight", 1) for u, v in G.edges()]
            max_w = max(weights)
            edge_widths = [0.6 + (w / max_w) * 4.0 for w in weights]
            nx.draw_networkx_edges(G, pos, ax=ax, width=edge_widths,
                                   edge_color="#4fc3f7", alpha=0.30)

        # 노드 크기 = 연결 수 기반
        degrees = dict(G.degree())
        node_sizes = [180 + degrees[n] * 90 for n in G.nodes()]
        nx.draw_networkx_nodes(G, pos, ax=ax,
                               node_color="#4fc3f7", node_size=node_sizes,
                               alpha=0.88, linewidths=0)

        # 라벨 (15자 초과 시 말줄임)
        id_to_note = {n["id"]: n for n in notes}
        labels = {}
        for nid in G.nodes():
            t = id_to_note[nid]["title"] if nid in id_to_note else ""
            labels[nid] = (t[:13] + "…") if len(t) > 13 else t
        nx.draw_networkx_labels(G, pos, labels, ax=ax,
                                font_size=7, font_color="#d4d4d4")

        # 캔버스 임베드
        canvas = FigureCanvasTkAgg(fig, master=self)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=6)

        self._fig = fig
        self._pos = pos
        self._id_to_note = id_to_note

        # 클릭 이벤트 — 가장 가까운 노드 선택
        def on_click(event):
            if event.inaxes != ax or event.xdata is None:
                return
            cx, cy = event.xdata, event.ydata
            xlim = ax.get_xlim()
            threshold = (xlim[1] - xlim[0]) * 0.06

            nearest_id, min_dist = None, float("inf")
            for nid, (nx_, ny_) in pos.items():
                d = ((cx - nx_)**2 + (cy - ny_)**2)**0.5
                if d < min_dist:
                    min_dist, nearest_id = d, nid

            if nearest_id and min_dist < threshold * 3 and nearest_id in id_to_note:
                def go():
                    self._app.select_note(nearest_id)
                    if self._app.state() == "withdrawn":
                        self._app.deiconify()
                    self._app.lift()
                    self._app.focus_force()
                self._app.after(0, go)

        fig.canvas.mpl_connect("button_press_event", on_click)

    def _on_close(self):
        if self._fig:
            try:
                import matplotlib.pyplot as plt
                plt.close(self._fig)
            except Exception as e:
                logging.error(e, exc_info=True)
        self.destroy()

# ── 관심사 & 히트맵 창 ───────────────────────────────
class InterestWindow(tk.Toplevel):
    def __init__(self, parent_app, notes):
        super().__init__(parent_app)
        self._fig1 = None
        self._fig2 = None
        self.title("📈 내 관심사 & 생산성")
        self.geometry("960x860")
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        hdr = tk.Frame(self, bg=BG2, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="📈 내 관심사 & 생산성 히트맵", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=16, pady=12)

        try:
            self._build(notes)
        except ImportError:
            tk.Label(self,
                     text="pip install matplotlib\n을 실행한 뒤 앱을 재시작하세요.",
                     bg=BG, fg="#f48771", font=("Segoe UI", 12),
                     justify="center").pack(expand=True)

    def _build(self, notes):
        import matplotlib
        if matplotlib.get_backend().lower() != "tkagg":
            matplotlib.use("TkAgg")
        matplotlib.rcParams["font.family"] = ["Malgun Gothic", "sans-serif"]
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.patches import Rectangle

        today = date.today()

        # ── 월별 태그 집계 ────────────────────────────
        month_tag_counts = defaultdict(lambda: defaultdict(int))
        all_tag_counts = Counter()

        for note in notes:
            try:
                dt = datetime.fromisoformat(note["created_at"])
                ym = dt.strftime("%Y-%m")
            except Exception as e:
                logging.error(e, exc_info=True)
                continue
            for tag in note["tags"]:
                month_tag_counts[ym][tag] += 1
                all_tag_counts[tag] += 1

        top_tags = [t for t, _ in all_tag_counts.most_common(10)]

        # 최근 12개월 목록
        months = []
        cur = today.replace(day=1)
        for _ in range(12):
            months.append(cur.strftime("%Y-%m"))
            if cur.month == 1:
                cur = cur.replace(year=cur.year - 1, month=12)
            else:
                cur = cur.replace(month=cur.month - 1)
        months.reverse()

        # 이번 달 최다 태그
        this_month = today.strftime("%Y-%m")
        this_counts = month_tag_counts.get(this_month, {})
        top_now = max(this_counts, key=this_counts.get) if this_counts else "없음"

        # 안내 레이블
        info = tk.Frame(self, bg=BG2)
        info.pack(fill="x")
        tk.Label(info,
                 text=f"  이번 달 가장 많이 생각한 주제 → #{top_now}",
                 bg=BG2, fg=ACCENT, font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=16, pady=8)

        # ── 누적 막대 차트 ────────────────────────────
        COLORS = [
            "#4fc3f7","#81c784","#ffb74d","#f06292","#ba68c8",
            "#4db6ac","#ffd54f","#ff8a65","#90a4ae","#a5d6a7",
        ]
        month_labels = [f"{int(m[5:])}월" for m in months]

        fig1 = Figure(figsize=(10.5, 3.8), facecolor="#1e1e1e")
        ax1 = fig1.add_subplot(111)
        ax1.set_facecolor("#252526")
        ax1.tick_params(colors="#858585", labelsize=8)
        for sp in ax1.spines.values():
            sp.set_color("#3c3c3c")

        if top_tags and months:
            bottom = [0] * len(months)
            for i, tag in enumerate(top_tags):
                vals = [month_tag_counts[m].get(tag, 0) for m in months]
                ax1.bar(month_labels, vals, bottom=bottom,
                        label=f"#{tag}", color=COLORS[i % len(COLORS)],
                        alpha=0.87, width=0.68)
                bottom = [b + v for b, v in zip(bottom, vals)]
            ax1.set_title("월별 태그 사용 빈도 (상위 10개)",
                          color="#d4d4d4", fontsize=10, pad=8)
            ax1.set_ylabel("노트 수", color="#858585", fontsize=8)
            ax1.tick_params(axis="x", rotation=40, labelsize=8)
            ax1.legend(loc="upper left", fontsize=7, framealpha=0.3,
                       facecolor="#2d2d2d", edgecolor="#3c3c3c",
                       labelcolor="#d4d4d4", ncol=5)
        else:
            ax1.text(0.5, 0.5, "태그가 있는 노트를 더 작성해보세요!",
                     transform=ax1.transAxes, ha="center", va="center",
                     color="#858585", fontsize=12)

        c1 = FigureCanvasTkAgg(fig1, master=self)
        c1.draw()
        c1.get_tk_widget().pack(fill="x", padx=8, pady=(4, 0))
        self._fig1 = fig1

        # ── 히트맵 통계 바 ────────────────────────────
        day_counts = defaultdict(int)
        for note in notes:
            try:
                d = datetime.fromisoformat(note["created_at"]).date()
                day_counts[d] += 1
            except Exception as e:
                logging.error(e, exc_info=True)

        if day_counts:
            best_day   = max(day_counts, key=day_counts.get)
            best_count = day_counts[best_day]
            # 최장 연속 기록
            max_streak = cur_streak = 0
            for i in range(365):
                d = today - timedelta(days=i)
                if day_counts.get(d, 0) > 0:
                    cur_streak += 1
                    max_streak  = max(max_streak, cur_streak)
                else:
                    cur_streak = 0
        else:
            best_day = today; best_count = 0; max_streak = 0

        stat_bar = tk.Frame(self, bg=BG3)
        stat_bar.pack(fill="x", padx=8, pady=(10, 2))
        tk.Label(stat_bar, text="📊 생산성 히트맵 (최근 1년)",
                 bg=BG3, fg=ACCENT, font=("Segoe UI", 9, "bold")).pack(
            side="left", padx=12, pady=6)
        tk.Label(stat_bar,
                 text=f"🏆 최다 작성일: {best_day.strftime('%m/%d')} ({best_count}개)   "
                      f"⚡ 최장 연속: {max_streak}일",
                 bg=BG3, fg=TEXT_DIM, font=("Segoe UI", 8)).pack(
            side="right", padx=12, pady=6)

        # ── GitHub 잔디 히트맵 ────────────────────────
        # 52주 전 월요일부터 오늘까지
        cur_monday = today - timedelta(days=today.weekday())
        start_date = cur_monday - timedelta(weeks=52)

        # weeks × days 데이터
        weeks_data = []
        week_dates = []
        d = start_date
        while d <= today + timedelta(days=6 - today.weekday()):
            week = []
            wdates = []
            for _ in range(7):
                week.append(day_counts.get(d, 0))
                wdates.append(d)
                d += timedelta(days=1)
            weeks_data.append(week)
            week_dates.append(wdates)

        max_c = max((max(w) for w in weeks_data), default=1) or 1

        def _heat_color(count):
            if count == 0:
                return "#2d2d2d"
            t = min(count / max_c, 1.0)
            r = int(0x0d + t * (0x4f - 0x0d))
            g = int(0x3a + t * (0xc3 - 0x3a))
            b = int(0x4f + t * (0xf7 - 0x4f))
            return f"#{r:02x}{g:02x}{b:02x}"

        NUM_WEEKS = len(weeks_data)
        CELL = 0.84
        GAP  = 0.16
        STEP = CELL + GAP

        fig2 = Figure(figsize=(10.5, 2.4), facecolor="#1e1e1e")
        ax2 = fig2.add_subplot(111)
        ax2.set_facecolor("#1e1e1e")
        ax2.set_xticks([]); ax2.set_yticks([])
        for sp in ax2.spines.values():
            sp.set_visible(False)

        # 셀 그리기
        for wi, week in enumerate(weeks_data):
            for di, count in enumerate(week):
                x = wi * STEP
                y = (6 - di) * STEP   # di=0(월) → y 최상단
                rect = Rectangle((x, y), CELL, CELL,
                                  color=_heat_color(count), linewidth=0)
                ax2.add_patch(rect)

        total_w = NUM_WEEKS * STEP
        total_h = 7 * STEP
        ax2.set_xlim(-1.2, total_w + 0.2)
        ax2.set_ylim(-0.4, total_h + 1.0)

        # 요일 레이블
        for di, name in enumerate(["월","화","수","목","금","토","일"]):
            y = (6 - di) * STEP + CELL / 2
            ax2.text(-0.15, y, name, color="#858585", fontsize=6.5,
                     va="center", ha="right")

        # 월 레이블
        prev_month = None
        for wi, wdates in enumerate(week_dates):
            m = wdates[0].month
            if m != prev_month:
                ax2.text(wi * STEP, total_h + 0.2,
                         f"{m}월", color="#858585", fontsize=7,
                         va="bottom", ha="left")
                prev_month = m

        c2 = FigureCanvasTkAgg(fig2, master=self)
        c2.draw()
        c2.get_tk_widget().pack(fill="x", padx=8, pady=(0, 10))
        self._fig2 = fig2

    def _on_close(self):
        try:
            import matplotlib.pyplot as plt
            if self._fig1: plt.close(self._fig1)
            if self._fig2: plt.close(self._fig2)
        except Exception as e:
            logging.error(e, exc_info=True)
        self.destroy()

# ── 앱 ───────────────────────────────────────────────
class BrainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("세컨 브레인")
        self.geometry("1200x820")
        self.minsize(1200, 820)
        self.configure(bg=BG)

        config = load_config()
        self.data = load_data()
        self.selected_id = None
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_list())
        self.note_type = tk.StringVar(value="note")
        self.api_client = None
        self.clipboard_enabled = tk.BooleanVar(value=config.get("clipboard_enabled", True))
        self._clipboard_active = config.get("clipboard_enabled", True)   # 스레드 안전 bool
        self._last_clipboard = ""
        self._active_toast = None
        self._monitor_running = True
        self.tray_icon = None

        self._build_ui()
        self._init_api()
        self.refresh_list()
        self.after(600, self._run_briefing)
        self._start_tray()
        self._start_clipboard_monitor()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── API ──────────────────────────────────────────
    def _init_api(self):
        config = load_config()
        api_key = config.get("api_key", "")
        if not api_key:
            dlg = ApiKeyDialog(self)
            api_key = dlg.result or ""
            if api_key:
                config["api_key"] = api_key
                save_config(config)
        if api_key:
            self._setup_gemini(api_key)

    def _setup_gemini(self, api_key):
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.api_client = genai
        except ImportError:
            messagebox.showerror("패키지 없음",
                "pip install google-generativeai 을 실행한 뒤 앱을 재시작하세요.")

    def _reset_api_key(self):
        dlg = ApiKeyDialog(self)
        if dlg.result:
            config = load_config()
            config["api_key"] = dlg.result
            save_config(config)
            self._setup_gemini(dlg.result)
            if self.api_client:
                messagebox.showinfo("완료", "API 키가 업데이트되었습니다.")

    # ── 지식 그래프 ───────────────────────────────────
    def _show_graph(self):
        KnowledgeGraphWindow(self, self.data["notes"])

    # ── 관심사 & 히트맵 ──────────────────────────────
    def _show_interests(self):
        InterestWindow(self, self.data["notes"])

    # ── 시스템 트레이 ─────────────────────────────────
    def _start_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw

            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([0, 0, 63, 63], fill=(30, 30, 30, 255))
            draw.ellipse([10, 10, 54, 54], fill=(79, 195, 247, 255))

            menu = pystray.Menu(
                pystray.MenuItem("세컨 브레인 열기", self._show_window),
                pystray.MenuItem(
                    "클립보드 캡처",
                    lambda icon, item: self.after(0, self._toggle_clipboard_setting),
                    checked=lambda item: self.clipboard_enabled.get()
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("종료", self._quit_app),
            )
            self.tray_icon = pystray.Icon("SecondBrain", img, "🧠 세컨 브레인", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except ImportError:
            pass

    def _show_window(self, icon=None, item=None):
        self.after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    def _on_close(self):
        if self.tray_icon:
            self.withdraw()
        else:
            self._quit_app()

    def _quit_app(self, icon=None, item=None):
        self._monitor_running = False
        if self.tray_icon:
            self.tray_icon.stop()
        self.after(0, self.destroy)

    # ── 클립보드 캡처 ─────────────────────────────────
    def _toggle_clipboard_setting(self):
        val = not self.clipboard_enabled.get()
        self.clipboard_enabled.set(val)
        self._clipboard_active = val          # 백그라운드 스레드용 plain bool 동기화
        config = load_config()
        config["clipboard_enabled"] = val
        save_config(config)
        if val:
            self.clipboard_toggle_btn.configure(
                text="📋 캡처 ON", bg="#1b3a2a", fg="#81c784")
        else:
            self.clipboard_toggle_btn.configure(
                text="📋 캡처 OFF", bg=BG3, fg=TEXT_DIM)

    def _start_clipboard_monitor(self):
        try:
            import pyperclip
        except ImportError:
            return

        def monitor():
            while self._monitor_running:
                try:
                    current = pyperclip.paste()
                    if current != self._last_clipboard:
                        # Tkinter 변수 대신 plain bool 사용 — 백그라운드 스레드 안전
                        if self._clipboard_active and len(current.strip()) >= CLIPBOARD_MIN_LEN:
                            self.after(0, lambda t=current: self._show_clipboard_toast(t))
                        self._last_clipboard = current
                except Exception as e:
                    logging.error(e, exc_info=True)
                time.sleep(1)

        threading.Thread(target=monitor, daemon=True).start()

    def _show_clipboard_toast(self, text):
        if self._active_toast:
            try:
                if self._active_toast.winfo_exists():
                    return
            except Exception as e:
                logging.error(e, exc_info=True)

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        toast = tk.Toplevel()
        toast.geometry(f"360x95+{sw - 376}+{sh - 130}")
        toast.configure(bg=BG2)
        toast.attributes("-topmost", True)
        toast.overrideredirect(True)
        self._active_toast = toast

        preview = text[:42] + "..." if len(text) > 42 else text
        tk.Label(toast, text="📋 클립보드에 복사됨 — 노트로 저장할까요?",
                 bg=BG2, fg=ACCENT, font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=14, pady=(10, 2))
        tk.Label(toast, text=f'"{preview}"', bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=14)

        btn_row = tk.Frame(toast, bg=BG2)
        btn_row.pack(anchor="e", padx=14, pady=6)
        tk.Button(btn_row, text="무시", bg=BG3, fg=TEXT_DIM,
                  font=("Segoe UI", 8), relief="flat", cursor="hand2",
                  command=toast.destroy).pack(side="left", padx=(0, 6), ipadx=8, ipady=3)
        tk.Button(btn_row, text="저장", bg=ACCENT, fg="#000",
                  font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                  command=lambda: self._save_from_clipboard(text, toast)
                  ).pack(side="left", ipadx=8, ipady=3)

        toast.after(TOAST_TIMEOUT_MS, lambda: toast.destroy() if toast.winfo_exists() else None)

    def _save_from_clipboard(self, text, toast):
        toast.destroy()
        self._show_window()
        first_line = (text.strip().splitlines() or [""])[0]
        auto_title = (first_line[:50].rsplit(" ", 1)[0] or first_line[:50]).strip()
        self.after(100, lambda: (
            self.new_note(),
            self.title_var.set(auto_title),
            self.content_box.delete("1.0", "end"),
            self.content_box.insert("1.0", text),
            self.status_label.configure(text="클립보드에서 가져옴")
        ))

    # ── 일일 브리핑 ──────────────────────────────────
    def _run_briefing(self):
        if not self.api_client or len(self.data["notes"]) < 10:
            return
        config = load_config()
        if config.get("last_briefing_date") == str(date.today()):
            return
        selected = random.sample(self.data["notes"], 3)
        BriefingDialog(self, selected)
        config["last_briefing_date"] = str(date.today())
        save_config(config)

    # ── 아이디어 충돌기 ──────────────────────────────
    def _idea_collider(self):
        if not self._check_api(): return
        if len(self.data["notes"]) < 2:
            messagebox.showinfo("알림", "아이디어 충돌을 위해 노트가 2개 이상 필요합니다.")
            return
        note_a, note_b, no_overlap = self._find_non_overlapping_pair()
        IdeaColliderDialog(self, note_a, note_b, no_overlap)

    def _find_non_overlapping_pair(self):
        notes = self.data["notes"]
        for _ in range(100):
            a, b = random.sample(notes, 2)
            if not (set(a["tags"]) & set(b["tags"])):
                return a, b, True
        a, b = random.sample(notes, 2)
        return a, b, False

    # ── Threads 초안 ──────────────────────────────────
    def _threads_draft(self):
        if not self._check_api(): return
        title   = self.title_var.get().strip()
        content = self.content_box.get("1.0", "end").strip()
        if not title and not content:
            messagebox.showwarning("알림", "노트 내용을 먼저 입력하세요."); return
        ThreadsDraftDialog(self, title, content)

    # ── 나에게 묻기 ───────────────────────────────────
    def _ask_brain(self):
        if not self._check_api(): return
        question = self.ask_var.get().strip()
        if not question:
            messagebox.showwarning("알림", "질문을 입력하세요."); return
        self.ask_btn.configure(text="생각 중...", state="disabled")
        self.status_label.configure(text="나에게 묻는 중...")
        notes = self.data["notes"]
        truncated = len(notes) > 200
        notes_to_send = sorted(notes, key=lambda n: n["updated_at"], reverse=True)[:200]
        notice = "※ 최근 200개 노트 기준으로 답변합니다.\n\n" if truncated else ""
        notes_context = "\n".join(
            f"- [{n['title']}]: {n['content'][:200]}" for n in notes_to_send)
        q = question

        def worker():
            try:
                import google.generativeai as genai
                model = genai.GenerativeModel(
                    GEMINI_MODEL,
                    system_instruction=(
                        "당신은 아래 노트들을 작성한 사람입니다. "
                        "이 사람의 사고방식과 관심사를 바탕으로 질문에 답해주세요. "
                        "없는 내용은 지어내지 말고 '관련 노트가 없습니다'라고 답하세요. "
                        "답변 마지막에 '📎 참고 노트:' 항목으로 근거 노트 제목을 나열해주세요. "
                        "반드시 한국어로 답변하세요."
                    )
                )
                response = model.generate_content(
                    f"[노트 목록]\n{notes_context}\n\n[질문]\n{q}")
                self.after(0, lambda: self._done_ask(notice + response.text))
            except Exception as e:
                logging.error(e, exc_info=True)
                self.after(0, lambda: self._done_ask_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _done_ask(self, text):
        self.ask_btn.configure(text="질문하기", state="normal")
        self.ask_var.set("")
        self.status_label.configure(text="답변 완료 ✓")
        self._show_ai_result("🧠 나에게 묻기 답변", text)

    def _done_ask_error(self, err):
        self.ask_btn.configure(text="질문하기", state="normal")
        self._ai_error(err)

    # ── 유튜브 자막 요약 ──────────────────────────────
    def _is_youtube_url(self, url):
        return "youtube.com/watch" in url or "youtu.be/" in url

    def _extract_youtube_id(self, url):
        patterns = [
            r"youtu\.be/([a-zA-Z0-9_-]{11})",
            r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
            r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            m = re.search(pattern, url)
            if m:
                return m.group(1)
        return None

    def _on_url_change(self, *args):
        if self.note_type.get() == "link":
            url = self.url_var.get()
            if self._is_youtube_url(url):
                if not self.youtube_btn.winfo_ismapped():
                    self.youtube_btn.pack(side="left", padx=(6, 0), ipadx=8, ipady=5)
            else:
                self.youtube_btn.pack_forget()

    def _youtube_summary(self):
        if not self._check_api(): return
        url = self.url_var.get().strip()
        vid = self._extract_youtube_id(url)
        if not vid:
            messagebox.showerror("오류", "YouTube 영상 ID를 찾을 수 없습니다."); return

        self.youtube_btn.configure(text="자막 추출 중...", state="disabled")
        self.status_label.configure(text="YouTube 자막 추출 중...")

        def worker():
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                try:
                    segments = YouTubeTranscriptApi.get_transcript(vid, languages=["ko", "en"])
                except Exception:
                    segments = YouTubeTranscriptApi.get_transcript(vid)
                transcript = " ".join(s["text"] for s in segments)[:5000]

                import google.generativeai as genai
                model = genai.GenerativeModel(
                    GEMINI_MODEL,
                    system_instruction=(
                        "당신은 유튜브 영상 내용을 분석하는 전문가입니다. "
                        "반드시 한국어로 답변하세요."
                    )
                )
                response = model.generate_content(
                    "다음 유튜브 영상 자막을 읽고 핵심 내용을 한국어로 요약해줘.\n"
                    "형식: 핵심 주제 1줄 + 주요 포인트 5개 (각 1~2줄)\n\n"
                    f"자막:\n{transcript}"
                )
                self.after(0, lambda: self._done_youtube(response.text))
            except Exception as e:
                logging.error(e, exc_info=True)
                self.after(0, lambda: self._youtube_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _done_youtube(self, text):
        self.youtube_btn.configure(text="📺 자막 요약", state="normal")
        self.status_label.configure(text="자막 요약 완료 ✓")
        self.content_box.delete("1.0", "end")
        self.content_box.insert("1.0", text)

    def _youtube_error(self, err):
        self.youtube_btn.configure(text="📺 자막 요약", state="normal")
        self.status_label.configure(text="자막 추출 실패")
        messagebox.showerror("오류",
            f"자막 추출 실패:\n{err}\n\n자막이 없거나 비공개 영상일 수 있어요.")

    # ── 망각 방지 복습 ────────────────────────────────
    def _days_since_review(self, note):
        ref = note.get("reviewed_at") or note.get("created_at", "")
        if not ref:
            return 0
        try:
            return (date.today() - datetime.fromisoformat(ref).date()).days
        except Exception as e:
            logging.error(e, exc_info=True)
            return 0

    def _mark_reviewed(self):
        if not self.selected_id: return
        now = datetime.now().isoformat(timespec="seconds")
        for note in self.data["notes"]:
            if note["id"] == self.selected_id:
                note["reviewed_at"] = now
                note["review_count"] = note.get("review_count", 0) + 1
                break
        save_data(self.data)
        self.review_bar.pack_forget()
        self.status_label.configure(text="복습 완료 ✓")
        self.refresh_list()

    # ── UI 빌드 ──────────────────────────────────────
    def _build_ui(self):
        header = tk.Frame(self, bg=BG2, height=48)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="🧠 세컨 브레인", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=20, pady=10)
        self.stats_label = tk.Label(header, text="", bg=BG2, fg=TEXT_DIM,
                                     font=("Segoe UI", 9))
        self.stats_label.pack(side="left", padx=(4, 0), pady=10)

        # 우측 버튼들 (오른쪽 → 왼쪽 순으로 pack)
        tk.Button(header, text="API 키 설정", bg=BG3, fg=TEXT_DIM,
                  font=("Segoe UI", 8), relief="flat",
                  command=self._reset_api_key).pack(
            side="right", padx=(8, 16), pady=13, ipadx=8, ipady=2)
        tk.Button(header, text="💾 백업", bg=BG3, fg=TEXT_DIM,
                  font=("Segoe UI", 8), relief="flat",
                  command=self._backup).pack(side="right", pady=13, ipadx=8, ipady=2)
        tk.Button(header, text="💥 아이디어 충돌", bg="#2a1b2a", fg="#ce93d8",
                  font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                  command=self._idea_collider).pack(
            side="right", padx=(0, 8), pady=13, ipadx=10, ipady=2)

        clip_bg  = "#1b3a2a" if self.clipboard_enabled.get() else BG3
        clip_fg  = "#81c784" if self.clipboard_enabled.get() else TEXT_DIM
        clip_txt = "📋 캡처 ON" if self.clipboard_enabled.get() else "📋 캡처 OFF"
        self.clipboard_toggle_btn = tk.Button(
            header, text=clip_txt, bg=clip_bg, fg=clip_fg,
            font=("Segoe UI", 8), relief="flat", cursor="hand2",
            command=self._toggle_clipboard_setting)
        self.clipboard_toggle_btn.pack(side="right", padx=(0, 8), pady=13, ipadx=8, ipady=2)

        # ★ 신규: 관심사 & 그래프 버튼
        tk.Button(header, text="📈 관심사", bg="#1a2030", fg="#ffb74d",
                  font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                  command=self._show_interests).pack(
            side="right", padx=(0, 8), pady=13, ipadx=10, ipady=2)
        tk.Button(header, text="🕸️ 지식 그래프", bg="#1a1530", fg="#ba68c8",
                  font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                  command=self._show_graph).pack(
            side="right", padx=(0, 8), pady=13, ipadx=10, ipady=2)

        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True)

        left = tk.Frame(main, bg=BG2, width=340)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._build_left(left)

        tk.Frame(main, bg=BORDER, width=1).pack(side="left", fill="y")

        right = tk.Frame(main, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self._build_right(right)

    def _build_left(self, parent):
        search_frame = tk.Frame(parent, bg=BG2)
        search_frame.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(search_frame, text="전체 검색  (제목 · 본문 · 태그)",
                 bg=BG2, fg=TEXT_DIM, font=("Segoe UI", 9)).pack(anchor="w")
        tk.Entry(search_frame, textvariable=self.search_var,
                 bg=BG3, fg=TEXT, insertbackground=TEXT,
                 relief="flat", font=("Segoe UI", 10), bd=6
                 ).pack(fill="x", ipady=4)

        tk.Button(parent, text="＋  새 노트", bg=ACCENT, fg="#000000",
                  font=("Segoe UI", 10, "bold"), relief="flat",
                  activebackground="#81d4fa", cursor="hand2",
                  command=self.new_note).pack(fill="x", padx=12, pady=(0, 10), ipady=6)

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x")

        cloud_outer = tk.Frame(parent, bg=BG2)
        cloud_outer.pack(fill="x", side="bottom")
        tk.Frame(cloud_outer, bg=BORDER, height=1).pack(fill="x")
        tk.Label(cloud_outer, text="태그 클라우드", bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=12, pady=(6, 2))
        self.tag_cloud_inner = tk.Frame(cloud_outer, bg=BG2)
        self.tag_cloud_inner.pack(fill="x", padx=12, pady=(0, 8))

        list_wrap = tk.Frame(parent, bg=BG2)
        list_wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(list_wrap, bg=BG2, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_wrap, orient="vertical", command=self.canvas.yview)
        self.scroll_inner = tk.Frame(self.canvas, bg=BG2)
        self.scroll_inner.bind("<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scroll_inner, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<MouseWheel>",
            lambda e: self.canvas.yview_scroll(-1*(e.delta//120), "units"))

    def _build_right(self, parent):
        self.right_parent = parent
        pad = dict(padx=24, pady=0)

        # 타입
        type_frame = tk.Frame(parent, bg=BG)
        type_frame.pack(anchor="w", padx=24, pady=(14, 6))
        tk.Label(type_frame, text="타입", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 12))
        for val, label in [("note", "📝  노트"), ("link", "🔗  링크")]:
            tk.Radiobutton(type_frame, text=label, variable=self.note_type,
                           value=val, bg=BG, fg=TEXT, selectcolor=BG3,
                           activebackground=BG, activeforeground=ACCENT,
                           font=("Segoe UI", 10), cursor="hand2",
                           command=self._toggle_link_row).pack(side="left", padx=(0, 16))

        # URL 행
        self.url_row = tk.Frame(parent, bg=BG)
        tk.Label(self.url_row, text="URL", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w")
        url_input_row = tk.Frame(self.url_row, bg=BG)
        url_input_row.pack(fill="x")
        self.url_var = tk.StringVar()
        self.url_var.trace_add("write", self._on_url_change)
        tk.Entry(url_input_row, textvariable=self.url_var,
                 bg=BG3, fg=TEXT, insertbackground=TEXT,
                 font=("Segoe UI", 10), relief="flat", bd=8
                 ).pack(side="left", fill="x", expand=True, ipady=5)
        self.fetch_btn = tk.Button(url_input_row, text="요약 가져오기",
                                   bg="#37474f", fg=ACCENT,
                                   font=("Segoe UI", 9, "bold"), relief="flat",
                                   activebackground="#455a64", cursor="hand2",
                                   command=self._fetch_summary)
        self.fetch_btn.pack(side="left", padx=(8, 0), ipadx=10, ipady=5)
        self.youtube_btn = tk.Button(url_input_row, text="📺 자막 요약",
                                     bg="#1a1a2e", fg="#ff6b6b",
                                     font=("Segoe UI", 9, "bold"), relief="flat",
                                     activebackground="#2a1a3e", cursor="hand2",
                                     command=self._youtube_summary)

        # 제목
        tk.Label(parent, text="제목", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=24, pady=(12, 2))
        self.title_var = tk.StringVar()
        tk.Entry(parent, textvariable=self.title_var,
                 bg=BG3, fg=TEXT, insertbackground=TEXT,
                 font=("Segoe UI", 13, "bold"), relief="flat", bd=8
                 ).pack(fill="x", **pad, ipady=6)

        # 태그
        tk.Label(parent, text="태그 (쉼표로 구분)", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=24, pady=(12, 2))
        self.tags_var = tk.StringVar()
        tk.Entry(parent, textvariable=self.tags_var,
                 bg=BG3, fg=TEXT, insertbackground=TEXT,
                 font=("Segoe UI", 10), relief="flat", bd=8
                 ).pack(fill="x", **pad, ipady=4)

        # 복습 알림 바
        self.review_bar = tk.Frame(parent, bg="#1b2d1b")
        self.review_bar_label = tk.Label(self.review_bar, text="", bg="#1b2d1b",
                                          fg="#81c784", font=("Segoe UI", 9))
        self.review_bar_label.pack(side="left", padx=(14, 8), pady=7)
        tk.Button(self.review_bar, text="✅ 복습 완료", bg="#1b3a2a", fg="#81c784",
                  font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                  command=self._mark_reviewed).pack(side="right", padx=12, pady=5,
                                                    ipadx=10, ipady=3)

        # 본문
        self.content_label = tk.Label(parent, text="본문", bg=BG, fg=TEXT_DIM,
                                       font=("Segoe UI", 9))
        self.content_label.pack(anchor="w", padx=24, pady=(12, 2))
        text_frame = tk.Frame(parent, bg=BG)
        text_frame.pack(fill="both", expand=True, padx=24)
        self.content_box = tk.Text(text_frame, bg=BG3, fg=TEXT, insertbackground=TEXT,
                                   font=("Segoe UI", 11), relief="flat", bd=0,
                                   wrap="word", padx=10, pady=10,
                                   selectbackground=SEL)
        vsb = ttk.Scrollbar(text_frame, command=self.content_box.yview)
        self.content_box.configure(yscrollcommand=vsb.set)
        self.content_box.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # AI 버튼
        ai_row = tk.Frame(parent, bg=BG)
        ai_row.pack(fill="x", padx=24, pady=(8, 0))
        tk.Label(ai_row, text="AI", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 10))
        self.keywords_btn = tk.Button(ai_row, text="🔗 연결고리 찾기",
                                      bg="#1b3a2a", fg="#81c784",
                                      font=("Segoe UI", 9, "bold"), relief="flat",
                                      activebackground="#2a4a3a", cursor="hand2",
                                      command=self._find_keywords)
        self.keywords_btn.pack(side="left", ipadx=10, ipady=5, padx=(0, 8))
        self.similar_btn = tk.Button(ai_row, text="🔍 비슷한 노트 찾기",
                                     bg="#1b2a3a", fg="#64b5f6",
                                     font=("Segoe UI", 9, "bold"), relief="flat",
                                     activebackground="#2a3a4a", cursor="hand2",
                                     command=self._find_similar)
        self.similar_btn.pack(side="left", ipadx=10, ipady=5, padx=(0, 8))
        tk.Button(ai_row, text="📱 Threads 초안",
                  bg="#1a1030", fg="#a78bfa",
                  font=("Segoe UI", 9, "bold"), relief="flat",
                  activebackground="#2a2040", cursor="hand2",
                  command=self._threads_draft).pack(side="left", ipadx=10, ipady=5)

        # AI 결과 영역
        self.ai_result_frame = tk.Frame(parent, bg=BG3)
        ai_result_header = tk.Frame(self.ai_result_frame, bg=BG3)
        ai_result_header.pack(fill="x", padx=12, pady=(8, 2))
        self.ai_result_title = tk.Label(ai_result_header, text="AI 분석 결과",
                                         bg=BG3, fg=ACCENT, font=("Segoe UI", 9, "bold"))
        self.ai_result_title.pack(side="left")
        tk.Button(ai_result_header, text="✕", bg=BG3, fg=TEXT_DIM,
                  font=("Segoe UI", 8), relief="flat", bd=0, cursor="hand2",
                  command=self._hide_ai_result).pack(side="right")
        result_text_wrap = tk.Frame(self.ai_result_frame, bg=BG3)
        result_text_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.ai_result_box = tk.Text(result_text_wrap, bg=BG3, fg=TEXT,
                                      font=("Segoe UI", 10), relief="flat", bd=0,
                                      wrap="word", padx=8, pady=6, height=7,
                                      state="disabled")
        ai_vsb = ttk.Scrollbar(result_text_wrap, command=self.ai_result_box.yview)
        self.ai_result_box.configure(yscrollcommand=ai_vsb.set)
        self.ai_result_box.pack(side="left", fill="both", expand=True)
        ai_vsb.pack(side="right", fill="y")

        # 저장/삭제
        self.btn_row = tk.Frame(parent, bg=BG)
        self.btn_row.pack(fill="x", padx=24, pady=(8, 4))
        self.status_label = tk.Label(self.btn_row, text="", bg=BG, fg=TEXT_DIM,
                                     font=("Segoe UI", 9))
        self.status_label.pack(side="left")
        tk.Button(self.btn_row, text="삭제", bg=BG3, fg="#f48771",
                  font=("Segoe UI", 10), relief="flat", bd=0,
                  activebackground=BORDER, cursor="hand2",
                  command=self.delete_note).pack(side="right", padx=(8, 0), ipadx=14, ipady=6)
        tk.Button(self.btn_row, text="저장  ✓", bg="#388e3c", fg="#ffffff",
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  activebackground="#43a047", cursor="hand2",
                  command=self.save_note).pack(side="right", ipadx=14, ipady=6)

        # 나에게 묻기
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x")
        ask_outer = tk.Frame(parent, bg=BG2)
        ask_outer.pack(fill="x")
        ask_inner = tk.Frame(ask_outer, bg=BG2)
        ask_inner.pack(fill="x", padx=24, pady=8)
        tk.Label(ask_inner, text="🧠 나에게 묻기", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        ask_row = tk.Frame(ask_inner, bg=BG2)
        ask_row.pack(fill="x")
        self.ask_var = tk.StringVar()
        self.ask_entry = tk.Entry(ask_row, textvariable=self.ask_var,
                                   bg=BG3, fg=TEXT, insertbackground=TEXT,
                                   font=("Segoe UI", 10), relief="flat", bd=8)
        self.ask_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.ask_entry.bind("<Return>", lambda e: self._ask_brain())
        self.ask_btn = tk.Button(ask_row, text="질문하기", bg="#2a2a3a", fg=ACCENT,
                                  font=("Segoe UI", 9, "bold"), relief="flat",
                                  cursor="hand2", command=self._ask_brain)
        self.ask_btn.pack(side="left", padx=(8, 0), ipadx=10, ipady=5)

        self._toggle_link_row()

    # ── AI 결과 ───────────────────────────────────────
    def _hide_ai_result(self):
        self.ai_result_frame.pack_forget()

    def _show_ai_result(self, title, text):
        self.ai_result_title.configure(text=title)
        self.ai_result_box.configure(state="normal")
        self.ai_result_box.delete("1.0", "end")
        self.ai_result_box.insert("1.0", text)
        self.ai_result_box.configure(state="disabled")
        self.ai_result_frame.pack(fill="x", padx=24, pady=(6, 0), before=self.btn_row)

    # ── URL 행 토글 ───────────────────────────────────
    def _toggle_link_row(self):
        if self.note_type.get() == "link":
            self.url_row.pack(fill="x", padx=24, pady=(0, 0),
                               before=self.right_parent.winfo_children()[2])
            self._on_url_change()
        else:
            self.url_row.pack_forget()
            self.url_var.set("")
            self.youtube_btn.pack_forget()

    # ── URL 요약 ──────────────────────────────────────
    def _fetch_summary(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("알림", "URL을 입력하세요."); return
        if not url.startswith("http"):
            url = "https://" + url
            self.url_var.set(url)
        self.fetch_btn.configure(text="가져오는 중...", state="disabled")
        self.status_label.configure(text="페이지 읽는 중...")
        # fetch_url_summary()는 네트워크 요청 — 반드시 백그라운드 스레드에서 실행
        def worker():
            result = fetch_url_summary(url)
            self.after(0, lambda: self._apply_summary(*result))
        threading.Thread(target=worker, daemon=True).start()

    def _apply_summary(self, title, body, err):
        self.fetch_btn.configure(text="요약 가져오기", state="normal")
        if err:
            self.status_label.configure(text=f"오류: {err}"); return
        if title: self.title_var.set(title)
        self.content_box.delete("1.0", "end")
        self.content_box.insert("1.0", body)
        self.status_label.configure(text="요약 완료 ✓")

    # ── AI 공통 ───────────────────────────────────────
    def _check_api(self):
        if not self.api_client:
            messagebox.showwarning("API 키 없음",
                "상단의 'API 키 설정' 버튼으로 키를 먼저 입력하세요.")
            return False
        return True

    def _ai_set_loading(self, btn, text):
        btn.configure(text="분석 중...", state="disabled")
        self.status_label.configure(text="AI 분석 중...")

    def _ai_error(self, err):
        self.keywords_btn.configure(text="🔗 연결고리 찾기", state="normal")
        self.similar_btn.configure(text="🔍 비슷한 노트 찾기", state="normal")
        self.status_label.configure(text="API 연결 실패 - 키를 확인해주세요")
        self._show_ai_result("❌ 오류", f"API 연결 실패 - 키를 확인해주세요\n\n{err}")

    # ── 연결고리 찾기 ─────────────────────────────────
    def _find_keywords(self):
        if not self._check_api(): return
        title   = self.title_var.get().strip()
        content = self.content_box.get("1.0", "end").strip()
        if not title and not content:
            messagebox.showwarning("알림", "노트 내용을 먼저 입력하세요."); return
        self._ai_set_loading(self.keywords_btn, "분석 중...")

        def worker():
            try:
                import google.generativeai as genai
                model = genai.GenerativeModel(
                    GEMINI_MODEL,
                    system_instruction=(
                        "당신은 지식 관리 전문가입니다. "
                        "사용자의 노트를 분석하여 주제적으로 연결될 수 있는 개념과 이유를 찾아주세요. "
                        "반드시 한국어로 답변하세요."
                    )
                )
                note_text = f"제목: {title}\n\n본문: {content[:1000]}"
                response = model.generate_content(
                    f"다음 노트와 주제적으로 연결될 수 있는 키워드 5개와 "
                    f"각각의 연결 이유를 한국어로 알려줘:\n\n{note_text}"
                )
                self.after(0, lambda: self._done_keywords(response.text))
            except Exception as e:
                logging.error(e, exc_info=True)
                self.after(0, lambda: self._ai_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _done_keywords(self, text):
        self.keywords_btn.configure(text="🔗 연결고리 찾기", state="normal")
        self.status_label.configure(text="분석 완료 ✓")
        self._show_ai_result("🔗 연결고리 분석", text)

    # ── 비슷한 노트 찾기 ──────────────────────────────
    def _find_similar(self):
        if not self._check_api(): return
        if len(self.data["notes"]) < 2:
            messagebox.showinfo("알림", "비교할 노트가 2개 이상 필요합니다."); return
        title   = self.title_var.get().strip()
        content = self.content_box.get("1.0", "end").strip()
        if not title and not content:
            messagebox.showwarning("알림", "노트 내용을 먼저 입력하세요."); return
        self._ai_set_loading(self.similar_btn, "분석 중...")
        current_id = self.selected_id

        def worker():
            try:
                other_notes = [n for n in self.data["notes"] if n["id"] != current_id]
                notes_block = "\n\n".join(
                    f"[ID:{n['id'][:8]}] {n['title']}\n"
                    f"태그: {', '.join(n['tags'])}\n"
                    f"내용: {n['content'][:200]}"
                    for n in other_notes[:30]
                )
                current_note = f"제목: {title}\n내용: {content[:500]}"
                import google.generativeai as genai
                model = genai.GenerativeModel(
                    GEMINI_MODEL,
                    system_instruction=(
                        "당신은 지식 관리 전문가입니다. "
                        "노트들의 주제적 연관성을 분석합니다. "
                        "반드시 한국어로 답변하세요."
                    )
                )
                response = model.generate_content(f"""현재 노트:
{current_note}

---
아래 목록에서 현재 노트와 가장 유사한 노트 3개를 골라 이유와 함께 알려주세요.
반드시 아래 형식을 정확히 지켜주세요:

[ID:xxxxxxxx] 노트 제목
이유: (유사한 이유 1-2문장)

[ID:xxxxxxxx] 노트 제목
이유: (유사한 이유 1-2문장)

[ID:xxxxxxxx] 노트 제목
이유: (유사한 이유 1-2문장)

---
노트 목록:
{notes_block}""")
                result_text = response.text
                short_ids = re.findall(r'\[ID:([a-f0-9]{8})\]', result_text)
                full_ids = []
                for sid in short_ids:
                    for n in other_notes:
                        if n["id"].startswith(sid) and n["id"] not in full_ids:
                            full_ids.append(n["id"]); break
                self.after(0, lambda: self._done_similar(result_text, full_ids))
            except Exception as e:
                logging.error(e, exc_info=True)
                self.after(0, lambda: self._ai_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _done_similar(self, text, note_ids):
        self.similar_btn.configure(text="🔍 비슷한 노트 찾기", state="normal")
        self.status_label.configure(text="분석 완료 ✓")
        hint = "\n\n💡 파란색 [ID:...] 부분을 클릭하면 해당 노트로 이동합니다." if note_ids else ""
        self.ai_result_title.configure(text="🔍 비슷한 노트")
        self.ai_result_box.configure(state="normal")
        self.ai_result_box.delete("1.0", "end")
        self.ai_result_box.insert("1.0", text + hint)
        for i, note_id in enumerate(note_ids):
            tag = f"link_{i}"
            short_id = note_id[:8]
            pattern = f"[ID:{short_id}]"
            start = "1.0"
            while True:
                pos = self.ai_result_box.search(pattern, start, stopindex="end")
                if not pos: break
                end_pos = f"{pos}+{len(pattern)}c"
                self.ai_result_box.tag_add(tag, pos, end_pos)
                self.ai_result_box.tag_configure(tag, foreground=ACCENT, underline=True)
                nid = note_id
                self.ai_result_box.tag_bind(tag, "<Button-1>",
                    lambda e, nid=nid: self.select_note(nid))
                self.ai_result_box.tag_bind(tag, "<Enter>",
                    lambda e: self.ai_result_box.configure(cursor="hand2"))
                self.ai_result_box.tag_bind(tag, "<Leave>",
                    lambda e: self.ai_result_box.configure(cursor="arrow"))
                start = end_pos
        self.ai_result_box.configure(state="disabled")
        self.ai_result_frame.pack(fill="x", padx=24, pady=(6, 0), before=self.btn_row)

    # ── 백업 ─────────────────────────────────────────
    def _backup(self):
        if not os.path.exists(DATA_FILE):
            messagebox.showinfo("알림", "백업할 데이터가 없습니다."); return
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(os.path.dirname(DATA_FILE), f"brain_backup_{date_str}.json")
        shutil.copy2(DATA_FILE, backup_path)
        messagebox.showinfo("백업 완료", f"저장됨:\n{backup_path}")

    # ── 통계 & 태그 클라우드 ──────────────────────────
    def _update_stats(self):
        total = len(self.data["notes"])
        links = sum(1 for n in self.data["notes"] if n.get("type") == "link")
        due   = sum(1 for n in self.data["notes"] if self._days_since_review(n) >= 7)
        review_text = f"  🔁 복습 {due}개" if due else ""
        self.stats_label.configure(
            text=f"📝 노트 {total - links}개  🔗 링크 {links}개{review_text}")

    def _refresh_tag_cloud(self):
        for w in self.tag_cloud_inner.winfo_children():
            w.destroy()
        all_tags = [t for n in self.data["notes"] for t in n["tags"]]
        if not all_tags:
            tk.Label(self.tag_cloud_inner, text="태그 없음", bg=BG2, fg=TEXT_DIM,
                     font=("Segoe UI", 8)).pack(anchor="w")
            return
        counts = Counter(all_tags)
        min_c, max_c = min(counts.values()), max(counts.values())
        row = tk.Frame(self.tag_cloud_inner, bg=BG2)
        row.pack(fill="x")
        for tag, count in sorted(counts.items(), key=lambda x: -x[1])[:20]:
            ratio = (count - min_c) / (max_c - min_c) if max_c > min_c else 0.5
            size = int(8 + ratio * 7)
            lbl = tk.Label(row, text=f"#{tag}", bg=BG2, fg=ACCENT,
                           font=("Segoe UI", size), cursor="hand2")
            lbl.pack(side="left", padx=(0, 4), pady=1)
            lbl.bind("<Button-1>", lambda e, t=tag: self._filter_by_tag(t))
            lbl.bind("<Enter>", lambda e, l=lbl: l.configure(fg="#81d4fa"))
            lbl.bind("<Leave>", lambda e, l=lbl: l.configure(fg=ACCENT))

    def _filter_by_tag(self, tag):
        self.search_var.set(tag)

    # ── 노트 목록 ─────────────────────────────────────
    def refresh_list(self):
        for w in self.scroll_inner.winfo_children():
            w.destroy()
        keyword = self.search_var.get().strip().lower()
        notes = self.data["notes"]
        if keyword:
            notes = [n for n in notes if
                     keyword in n["title"].lower() or
                     keyword in n["content"].lower() or
                     any(keyword in t.lower() for t in n["tags"])]
        notes = sorted(notes, key=lambda n: n["updated_at"], reverse=True)
        for note in notes:
            self._note_card(note)
        self._update_stats()
        self._refresh_tag_cloud()

    def _note_card(self, note):
        is_sel = note["id"] == self.selected_id
        bg = SEL if is_sel else BG2
        hover_bg = "#1a3a5c" if not is_sel else SEL

        card = tk.Frame(self.scroll_inner, bg=bg, cursor="hand2")
        card.pack(fill="x")
        tk.Frame(card, bg=BORDER, height=1).pack(fill="x")
        inner = tk.Frame(card, bg=bg, padx=14, pady=10)
        inner.pack(fill="x")

        days = self._days_since_review(note)
        review_icon = "🔁 " if days >= 7 else ""
        type_icon = "🔗 " if note.get("type") == "link" else "📝 "
        title_text = review_icon + type_icon + (note["title"] if note["title"] else "(제목 없음)")
        tk.Label(inner, text=title_text, bg=bg, fg=TEXT,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x")
        if note["tags"]:
            tk.Label(inner, text="  ".join(f"#{t}" for t in note["tags"]),
                     bg=bg, fg=ACCENT, font=("Segoe UI", 8), anchor="w").pack(
                fill="x", pady=(2, 0))
        tk.Label(inner, text=note["updated_at"][:10], bg=bg, fg=TEXT_DIM,
                 font=("Segoe UI", 8), anchor="w").pack(fill="x", pady=(2, 0))

        def on_enter(e, c=card, i=inner):
            if note["id"] != self.selected_id:
                c.configure(bg=hover_bg); i.configure(bg=hover_bg)
                for ch in i.winfo_children(): ch.configure(bg=hover_bg)

        def on_leave(e, c=card, i=inner):
            if note["id"] != self.selected_id:
                c.configure(bg=BG2); i.configure(bg=BG2)
                for ch in i.winfo_children(): ch.configure(bg=BG2)

        for w in [card, inner] + inner.winfo_children():
            w.bind("<Button-1>", lambda e, nid=note["id"]: self.select_note(nid))
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)

    # ── 노트 조작 ─────────────────────────────────────
    def new_note(self):
        self.selected_id = None
        self.note_type.set("note")
        self._toggle_link_row()
        self.url_var.set("")
        self.title_var.set("")
        self.tags_var.set("")
        self.content_box.delete("1.0", "end")
        self._hide_ai_result()
        self.review_bar.pack_forget()
        self.status_label.configure(text="새 노트")

    def select_note(self, note_id):
        self.selected_id = note_id
        note = next(n for n in self.data["notes"] if n["id"] == note_id)
        self.note_type.set(note.get("type", "note"))
        self._toggle_link_row()
        self.url_var.set(note.get("url", ""))
        self.title_var.set(note["title"])
        self.tags_var.set(", ".join(note["tags"]))
        self.content_box.delete("1.0", "end")
        self.content_box.insert("1.0", note["content"])
        self._hide_ai_result()

        days = self._days_since_review(note)
        if days >= 7:
            suffix = "  — 오래된 노트예요!" if days >= 90 else ""
            self.review_bar_label.configure(
                text=f"🔁 마지막으로 본 지 {days}일 됐어요{suffix}")
            self.review_bar.pack(fill="x", padx=24, pady=(6, 0),
                                  before=self.content_label)
        else:
            self.review_bar.pack_forget()

        self.status_label.configure(text=f"수정됨: {note['updated_at'][:16]}")
        self.refresh_list()

    def save_note(self):
        title   = self.title_var.get().strip()
        content = self.content_box.get("1.0", "end").strip()
        tags    = [t.strip() for t in self.tags_var.get().split(",") if t.strip()]
        ntype   = self.note_type.get()
        url     = self.url_var.get().strip() if ntype == "link" else ""
        now     = datetime.now().isoformat(timespec="seconds")

        if not title:
            messagebox.showwarning("알림", "제목을 입력하세요."); return

        if self.selected_id:
            for note in self.data["notes"]:
                if note["id"] == self.selected_id:
                    note.update(title=title, content=content, tags=tags,
                                type=ntype, url=url, updated_at=now)
                    break
        else:
            new = {"id": str(uuid.uuid4()), "title": title, "content": content,
                   "tags": tags, "type": ntype, "url": url,
                   "created_at": now, "updated_at": now,
                   "reviewed_at": None, "review_count": 0}
            self.data["notes"].append(new)
            self.selected_id = new["id"]

        save_data(self.data)
        self.status_label.configure(text=f"저장됨: {now[:16]}")
        self.refresh_list()

    def delete_note(self):
        if not self.selected_id:
            messagebox.showinfo("알림", "삭제할 노트를 선택하세요."); return
        if not messagebox.askyesno("삭제 확인", "이 노트를 삭제할까요?"): return
        self.data["notes"] = [n for n in self.data["notes"] if n["id"] != self.selected_id]
        save_data(self.data)
        self.new_note()
        self.refresh_list()


if __name__ == "__main__":
    app = BrainApp()
    app.mainloop()

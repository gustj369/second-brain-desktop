import tkinter as tk
from tkinter import ttk, messagebox
import json, uuid, os, threading, re, shutil, random
from datetime import datetime, date
from collections import Counter

DATA_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain.json")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

BG       = "#1e1e1e"
BG2      = "#252526"
BG3      = "#2d2d2d"
ACCENT   = "#4fc3f7"
TEXT     = "#d4d4d4"
TEXT_DIM = "#858585"
BORDER   = "#3c3c3c"
SEL      = "#094771"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"notes": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def fetch_url_summary(url):
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
                "gemini-2.5-flash",
                system_instruction="당신은 지적 성장을 돕는 코치입니다. 반드시 한국어로 답변하세요."
            )
            notes_text = "\n\n".join(
                f"[노트 {i+1}] 제목: {n['title']}\n내용: {n['content'][:300]}"
                for i, n in enumerate(notes)
            )
            response = model.generate_content(
                f"다음 노트 {len(notes)}개를 읽고, 각각에 대해 오늘 다시 생각해볼 질문 1개씩을 한국어로 만들어줘.\n\n"
                f"형식을 정확히 지켜줘:\n[노트 1] 제목\n질문: (질문 내용)\n\n[노트 2] ...\n\n"
                f"노트 목록:\n{notes_text}"
            )
            result = response.text
        except Exception as e:
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
                "gemini-2.5-flash",
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

# ── 앱 ───────────────────────────────────────────────
class BrainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("세컨 브레인")
        self.geometry("1200x800")
        self.minsize(1200, 800)
        self.configure(bg=BG)

        self.data = load_data()
        self.selected_id = None
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_list())
        self.note_type = tk.StringVar(value="note")
        self.api_client = None

        self._build_ui()
        self._init_api()
        self.refresh_list()
        self.after(600, self._run_briefing)

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
            f"- [{n['title']}]: {n['content'][:200]}"
            for n in notes_to_send
        )
        q = question

        def worker():
            try:
                import google.generativeai as genai
                model = genai.GenerativeModel(
                    "gemini-2.5-flash",
                    system_instruction=(
                        "당신은 아래 노트들을 작성한 사람입니다. "
                        "이 사람의 사고방식과 관심사를 바탕으로 질문에 답해주세요. "
                        "없는 내용은 지어내지 말고 '관련 노트가 없습니다'라고 답하세요. "
                        "답변 마지막에 근거로 사용한 노트 제목을 '📎 참고 노트:' 항목으로 나열해주세요. "
                        "반드시 한국어로 답변하세요."
                    )
                )
                prompt = f"[노트 목록]\n{notes_context}\n\n[질문]\n{q}"
                response = model.generate_content(prompt)
                result = notice + response.text
                self.after(0, lambda: self._done_ask(result))
            except Exception as e:
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

    # ── 망각 방지 복습 ────────────────────────────────
    def _days_since_review(self, note):
        ref = note.get("reviewed_at") or note.get("created_at", "")
        if not ref:
            return 0
        try:
            return (date.today() - datetime.fromisoformat(ref).date()).days
        except:
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

        tk.Button(header, text="API 키 설정", bg=BG3, fg=TEXT_DIM,
                  font=("Segoe UI", 8), relief="flat",
                  command=self._reset_api_key).pack(side="right", padx=(8, 16), pady=13, ipadx=8, ipady=2)
        tk.Button(header, text="💾 백업", bg=BG3, fg=TEXT_DIM,
                  font=("Segoe UI", 8), relief="flat",
                  command=self._backup).pack(side="right", pady=13, ipadx=8, ipady=2)
        tk.Button(header, text="💥 아이디어 충돌", bg="#2a1b2a", fg="#ce93d8",
                  font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                  command=self._idea_collider).pack(side="right", padx=(0, 8), pady=13, ipadx=10, ipady=2)

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
        tk.Label(search_frame, text="전체 검색  (제목 · 본문 · 태그)", bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w")
        tk.Entry(search_frame, textvariable=self.search_var,
                 bg=BG3, fg=TEXT, insertbackground=TEXT,
                 relief="flat", font=("Segoe UI", 10), bd=6
                 ).pack(fill="x", ipady=4)

        tk.Button(parent, text="＋  새 노트", bg=ACCENT, fg="#000000",
                  font=("Segoe UI", 10, "bold"), relief="flat",
                  activebackground="#81d4fa", cursor="hand2",
                  command=self.new_note).pack(fill="x", padx=12, pady=(0, 10), ipady=6)

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x")

        # 태그 클라우드 (하단 고정)
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
        self.similar_btn.pack(side="left", ipadx=10, ipady=5)

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

        # 저장/삭제 버튼
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
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=0)
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
                                   font=("Segoe UI", 10), relief="flat", bd=8,
                                   width=40)
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
        else:
            self.url_row.pack_forget()
            self.url_var.set("")

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
        threading.Thread(target=lambda: self.after(0,
            lambda: self._apply_summary(*fetch_url_summary(url))), daemon=True).start()

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
                    "gemini-2.5-flash",
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
                    "gemini-2.5-flash",
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
                self.after(0, lambda: self._ai_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _done_similar(self, text, note_ids):
        self.similar_btn.configure(text="🔍 비슷한 노트 찾기", state="normal")
        self.status_label.configure(text="분석 완료 ✓")
        hint = "\n\n💡 파란색으로 표시된 [ID:...] 부분을 클릭하면 해당 노트로 이동합니다." if note_ids else ""
        display = text + hint
        self.ai_result_title.configure(text="🔍 비슷한 노트")
        self.ai_result_box.configure(state="normal")
        self.ai_result_box.delete("1.0", "end")
        self.ai_result_box.insert("1.0", display)
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
        review_due = sum(1 for n in self.data["notes"] if self._days_since_review(n) >= 7)
        review_text = f"  🔁 복습 {review_due}개" if review_due else ""
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
                     bg=bg, fg=ACCENT, font=("Segoe UI", 8), anchor="w").pack(fill="x", pady=(2, 0))
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
            msg = f"🔁 마지막으로 본 지 {days}일 됐어요{'  — 오래된 노트예요!' if days >= 90 else ''}"
            self.review_bar_label.configure(text=msg)
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

        if not title and not content:
            messagebox.showwarning("알림", "제목 또는 본문을 입력하세요."); return

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

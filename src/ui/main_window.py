import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import os
import threading
import queue
import webbrowser
from utils.logger import logger
from core.engine import CrawlerEngine
from ui.settings_dialog import SettingsDialog
from db_viewer.db_viewer import DBViewer
from data.db_repository import db

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Manatoki Crawler (Reborn)")
        self.geometry("850x650") # Slightly wider for sidebar
        
        self.msg_queue = queue.Queue()
        self.engine = None
        self.engine_thread = None
        self.current_view = None
        
        # PERSISTENT VARIABLES (Shared across views)
        self.url_var = tk.StringVar()
        self.path_var = tk.StringVar(value="downloaded_files")
        self.threads_var = tk.StringVar(value="2")
        self.captcha_auto_var = tk.BooleanVar(value=db.get_config("CAPTCHA_AUTO_SOLVE") != "false")
        self.headless_var = tk.BooleanVar(value=db.get_config("HEADLESS_MODE") == "true")
        self._status_counter = 0  # For throttling status refresh
        
        # Persistent log area to keep logs when switching views
        self.log_area_persistent = scrolledtext.ScrolledText(None, state='disabled')
        
        self._create_widgets()
        self._setup_logger()
        
        self.after(100, self._process_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_widgets(self):
        # 1. Main Layout Containers
        self.sidebar = ttk.Frame(self, width=170, padding=10)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)

        self.content_container = ttk.Frame(self, padding=10)
        self.content_container.pack(side='right', fill='both', expand=True)

        # 2. Sidebar Menu
        ttk.Label(self.sidebar, text="MANATOKI\nCRAWLER", font=('Helvetica', 14, 'bold'), justify='center').pack(pady=(10, 30))
        
        menu_items = [
            ("🏠 수집 메인", self._show_dashboard),
            ("🆕 선택 크롤링", self._show_latest_updates),
            ("📁 DB 확인", self._show_db_viewer),
            ("⚙️ 기본 설정", self._show_settings),
        ]
        
        self.menu_buttons = {}
        for text, command in menu_items:
            btn = ttk.Button(self.sidebar, text=text, command=command)
            btn.pack(fill='x', pady=4)
            self.menu_buttons[text] = btn

        ttk.Separator(self.sidebar, orient='horizontal').pack(fill='x', pady=20)
        
        # Shortcut button
        ttk.Button(self.sidebar, text="🌐 마나토끼 바로가기", command=self._open_manatoki).pack(fill='x', pady=4)
        
        ttk.Button(self.sidebar, text="About", command=self._show_about).pack(fill='x')
        ttk.Button(self.sidebar, text="종료", command=self._on_close).pack(fill='x', pady=4)

        # 3. Status Area (bottom of sidebar)
        status_frame = ttk.LabelFrame(self.sidebar, text="상태", padding=5)
        status_frame.pack(side='bottom', fill='x', pady=(10, 0))

        self.status_captcha_label = ttk.Label(status_frame, text="", font=('Helvetica', 9))
        self.status_captcha_label.pack(anchor='w')
        self.status_apikey_label = ttk.Label(status_frame, text="", font=('Helvetica', 9))
        self.status_apikey_label.pack(anchor='w')
        self.status_engine_label = ttk.Label(status_frame, text="", font=('Helvetica', 9))
        self.status_engine_label.pack(anchor='w')

        self._refresh_status()

        # 4. Initial View
        self._show_dashboard()

    def _open_manatoki(self):
        url = db.get_config("MANATOKI_URL")
        if url:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            webbrowser.open(url)
        else:
            messagebox.showinfo("알림", "기본 설정에서 마나토끼 주소를 먼저 설정해주세요.")

    def _refresh_status(self):
        """사이드바 상태 영역 갱신"""
        # Captcha auto-solve
        captcha_auto = db.get_config("CAPTCHA_AUTO_SOLVE") != "false"
        self.status_captcha_label.config(
            text=f"🤖 캡챠: {'자동' if captcha_auto else '수동'}",
            foreground='green' if captcha_auto else 'orange'
        )
        # API Key
        api_key = db.get_config("GEMINI_API_KEY")
        has_key = bool(api_key and api_key != "YOUR_API_KEY")
        self.status_apikey_label.config(
            text=f"🔑 API 키: {'설정됨' if has_key else '미설정'}",
            foreground='green' if has_key else 'red'
        )
        # Engine
        running = self.engine and self.engine.is_running
        self.status_engine_label.config(
            text=f"⚙️ 엔진: {'실행중' if running else '대기'}",
            foreground='blue' if running else 'gray'
        )

    def _show_view(self, view_frame):
        if self.current_view:
            self.current_view.destroy()
        self.current_view = view_frame
        self.current_view.pack(fill='both', expand=True)
        self._refresh_status()

    def _show_dashboard(self):
        frame = ttk.Frame(self.content_container)
        
        # 1. URL Input
        url_frame = ttk.LabelFrame(frame, text="수집 대상", padding=10)
        url_frame.pack(fill='x', pady=5)
        
        ttk.Label(url_frame, text="URL:").pack(side='left')
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url_var)
        self.url_entry.pack(side='left', fill='x', expand=True, padx=5)

        # 2. Options
        opt_frame = ttk.LabelFrame(frame, text="옵션", padding=10)
        opt_frame.pack(fill='x', pady=5)

        # Row 1: 다운로드 경로 + 스레드
        row1 = ttk.Frame(opt_frame)
        row1.pack(fill='x')
        ttk.Label(row1, text="다운로드 경로:").pack(side='left')
        ttk.Entry(row1, textvariable=self.path_var).pack(side='left', fill='x', expand=True, padx=5)
        ttk.Button(row1, text="선택", command=self._browse_path).pack(side='left')
        ttk.Separator(row1, orient='vertical').pack(side='left', fill='y', padx=10)
        ttk.Label(row1, text="스레드:").pack(side='left')
        ttk.Spinbox(row1, from_=1, to=8, textvariable=self.threads_var, width=5).pack(side='left', padx=5)

        # Row 2: 체크박스 옵션
        row2 = ttk.Frame(opt_frame)
        row2.pack(fill='x', pady=(5, 0))
        ttk.Checkbutton(row2, text="캡챠 자동 해결", variable=self.captcha_auto_var, command=self._on_option_toggle).pack(side='left', padx=(0, 15))
        ttk.Checkbutton(row2, text="백그라운드 실행 (Headless)", variable=self.headless_var, command=self._on_option_toggle).pack(side='left')

        # 3. Controls
        btn_frame = ttk.Frame(frame, padding=5)
        btn_frame.pack(fill='x', pady=5)
        
        self.btn_start = ttk.Button(btn_frame, text="수집 시작", command=self._start_crawling)
        self.btn_start.pack(side='left', fill='x', expand=True, padx=5)
        
        self.btn_stop = ttk.Button(btn_frame, text="중지", command=self._stop_crawling, state='disabled')
        if self.engine and self.engine.is_running:
            self.btn_stop.config(state='normal')
            self.btn_start.config(state='disabled')
        self.btn_stop.pack(side='left', fill='x', expand=True, padx=5)

        # 4. Logs
        log_frame = ttk.LabelFrame(frame, text="로그", padding=5)
        log_frame.pack(fill='both', expand=True, pady=5)
        
        # Shared Log Area
        self.log_area = scrolledtext.ScrolledText(log_frame, state='normal')
        self.log_area.insert(tk.END, self.log_area_persistent.get('1.0', tk.END))
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')
        self.log_area.pack(fill='both', expand=True)

        self._show_view(frame)

    def _show_db_viewer(self):
        self._show_view(DBViewer(self.content_container))

    def _show_settings(self):
        self._show_view(SettingsDialog(self.content_container))

    def _show_latest_updates(self):
        frame = ttk.Frame(self.content_container, padding=10)
        
        action_frame = ttk.Frame(frame)
        action_frame.pack(fill='x', pady=(0, 8))

        ttk.Button(action_frame, text="새로고침", command=lambda: self._load_latest_updates(tree)).pack(side='left')
        ttk.Button(action_frame, text="선택 크롤링", command=lambda: self._crawl_selected_latest(tree)).pack(side='left', padx=6)

        tree = ttk.Treeview(frame, columns=("Select", "List URL", "Title", "Last Crawled"), show='headings')
        tree.heading("Select", text="선택")
        tree.heading("List URL", text="List URL")
        tree.heading("Title", text="제목")
        tree.heading("Last Crawled", text="최근 수집")
        
        tree.column("Select", width=50, anchor='center')
        tree.column("List URL", width=250)
        tree.column("Title", width=200)
        tree.column("Last Crawled", width=120, anchor='center')

        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        tree.pack(side='left', fill='both', expand=True)

        tree.latest_check_vars = {}
        tree.bind("<Button-1>", lambda event: self._on_latest_tree_click(tree, event))

        self._load_latest_updates(tree)
        self._show_view(frame)

    def _setup_logger(self):
        def on_log(level, msg):
            self.msg_queue.put(msg)
        logger.add_listener(on_log)

    def _process_queue(self):
        try:
            while not self.msg_queue.empty():
                msg = self.msg_queue.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        
        if self.engine and not self.engine.is_running:
            if hasattr(self, 'btn_start') and str(self.btn_start['state']) == 'disabled':
                self._toggle_ui(running=False)

        self.after(100, self._process_queue)
        self._status_counter += 1
        if self._status_counter % 20 == 0:  # ~2초마다 갱신
            self._refresh_status()

    def _append_log(self, text):
        # Update persistent store
        self.log_area_persistent.config(state='normal')
        self.log_area_persistent.insert(tk.END, text + "\n")
        self.log_area_persistent.see(tk.END)
        self.log_area_persistent.config(state='disabled')
        
        # Update UI if dashboard is active
        if hasattr(self, 'log_area') and self.log_area.winfo_exists():
            self.log_area.config(state='normal')
            self.log_area.insert(tk.END, text + "\n")
            self.log_area.see(tk.END)
            self.log_area.config(state='disabled')

    def _on_option_toggle(self):
        """체크박스 변경 시 즉시 DB에 저장"""
        db.set_config("CAPTCHA_AUTO_SOLVE", "true" if self.captcha_auto_var.get() else "false")
        db.set_config("HEADLESS_MODE", "true" if self.headless_var.get() else "false")
        self._refresh_status()

    def _browse_path(self):
        path = filedialog.askdirectory()
        if path:
            self.path_var.set(path)
            list_url_path = os.path.join(path, "list_url.txt")
            if os.path.exists(list_url_path):
                try:
                    with open(list_url_path, 'r', encoding='utf-8') as f:
                        saved_url = f.read().strip()
                        if saved_url:
                            self.url_var.set(saved_url)
                            self._append_log(f"URL loaded from file: {saved_url}")
                except Exception as e:
                    logger.warning(f"Failed to load list_url.txt: {e}")

    def _load_latest_updates(self, tree):
        for item in tree.get_children():
            tree.delete(item)
        tree.latest_check_vars.clear()
        try:
            rows = db.get_latest_mana_lists()
            for list_url, list_title, last_crawled in rows:
                item_id = f"ml_{len(tree.latest_check_vars) + 1}"
                tree.latest_check_vars[item_id] = tk.BooleanVar(value=False)
                tree.insert("", "end", iid=item_id, values=("☐", list_url, list_title, last_crawled))
        except Exception as e:
            messagebox.showerror("Error", f"Could not load latest updates: {e}")

    def _on_latest_tree_click(self, tree, event):
        region = tree.identify_region(event.x, event.y)
        if region == "heading" and tree.identify_column(event.x) == "#1":
            self._toggle_all_latest(tree)
            return
        if region == "cell" and tree.identify_column(event.x) == "#1":
            item_iid = tree.identify_row(event.y)
            if item_iid:
                var = tree.latest_check_vars.get(item_iid)
                if var:
                    var.set(not var.get())
                    self._update_latest_checkbox(tree, item_iid, var.get())

    def _update_latest_checkbox(self, tree, item_iid, is_checked):
        current_values = tree.item(item_iid, 'values')
        new_values = list(current_values)
        new_values[0] = "☑" if is_checked else "☐"
        tree.item(item_iid, values=tuple(new_values))

    def _toggle_all_latest(self, tree):
        any_unchecked = any(not var.get() for var in tree.latest_check_vars.values())
        new_state = any_unchecked
        for item_id, var in tree.latest_check_vars.items():
            var.set(new_state)
            self._update_latest_checkbox(tree, item_id, new_state)

    def _crawl_selected_latest(self, tree):
        if self.engine and self.engine.is_running:
            messagebox.showinfo("알림", "크롤링이 이미 진행 중입니다.")
            return
        selected_urls = [tree.item(iid, "values")[1] for iid, var in tree.latest_check_vars.items() if var.get()]
        if not selected_urls:
            messagebox.showinfo("알림", "크롤링할 항목을 선택해주세요.")
            return
        
        path = self.path_var.get()
        try: threads = int(self.threads_var.get())
        except: threads = 2
        base_folder = db.get_config("LOCAL_BASE_STORE_FOLDER") or ""
        self.engine = CrawlerEngine(download_path=path, num_download_threads=threads, captcha_auto_solve=self.captcha_auto_var.get(), base_store_folder=base_folder, headless=self.headless_var.get())
        self._toggle_ui(running=True)

        def run_batch():
            self.engine.start_batch(selected_urls)
            self._toggle_ui(running=False)
        threading.Thread(target=run_batch, daemon=True).start()

    def _start_crawling(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Warning", "URL을 입력해주세요.")
            return
        path = self.path_var.get()
        try: threads = int(self.threads_var.get())
        except: threads = 2
        
        # Auto-save and .bat creation logic (simplified)
        if path and os.path.isdir(path):
            try:
                with open(os.path.join(path, "list_url.txt"), 'w', encoding='utf-8') as f: f.write(url)
            except: pass

        base_folder = db.get_config("LOCAL_BASE_STORE_FOLDER") or ""
        self.engine = CrawlerEngine(download_path=path, num_download_threads=threads, captcha_auto_solve=self.captcha_auto_var.get(), base_store_folder=base_folder, headless=self.headless_var.get())
        self._toggle_ui(running=True)
        self.engine_thread = threading.Thread(target=self.engine.start, args=(url,), daemon=True)
        self.engine_thread.start()

    def _stop_crawling(self):
        if self.engine: self.engine.stop()
        if hasattr(self, 'btn_stop'): self.btn_stop.config(state='disabled')

    def _toggle_ui(self, running):
        if hasattr(self, 'btn_start') and self.btn_start.winfo_exists():
            self.btn_start.config(state='disabled' if running else 'normal')
        if hasattr(self, 'btn_stop') and self.btn_stop.winfo_exists():
            self.btn_stop.config(state='normal' if running else 'disabled')
        if hasattr(self, 'url_entry') and self.url_entry.winfo_exists():
            self.url_entry.config(state='disabled' if running else 'normal')

    def _show_about(self):
        messagebox.showinfo("About", "Manatoki Crawler\nVersion 3.0.1 (Sidebar Integrated)\n\nCreated by ChoChoCho with Gemini 3")

    def _on_close(self):
        if self.engine and self.engine.is_running:
            if messagebox.askokcancel("종료", "크롤링이 진행 중입니다. 정말 종료하시겠습니까?"):
                self.engine.stop()
                self.destroy()
        else:
            self.destroy()

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import os
import threading
import queue
from utils.logger import logger
from core.engine import CrawlerEngine
from ui.settings_dialog import SettingsDialog
from db_viewer.db_viewer import DBViewer # Keeping legacy DBViewer for now

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Manatoki Crawler (Reborn)")
        self.geometry("700x600")
        
        # Queue for thread-safe UI updates
        self.msg_queue = queue.Queue()
        
        # Engine
        self.engine = None
        self.engine_thread = None
        
        self._create_widgets()
        self._setup_logger()
        
        # periodic check for queue
        self.after(100, self._process_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_widgets(self):
        # Menu
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="종료", command=self._on_close)
        menubar.add_cascade(label="파일", menu=file_menu)
        
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="기본 설정", command=self._open_settings)
        menubar.add_cascade(label="설정", menu=settings_menu)
        
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="DB Viewer", command=self._open_db_viewer)
        menubar.add_cascade(label="도구", menu=tools_menu)

        # Main Layout
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill='both', expand=True)

        # 1. URL Input
        url_frame = ttk.LabelFrame(main_frame, text="수집 대상", padding=10)
        url_frame.pack(fill='x', pady=5)
        
        ttk.Label(url_frame, text="URL:").pack(side='left')
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url_var)
        self.url_entry.pack(side='left', fill='x', expand=True, padx=5)

        # 2. Options
        opt_frame = ttk.LabelFrame(main_frame, text="옵션", padding=10)
        opt_frame.pack(fill='x', pady=5)
        
        ttk.Label(opt_frame, text="다운로드 경로:").pack(side='left')
        self.path_var = tk.StringVar(value="downloaded_files")
        ttk.Entry(opt_frame, textvariable=self.path_var).pack(side='left', fill='x', expand=True, padx=5)
        ttk.Button(opt_frame, text="선택", command=self._browse_path).pack(side='left')
        
        ttk.Separator(opt_frame, orient='vertical').pack(side='left', fill='y', padx=10)
        
        ttk.Label(opt_frame, text="다운로드 스레드:").pack(side='left')
        self.threads_var = tk.StringVar(value="4")
        ttk.Spinbox(opt_frame, from_=1, to=8, textvariable=self.threads_var, width=5).pack(side='left', padx=5)

        # 3. Controls
        btn_frame = ttk.Frame(main_frame, padding=5)
        btn_frame.pack(fill='x', pady=5)
        
        self.btn_start = ttk.Button(btn_frame, text="수집 시작", command=self._start_crawling)
        self.btn_start.pack(side='left', fill='x', expand=True, padx=5)
        
        self.btn_stop = ttk.Button(btn_frame, text="중지", command=self._stop_crawling, state='disabled')
        self.btn_stop.pack(side='left', fill='x', expand=True, padx=5)

        # 4. Logs
        log_frame = ttk.LabelFrame(main_frame, text="로그", padding=5)
        log_frame.pack(fill='both', expand=True, pady=5)
        
        self.log_area = scrolledtext.ScrolledText(log_frame, state='disabled')
        self.log_area.pack(fill='both', expand=True)

    def _setup_logger(self):
        # Add listener to global logger
        def on_log(level, msg):
            self.msg_queue.put(msg)
        
        logger.add_listener(on_log)

    def _process_queue(self):
        try:
            while not self.msg_queue.empty():
                msg = self.msg_queue.get_nowait()
                self._append_log(msg)
                
                # Check for specific messages to toggle UI state?
                # Better to use a separate check or callback from engine completion
                if "Crawling Finished." in msg or "Stopping crawler..." in msg:
                     # This is logically weak, but engine doesn't have events yet.
                     # We might want to pass a callback to engine or poll engine state.
                     pass 
        except queue.Empty:
            pass
        
        # Check engine state and update UI
        if self.engine:
            if not self.engine.is_running:
                # Engine stopped. If UI says running (Stop button enabled or Start disabled), reset it.
                # Assuming if Start is disabled, we are in running state.
                if str(self.btn_start['state']) == 'disabled':
                    self._toggle_ui(running=False)

        self.after(100, self._process_queue)

    def _append_log(self, text):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, text + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def _browse_path(self):
        path = filedialog.askdirectory()
        if path:
            self.path_var.set(path)
            # Auto-load URL if exists
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

    def _open_settings(self):
        SettingsDialog(self)

    def _open_db_viewer(self):
        # Lazy import or use existing class
        try:
            DBViewer(self)
        except Exception as e:
            messagebox.showerror("Error", f"Could not open DB Viewer: {e}")

    def _start_crawling(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Warning", "URL을 입력해주세요.")
            return

        path = self.path_var.get()
        
        # Auto-save URL
        if path and os.path.isdir(path):
            try:
                list_url_path = os.path.join(path, "list_url.txt")
                with open(list_url_path, 'w', encoding='utf-8') as f:
                    f.write(url)
            except Exception as e:
                logger.warning(f"Failed to save list_url.txt: {e}")

        try:
            threads = int(self.threads_var.get())
        except:
            threads = 4

        self.engine = CrawlerEngine(download_path=path, num_download_threads=threads)
        self._toggle_ui(running=True)
        
        self.engine_thread = threading.Thread(target=self.engine.start, args=(url,))
        self.engine_thread.daemon = True
        self.engine_thread.start()

    def _stop_crawling(self):
        if self.engine:
            self.engine.stop()
        self.btn_stop.config(state='disabled') # Indicate stopping logic started

    def _toggle_ui(self, running):
        if running:
            self.btn_start.config(state='disabled')
            self.btn_stop.config(state='normal')
            self.url_entry.config(state='disabled')
        else:
            self.btn_start.config(state='normal')
            self.btn_stop.config(state='disabled')
            self.url_entry.config(state='normal')

    def _on_close(self):
        if self.engine and self.engine.is_running:
            if messagebox.askokcancel("종료", "크롤링이 진행 중입니다. 정말 종료하시겠습니까?"):
                self.engine.stop()
                self.destroy()
        else:
            self.destroy()

import tkinter as tk
from tkinter import ttk, messagebox
from data.db_repository import db

class SettingsDialog(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._create_widgets()
        self._load_settings()

    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill='both', expand=True)

        # Gemini API Key
        ttk.Label(main_frame, text="Gemini API Key:").pack(anchor='w')
        self.api_key_var = tk.StringVar()
        entry_frame = ttk.Frame(main_frame)
        entry_frame.pack(fill='x', pady=5)
        
        self.api_key_entry = ttk.Entry(entry_frame, textvariable=self.api_key_var, show="*")
        self.api_key_entry.pack(side='left', fill='x', expand=True)
        
        # Toggle visibility
        self.show_key_var = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(entry_frame, text="보기", variable=self.show_key_var, command=self._toggle_visibility)
        cb.pack(side='right', padx=5)

        ttk.Label(main_frame, text="* 캡차 해결을 위해 필요합니다.").pack(anchor='w', pady=(0, 10))

        # Captcha Auto-Solve Toggle
        ttk.Separator(main_frame, orient='horizontal').pack(fill='x', pady=10)
        self.captcha_auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(main_frame, text="캡챠 자동 해결 (Gemini API 사용)", variable=self.captcha_auto_var).pack(anchor='w')
        ttk.Label(main_frame, text="* 꺼져 있으면 캡챠 등장 시 유저가 직접 입력할 때까지 대기합니다.", foreground='gray').pack(anchor='w', pady=(0, 10))

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=20)
        ttk.Button(btn_frame, text="저장", command=self._save).pack(side='right', padx=5)

    def _toggle_visibility(self):
        if self.show_key_var.get():
            self.api_key_entry.config(show="")
        else:
            self.api_key_entry.config(show="*")

    def _load_settings(self):
        # API Key
        key = db.get_config("GEMINI_API_KEY")
        if key:
            self.api_key_var.set(key)
        # Captcha Auto-Solve
        captcha_auto = db.get_config("CAPTCHA_AUTO_SOLVE")
        self.captcha_auto_var.set(captcha_auto != "false")

    def _save(self):
        # Save API Key
        key = self.api_key_var.get().strip()
        if key:
            db.set_config("GEMINI_API_KEY", key)
        # Save Captcha Auto-Solve
        db.set_config("CAPTCHA_AUTO_SOLVE", "true" if self.captcha_auto_var.get() else "false")
        messagebox.showinfo("설정", "저장되었습니다.")

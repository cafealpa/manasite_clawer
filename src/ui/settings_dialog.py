import tkinter as tk
from tkinter import ttk, messagebox
from data.db_repository import db

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("설정")
        self.geometry("400x200")
        self.resizable(False, False)
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

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=20)
        ttk.Button(btn_frame, text="저장", command=self._save).pack(side='right', padx=5)
        ttk.Button(btn_frame, text="취소", command=self.destroy).pack(side='right')

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

    def _save(self):
        # Save API Key
        key = self.api_key_var.get().strip()
        if key:
            db.set_config("GEMINI_API_KEY", key)
            
        messagebox.showinfo("설정", "저장되었습니다.")
        self.destroy()

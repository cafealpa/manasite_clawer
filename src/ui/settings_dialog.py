import tkinter as tk
from tkinter import ttk, messagebox, filedialog
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

        # Base Store Folder
        ttk.Separator(main_frame, orient='horizontal').pack(fill='x', pady=10)
        ttk.Label(main_frame, text="기본 저장 경로:").pack(anchor='w')
        base_frame = ttk.Frame(main_frame)
        base_frame.pack(fill='x', pady=5)
        self.base_folder_var = tk.StringVar()
        ttk.Entry(base_frame, textvariable=self.base_folder_var).pack(side='left', fill='x', expand=True)
        ttk.Button(base_frame, text="선택", command=self._browse_base_folder).pack(side='left', padx=5)
        ttk.Label(main_frame, text="* 다운로드 경로 미지정 시, 이 경로 아래에 제목별 폴더가 자동 생성됩니다.", foreground='gray').pack(anchor='w', pady=(0, 10))

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=20)
        ttk.Button(btn_frame, text="저장", command=self._save).pack(side='right', padx=5)

    def _toggle_visibility(self):
        if self.show_key_var.get():
            self.api_key_entry.config(show="")
        else:
            self.api_key_entry.config(show="*")

    def _browse_base_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.base_folder_var.set(folder)

    def _load_settings(self):
        # API Key
        key = db.get_config("GEMINI_API_KEY")
        if key:
            self.api_key_var.set(key)
        # Base Store Folder
        base_folder = db.get_config("LOCAL_BASE_STORE_FOLDER")
        if base_folder:
            self.base_folder_var.set(base_folder)

    def _save(self):
        # Save API Key
        key = self.api_key_var.get().strip()
        if key:
            db.set_config("GEMINI_API_KEY", key)
        # Save Base Store Folder
        base_folder = self.base_folder_var.get().strip()
        if base_folder:
            db.set_config("LOCAL_BASE_STORE_FOLDER", base_folder)
        messagebox.showinfo("설정", "저장되었습니다.")

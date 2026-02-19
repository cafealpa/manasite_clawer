import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
from data.db_repository import db

FONT_FAMILY = "Malgun Gothic"

class SettingsDialog(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._create_widgets()
        self._load_settings()

    def _create_widgets(self):
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)

        # Manatoki URL
        ctk.CTkLabel(main_frame, text="마나토끼 주소:", font=ctk.CTkFont(family=FONT_FAMILY, weight="bold")).pack(anchor='w', padx=20, pady=(20, 5))
        self.mana_url_var = tk.StringVar()
        mana_url_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        mana_url_frame.pack(fill='x', padx=20, pady=5)
        ctk.CTkEntry(mana_url_frame, textvariable=self.mana_url_var, font=ctk.CTkFont(family=FONT_FAMILY)).pack(side='left', fill='x', expand=True)
        ctk.CTkLabel(main_frame, text="* 사이드바 바로가기 버튼에 사용될 URL입니다.", text_color="gray", font=ctk.CTkFont(family=FONT_FAMILY)).pack(anchor='w', padx=20, pady=(0, 10))

        # Gemini API Key
        ctk.CTkFrame(main_frame, height=2, fg_color="gray50").pack(fill='x', padx=20, pady=10)
        ctk.CTkLabel(main_frame, text="Gemini API Key:", font=ctk.CTkFont(family=FONT_FAMILY, weight="bold")).pack(anchor='w', padx=20, pady=5)
        self.api_key_var = tk.StringVar()
        entry_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        entry_frame.pack(fill='x', padx=20, pady=5)
        
        self.api_key_entry = ctk.CTkEntry(entry_frame, textvariable=self.api_key_var, show="*", font=ctk.CTkFont(family=FONT_FAMILY))
        self.api_key_entry.pack(side='left', fill='x', expand=True)
        
        # Toggle visibility
        self.show_key_var = tk.BooleanVar(value=False)
        cb = ctk.CTkCheckBox(entry_frame, text="보기", variable=self.show_key_var, command=self._toggle_visibility, width=60, font=ctk.CTkFont(family=FONT_FAMILY))
        cb.pack(side='right', padx=10)

        ctk.CTkLabel(main_frame, text="* 캡차 해결을 위해 필요합니다.", text_color="gray", font=ctk.CTkFont(family=FONT_FAMILY)).pack(anchor='w', padx=20, pady=(0, 10))

        # Base Store Folder
        ctk.CTkFrame(main_frame, height=2, fg_color="gray50").pack(fill='x', padx=20, pady=10)
        ctk.CTkLabel(main_frame, text="기본 저장 경로:", font=ctk.CTkFont(family=FONT_FAMILY, weight="bold")).pack(anchor='w', padx=20, pady=5)
        base_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        base_frame.pack(fill='x', padx=20, pady=5)
        self.base_folder_var = tk.StringVar()
        ctk.CTkEntry(base_frame, textvariable=self.base_folder_var, font=ctk.CTkFont(family=FONT_FAMILY)).pack(side='left', fill='x', expand=True)
        ctk.CTkButton(base_frame, text="선택", command=self._browse_base_folder, width=60, font=ctk.CTkFont(family=FONT_FAMILY)).pack(side='left', padx=10)
        ctk.CTkLabel(main_frame, text="* 다운로드 경로 미지정 시, 이 경로 아래에 제목별 폴더가 자동 생성됩니다.", text_color="gray", font=ctk.CTkFont(family=FONT_FAMILY)).pack(anchor='w', padx=20, pady=(0, 10))

        # DB File
        ctk.CTkFrame(main_frame, height=2, fg_color="gray50").pack(fill='x', padx=20, pady=10)
        ctk.CTkLabel(main_frame, text="DB File:", font=ctk.CTkFont(family=FONT_FAMILY, weight="bold")).pack(anchor='w', padx=20, pady=5)
        db_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        db_frame.pack(fill='x', padx=20, pady=5)
        self.db_path_var = tk.StringVar()
        ctk.CTkEntry(db_frame, textvariable=self.db_path_var, font=ctk.CTkFont(family=FONT_FAMILY)).pack(side='left', fill='x', expand=True)
        ctk.CTkButton(db_frame, text="Select", command=self._browse_db_file, width=60, font=ctk.CTkFont(family=FONT_FAMILY)).pack(side='left', padx=10)
        ctk.CTkLabel(main_frame, text="* Changing DB file affects all history and settings stored in DB.", text_color="gray", font=ctk.CTkFont(family=FONT_FAMILY)).pack(anchor='w', padx=20, pady=(0, 10))

        # Buttons
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill='x', pady=20, padx=20)
        ctk.CTkButton(btn_frame, text="Save", command=self._save, width=100, font=ctk.CTkFont(family=FONT_FAMILY)).pack(side='right')

    def _toggle_visibility(self):
        if self.show_key_var.get():
            self.api_key_entry.configure(show="")
        else:
            self.api_key_entry.configure(show="*")

    def _browse_base_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.base_folder_var.set(folder)

    def _browse_db_file(self):
        db_path = filedialog.askopenfilename(
            filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")]
        )
        if db_path:
            self.db_path_var.set(db_path)

    def _load_settings(self):
        # Manatoki URL
        mana_url = db.get_config("MANATOKI_URL")
        if mana_url:
            self.mana_url_var.set(mana_url)
        # API Key
        key = db.get_config("GEMINI_API_KEY")
        if key:
            self.api_key_var.set(key)
        # Base Store Folder
        base_folder = db.get_config("LOCAL_BASE_STORE_FOLDER")
        if base_folder:
            self.base_folder_var.set(base_folder)
        # DB Path (global)
        db_path = db.get_global_config("DB_PATH") or db.db_path
        if db_path:
            self.db_path_var.set(db_path)

    def _save(self):
        # Save Manatoki URL
        mana_url = self.mana_url_var.get().strip()
        if mana_url:
            db.set_config("MANATOKI_URL", mana_url)
        # Save API Key
        key = self.api_key_var.get().strip()
        if key:
            db.set_config("GEMINI_API_KEY", key)
        # Save Base Store Folder
        base_folder = self.base_folder_var.get().strip()
        if base_folder:
            db.set_config("LOCAL_BASE_STORE_FOLDER", base_folder)
        # Save DB Path (global)
        db_path = self.db_path_var.get().strip()
        if db_path:
            db.set_db_path(db_path)
            db.set_global_config("DB_PATH", db_path)
        messagebox.showinfo("설정", "저장되었습니다.")

import tkinter as tk
from tkinter import ttk, messagebox
import os
import time
from PIL import Image, ImageTk
from data.db_repository import db
from core.engine import CrawlerEngine

class ImageViewer(tk.Toplevel):
    def __init__(self, parent, folder_path, title="Image Viewer", current_db_id=None):
        super().__init__(parent)
        self.title(f"Viewer - {title}")
        self.geometry("1000x800")
        
        self.folder_path = folder_path
        self.current_db_id = current_db_id
        self.image_files = self._get_image_files()
        self.current_index = 0
        
        self._navigating = False
        self._last_alert_time = 0
        self._updating_ui = False
        self.fit_mode = True  # Default to Fit to Window
        
        if not self.image_files:
            ttk.Label(self, text="이미지를 찾을 수 없습니다.", font=("Helvetica", 14)).pack(expand=True)
            return

        self._create_widgets()
        self._show_image(calculate_fit=True)

    def _get_image_files(self):
        if not os.path.exists(self.folder_path):
            return []
        
        valid_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
        files = [f for f in os.listdir(self.folder_path) if f.lower().endswith(valid_extensions)]
        files.sort(key=lambda x: self._natural_sort_key(x))
        return [os.path.join(self.folder_path, f) for f in files]

    def _natural_sort_key(self, s):
        import re
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

    def _create_widgets(self):
        # Main container
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill='both', expand=True)

        # Canvas for image with scrollbars
        self.canvas_frame = ttk.Frame(self.main_frame)
        self.canvas_frame.pack(side='top', fill='both', expand=True)

        self.canvas = tk.Canvas(self.canvas_frame, bg='black')
        self.v_scroll = ttk.Scrollbar(self.canvas_frame, orient='vertical', command=self.canvas.yview)
        self.h_scroll = ttk.Scrollbar(self.canvas_frame, orient='horizontal', command=self.canvas.xview)
        
        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        
        self.v_scroll.pack(side='right', fill='y')
        self.h_scroll.pack(side='bottom', fill='x')
        self.canvas.pack(side='left', fill='both', expand=True)

        # Bottom Control Container
        self.bottom_frame = ttk.Frame(self.main_frame, padding=5)
        self.bottom_frame.pack(side='bottom', fill='x')

        # Navigation Row
        self.nav_frame = ttk.Frame(self.bottom_frame)
        self.nav_frame.pack(side='top', fill='x')

        # 1. Left Buttons
        left_btn_frame = ttk.Frame(self.nav_frame)
        left_btn_frame.pack(side='left')
        
        ttk.Button(left_btn_frame, text="⏮ 이전 화", command=self._go_prev_episode).pack(side='left', padx=5)
        ttk.Button(left_btn_frame, text="◀ 이전", command=self._prev_image).pack(side='left', padx=5)

        # 2. Right Buttons (Pack first to stay on right)
        right_btn_frame = ttk.Frame(self.nav_frame)
        right_btn_frame.pack(side='right')
        
        ttk.Button(right_btn_frame, text="다음 ▶", command=self._next_image).pack(side='left', padx=5)
        ttk.Button(right_btn_frame, text="다음 화 ⏭", command=self._go_next_episode).pack(side='left', padx=5)

        # 3. Zoom Controls (Pack right, next to right buttons)
        zoom_frame = ttk.Frame(self.nav_frame)
        zoom_frame.pack(side='right', padx=10)

        ttk.Button(zoom_frame, text="-", width=2, command=self._zoom_out).pack(side='left')
        
        self.scale_var = tk.DoubleVar(value=100.0)
        self.entry_var = tk.StringVar(value="100")
        self.zoom_entry = ttk.Entry(zoom_frame, textvariable=self.entry_var, width=4, justify='center')
        self.zoom_entry.pack(side='left', padx=2)
        self.zoom_entry.bind("<Return>", self._on_entry_change)
        
        ttk.Button(zoom_frame, text="+", width=2, command=self._zoom_in).pack(side='left')
        ttk.Label(zoom_frame, text="%").pack(side='left', padx=(2, 5))
        
        ttk.Button(zoom_frame, text="원본", width=4, command=self._reset_zoom).pack(side='left')

        # 4. Center Info (Pack last to fill remaining space)
        self.info_label = ttk.Label(self.nav_frame, text="", anchor='center')
        self.info_label.pack(side='left', fill='x', expand=True)

        # Bindings
        self.bind("<Left>", lambda e: self._prev_image())
        self.bind("<Right>", lambda e: self._next_image())
        self.bind("<Up>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.bind("<Down>", lambda e: self.canvas.yview_scroll(1, "units"))
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Configure>", self._on_resize)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def _on_resize(self, event):
        # Only redraw if the viewer is initialized and has images
        if hasattr(self, 'image_files') and self.image_files:
            # If in fit mode, recalculate fit. Otherwise keep current scale.
            self._show_image(calculate_fit=self.fit_mode)

    def _zoom_in(self):
        current = self.scale_var.get()
        new_val = min(300, current + 5)
        self._update_zoom(new_val)

    def _zoom_out(self):
        current = self.scale_var.get()
        new_val = max(10, current - 5)
        self._update_zoom(new_val)

    def _reset_zoom(self):
        self._update_zoom(100.0)

    def _update_zoom(self, value):
        self.fit_mode = False
        self.scale_var.set(value)
        self.entry_var.set(f"{value:.0f}")
        self._show_image(calculate_fit=False)

    def _on_entry_change(self, event):
        try:
            val = float(self.entry_var.get())
            # Clamp value
            val = max(10, min(300, val))
            self._update_zoom(val)
        except ValueError:
            pass

    def _show_image(self, calculate_fit=True):
        if not self.image_files: return
        
        img_path = self.image_files[self.current_index]
        try:
            pil_img = Image.open(img_path)
            img_width, img_height = pil_img.size
            
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            # Initial fallback if window is not yet drawn
            if canvas_width < 10: canvas_width = 1000
            if canvas_height < 10: canvas_height = 800
            
            ratio = 1.0
            
            if calculate_fit:
                self.fit_mode = True
                width_ratio = (canvas_width - 20) / img_width
                height_ratio = (canvas_height - 20) / img_height
                ratio = min(width_ratio, height_ratio)
                
                # Update UI controls without triggering callbacks
                self._updating_ui = True
                self.scale_var.set(ratio * 100)
                self.entry_var.set(f"{ratio * 100:.0f}")
                self._updating_ui = False
            else:
                ratio = self.scale_var.get() / 100.0
            
            new_width = int(img_width * ratio)
            new_height = int(img_height * ratio)
            
            # High quality resize (Fixed to LANCZOS)
            pil_img = pil_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            self.tk_img = ImageTk.PhotoImage(pil_img)
            self.canvas.delete("all")
            
            # Center the image in canvas
            # If image is smaller than canvas, center it.
            # If larger, scrollregion handles it.
            x_pos = max(canvas_width // 2, new_width // 2)
            y_pos = max(canvas_height // 2, new_height // 2)
            
            self.canvas.create_image(x_pos, y_pos, anchor='center', image=self.tk_img)
            self.canvas.config(scrollregion=(0, 0, new_width, new_height))
            
            self.info_label.config(text=f"[{self.current_index + 1} / {len(self.image_files)}] {os.path.basename(img_path)}")
            
        except Exception as e:
            self.info_label.config(text=f"Error loading image: {e}")

    def _prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._show_image(calculate_fit=self.fit_mode) # Keep fit mode
        else:
            pass

    def _next_image(self):
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self._show_image(calculate_fit=self.fit_mode) # Keep fit mode
        else:
            self._try_next_episode()

    def _try_next_episode(self):
        self._go_next_episode()

    def _go_next_episode(self):
        if self._navigating: return
        self._navigating = True
        try:
            if not self.current_db_id:
                return

            next_ep = db.get_next_episode(self.current_db_id)
            if next_ep:
                next_id, next_title = next_ep
                self._load_episode(next_id, next_title)
            else:
                if time.time() - self._last_alert_time > 1.5:
                    self._last_alert_time = time.time()
                    messagebox.showinfo("알림", "다음 화가 없습니다.")
        finally:
            self._navigating = False

    def _go_prev_episode(self):
        if self._navigating: return
        self._navigating = True
        try:
            if not self.current_db_id:
                return

            prev_ep = db.get_prev_episode(self.current_db_id)
            if prev_ep:
                prev_id, prev_title = prev_ep
                self._load_episode(prev_id, prev_title)
            else:
                if time.time() - self._last_alert_time > 1.5:
                    self._last_alert_time = time.time()
                    messagebox.showinfo("알림", "이전 화가 없습니다.")
        finally:
            self._navigating = False

    def _load_episode(self, ep_id, ep_title):
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ml.local_store_path 
                FROM crawled_urls cu
                JOIN mana_lists ml ON cu.mana_list_id = ml.id
                WHERE cu.id = ?
            """, (ep_id,))
            row = cursor.fetchone()
            base_path = row[0] if row and row[0] else "downloaded_files"
        
        safe_title = CrawlerEngine._sanitize_folder_name(ep_title)
        ep_path = os.path.join(base_path, safe_title)
        
        if os.path.exists(ep_path):
            self.folder_path = ep_path
            self.title(f"Viewer - {ep_title}")
            self.current_db_id = ep_id
            self.image_files = self._get_image_files()
            self.current_index = 0
            self.fit_mode = True # Reset zoom on episode change
            
            if not self.image_files:
                self.canvas.delete("all")
                self.info_label.config(text="이미지를 찾을 수 없습니다.")
            else:
                self._show_image(calculate_fit=True)
        else:
            messagebox.showwarning("오류", f"폴더를 찾을 수 없습니다:\n{ep_path}")

    def _show_toast(self, message, duration=2000):
        if hasattr(self, '_current_toast') and self._current_toast.winfo_exists():
            self._current_toast.destroy()

        toast_frame = ttk.Frame(self, relief='solid', borderwidth=1)
        self._current_toast = toast_frame
        
        label = ttk.Label(toast_frame, text=message, padding=(20, 10), background="#333333", foreground="#ffffff")
        label.pack()
        
        toast_frame.place(relx=0.5, rely=0.85, anchor='center')
        self.after(duration, toast_frame.destroy)

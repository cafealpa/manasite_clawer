import tkinter as tk
from tkinter import ttk, messagebox
import os
from data.db_repository import db
from ui.image_viewer import ImageViewer
from utils.logger import logger
from core.engine import CrawlerEngine

class DBViewer(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        
        self.check_vars = {}
        self._create_widgets()
        self.load_data()

    def _create_widgets(self):
        # --- Top Frames ---
        top_frame = ttk.Frame(self)
        top_frame.pack(pady=(10, 0), padx=10, fill='x', expand=False)

        search_frame = ttk.Frame(top_frame)
        search_frame.pack(fill='x', expand=True)

        search_label = ttk.Label(search_frame, text="제목 검색:")
        search_label.pack(side='left', padx=(0, 5))
        self.search_entry = ttk.Entry(search_frame, width=40)
        self.search_entry.pack(side='left', fill='x', expand=True)
        self.search_entry.bind("<Return>", self.search_data)
        search_button = ttk.Button(search_frame, text="검색", command=self.search_data)
        search_button.pack(side='left', padx=5)

        refresh_button = ttk.Button(search_frame, text="새로고침", command=self.refresh_data)
        refresh_button.pack(side='left', padx=5)

        action_frame = ttk.Frame(top_frame)
        action_frame.pack(fill='x', expand=True, pady=(5,0))

        delete_button = ttk.Button(action_frame, text="선택삭제", command=self.delete_selected)
        delete_button.pack(side='left')
        
        ttk.Label(action_frame, text="* 항목을 더블클릭하면 뷰어를 엽니다.", foreground='gray').pack(side='right')

        # --- Treeview Frame ---
        tree_frame = ttk.Frame(self)
        tree_frame.pack(pady=10, padx=10, fill='both', expand=True)

        # --- Treeview ---
        self.tree = ttk.Treeview(tree_frame, columns=("Select", "ID", "Page Title", "Crawled At", "URL"), show='headings')
        
        # Setup Headings with Sort Command
        self.tree.heading("Select", text="선택", command=self.toggle_all_checkboxes)
        self.tree.heading("ID", text="ID", command=lambda: self.sort_column("ID", False))
        self.tree.heading("Page Title", text="제목", command=lambda: self.sort_column("Page Title", False))
        self.tree.heading("Crawled At", text="수집일시", command=lambda: self.sort_column("Crawled At", False))
        self.tree.heading("URL", text="URL", command=lambda: self.sort_column("URL", False))

        self.tree.column("Select", width=50, anchor='center')
        self.tree.column("ID", width=50, anchor='center')
        self.tree.column("Page Title", width=250)
        self.tree.column("Crawled At", width=150, anchor='center')
        self.tree.column("URL", width=400)

        # --- Scrollbar ---
        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.tree.pack(side='left', fill='both', expand=True)

        # --- Bindings ---
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Double-1>", self.on_double_click)

    def sort_column(self, col, reverse):
        """Sort treeview content by column"""
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        try:
            if col == "ID":
                l.sort(key=lambda t: int(t[0]), reverse=reverse)
            else:
                l.sort(reverse=reverse)
        except ValueError:
            l.sort(reverse=reverse)

        # Rearrange items in sorted positions
        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        # Update heading command to reverse sort next time
        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def load_data(self, search_term=""):
        # Clear existing data
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.check_vars.clear()

        # Load new data
        try:
            rows = db.search_crawled_urls(search_term)
            for row in rows:
                item_id = row[0]
                self.check_vars[item_id] = tk.BooleanVar(value=False)
                # Treeview에 데이터 삽입 (체크박스 상태는 텍스트로 표현)
                self.tree.insert("", "end", values=("☐",) + row, tags=(item_id,))

        except Exception as e:
            messagebox.showerror("데이터베이스 오류", f"데이터를 불러오는 중 오류가 발생했습니다: {e}")

    def on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        # Heading click is handled by command=... in heading setup
        
        if region != "cell":
            return

        item_iid = self.tree.identify_row(event.y)
        if not item_iid:
            return

        col = self.tree.identify_column(event.x)
        if col == "#1": # "Select" column
            item_id = self.tree.item(item_iid, "tags")[0]
            var = self.check_vars[int(item_id)]
            var.set(not var.get())
            self.update_checkbox_display(item_iid, var.get())

    def on_double_click(self, event):
        item_iid = self.tree.identify_row(event.y)
        if not item_iid:
            return
        
        values = self.tree.item(item_iid, "values")
        page_title = values[2]
        item_id = self.tree.item(item_iid, "tags")[0]
        
        logger.info(f"Double-clicked item ID: {item_id}, Title: {page_title}")
        
        folder_path = self._get_folder_path(item_id, page_title)
        logger.info(f"Resolved folder path: {folder_path}")
        
        if folder_path and os.path.exists(folder_path):
            logger.info(f"Opening ImageViewer for: {folder_path}")
            # Pass current_db_id to enable next episode navigation
            ImageViewer(self, folder_path, title=page_title, current_db_id=int(item_id))
        else:
            logger.warning(f"Folder not found: {folder_path}")
            messagebox.showwarning("알림", f"이미지 폴더를 찾을 수 없습니다.\n경로: {folder_path}")

    def _get_folder_path(self, item_id, page_title):
        safe_title = CrawlerEngine._sanitize_folder_name(page_title)
        
        # Query DB for the local_store_path of the parent mana_list
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ml.local_store_path 
                FROM crawled_urls cu
                JOIN mana_lists ml ON cu.mana_list_id = ml.id
                WHERE cu.id = ?
            """, (item_id,))
            row = cursor.fetchone()
            
            base_path = None
            if row and row[0]:
                base_path = row[0]
                logger.debug(f"Found base path in DB: {base_path}")
            else:
                logger.debug("No base path in DB, using default 'downloaded_files'")
                base_path = "downloaded_files"
                
            full_path = os.path.join(base_path, safe_title)
            return full_path

    def update_checkbox_display(self, item_iid, is_checked):
        current_values = self.tree.item(item_iid, 'values')
        new_values = list(current_values)
        new_values[0] = "☑" if is_checked else "☐"
        self.tree.item(item_iid, values=tuple(new_values))

    def toggle_all_checkboxes(self):
        # Determine the new state (if any are unchecked, check all)
        any_unchecked = any(not var.get() for var in self.check_vars.values())
        new_state = any_unchecked

        for item_id, var in self.check_vars.items():
            var.set(new_state)

        for item_iid in self.tree.get_children():
            self.update_checkbox_display(item_iid, new_state)

    def search_data(self, event=None):
        search_term = self.search_entry.get()
        self.load_data(search_term)

    def refresh_data(self):
        self.search_entry.delete(0, tk.END)
        self.load_data()

    def delete_selected(self):
        selected_ids = [item_id for item_id, var in self.check_vars.items() if var.get()]

        if not selected_ids:
            messagebox.showinfo("알림", "삭제할 항목을 선택하세요.")
            return

        if messagebox.askyesno("확인", f"{len(selected_ids)}개의 항목을 정말 삭제하시겠습니까?"):
            try:
                deleted_count = db.delete_crawled_urls(selected_ids)
                messagebox.showinfo("성공", f"{deleted_count}개의 항목을 삭제했습니다.")
                self.load_data(self.search_entry.get()) # Refresh the list
            except Exception as e:
                messagebox.showerror("데이터베이스 오류", f"삭제 중 오류가 발생했습니다: {e}")

if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()  # 메인 창 숨기기
    app = DBViewer(root)
    root.mainloop()

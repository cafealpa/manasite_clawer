import sqlite3
from contextlib import contextmanager
from typing import Optional, List
from utils.config import config_manager
from utils.logger import logger

DB_FILE = 'crawled_pages.db'

class DBRepository:
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self._create_tables()
        self._migrate_schema()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _create_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS crawled_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    page_title TEXT,
                    list_url TEXT,
                    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()

    def _migrate_schema(self):
        """Attempts to migrate schema for existing tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Try adding list_url column if it doesn't exist
                cursor.execute("ALTER TABLE crawled_urls ADD COLUMN list_url TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                # Column likely already exists
                pass

    def get_config(self, key: str) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_config WHERE key = ?", (key,))
            result = cursor.fetchone()
            if result:
                # Decrypt value if it's sensitive (or everything for simplicity)
                # But typically only keys/passwords need encryption.
                # Here we decrypt everything assuming config_manager handles plain text gracefully.
                encrypted_value = result[0]
                return config_manager.decrypt_value(encrypted_value)
            return None

    def set_config(self, key: str, value: str):
        # Encrypt everything stored in config
        encrypted_value = config_manager.encrypt_value(value)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)", (key, encrypted_value))
            conn.commit()

    def is_url_crawled(self, url: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM crawled_urls WHERE url = ?", (url,))
            return cursor.fetchone() is not None

    def add_crawled_url(self, url: str, page_title: str, list_url: str = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO crawled_urls (url, page_title, list_url) VALUES (?, ?, ?)", (url, page_title, list_url))
                conn.commit()
                # logger.debug(f"DB Saved: {url}")
            except sqlite3.IntegrityError:
                # logger.debug(f"DB Duplicate ignored: {url}")
                pass

    def delete_crawled_urls(self, ids: List[int]) -> int:
        if not ids:
            return 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' for _ in ids)
            query = f"DELETE FROM crawled_urls WHERE id IN ({placeholders})"
            cursor.execute(query, ids)
            conn.commit()
            return cursor.rowcount

    def search_crawled_urls(self, search_term: str = "") -> List[tuple]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT id, page_title, crawled_at, url FROM crawled_urls"
            params = []
            if search_term:
                query += " WHERE page_title LIKE ?"
                params.append(f"%{search_term}%")
            query += " ORDER BY crawled_at DESC"
            
            cursor.execute(query, params)
            return cursor.fetchall()

# Global Repository Instance
db = DBRepository()

import os
import sqlite3
from contextlib import contextmanager
from typing import Optional, List
from utils.config import config_manager
from utils.logger import logger

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'crawled_pages.db')

class DBRepository:
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self._initialized = False
        # self._create_tables() # Lazy Init
        # self._migrate_schema()

    def _initialize_db(self):
        if not self._initialized:
            self._initialized = True
            try:
                self._create_tables()
                self._migrate_schema()
            except Exception:
                self._initialized = False
                raise

    @contextmanager
    def _get_connection(self):
        if not self._initialized:
            self._initialize_db()
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _create_tables(self):
        # Use direct connection to avoid recursion
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mana_lists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mana_list_url TEXT NOT NULL UNIQUE,
                    mana_title TEXT,
                    local_store_path TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS crawled_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    page_title TEXT,
                    list_url TEXT,
                    mana_list_id INTEGER,
                    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (mana_list_id) REFERENCES mana_lists(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _ensure_config_table(self, conn):
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()

    def set_db_path(self, db_path: str):
        if db_path and db_path != self.db_path:
            self.db_path = db_path
            self._initialized = False

    def _migrate_schema(self):
        """Attempts to migrate schema for existing tables."""
        # Use direct connection to avoid recursion
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            try:
                # Try adding list_url column if it doesn't exist
                cursor.execute("ALTER TABLE crawled_urls ADD COLUMN list_url TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                # Column likely already exists
                pass
            try:
                cursor.execute("ALTER TABLE crawled_urls ADD COLUMN mana_list_id INTEGER")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE mana_lists ADD COLUMN local_store_path TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO mana_lists (mana_list_url)
                    SELECT DISTINCT list_url
                    FROM crawled_urls
                    WHERE list_url IS NOT NULL AND list_url != ''
                """)
                cursor.execute("""
                    UPDATE crawled_urls
                    SET mana_list_id = (
                        SELECT id FROM mana_lists WHERE mana_lists.mana_list_url = crawled_urls.list_url
                    )
                    WHERE mana_list_id IS NULL AND list_url IS NOT NULL AND list_url != ''
                """)
                conn.commit()
            except sqlite3.OperationalError:
                pass
        finally:
            conn.close()

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

    def get_global_config(self, key: str) -> Optional[str]:
        conn = sqlite3.connect(DB_FILE)
        try:
            self._ensure_config_table(conn)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_config WHERE key = ?", (key,))
            result = cursor.fetchone()
            if result:
                return config_manager.decrypt_value(result[0])
            return None
        finally:
            conn.close()

    def set_global_config(self, key: str, value: str):
        encrypted_value = config_manager.encrypt_value(value)
        conn = sqlite3.connect(DB_FILE)
        try:
            self._ensure_config_table(conn)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)", (key, encrypted_value))
            conn.commit()
        finally:
            conn.close()

    def is_url_crawled(self, url: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM crawled_urls WHERE url = ?", (url,))
            return cursor.fetchone() is not None

    def _get_or_create_mana_list(
        self,
        mana_list_url: str,
        mana_title: str = None,
        local_store_path: str = None,
    ) -> Optional[int]:
        if not mana_list_url:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO mana_lists (mana_list_url, mana_title, local_store_path) VALUES (?, ?, ?)",
                (mana_list_url, mana_title, local_store_path)
            )
            if mana_title:
                cursor.execute(
                    "UPDATE mana_lists SET mana_title = ? WHERE mana_list_url = ? AND (mana_title IS NULL OR mana_title != ?)",
                    (mana_title, mana_list_url, mana_title)
                )
            if local_store_path:
                cursor.execute(
                    "UPDATE mana_lists SET local_store_path = ? WHERE mana_list_url = ? AND (local_store_path IS NULL OR local_store_path != ?)",
                    (local_store_path, mana_list_url, local_store_path)
                )
            conn.commit()
            cursor.execute("SELECT id FROM mana_lists WHERE mana_list_url = ?", (mana_list_url,))
            row = cursor.fetchone()
            return row[0] if row else None

    def add_crawled_url(
        self,
        url: str,
        page_title: str,
        list_url: str = None,
        list_title: str = None,
        local_store_path: str = None,
    ):
        mana_list_id = self._get_or_create_mana_list(list_url, list_title, local_store_path)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO crawled_urls (url, page_title, list_url, mana_list_id) VALUES (?, ?, ?, ?)",
                    (url, page_title, list_url, mana_list_id)
                )
                conn.commit()
                # logger.debug(f"DB Saved: {url}")
            except sqlite3.IntegrityError as e:
                if "UNIQUE" in str(e):
                    logger.debug(f"DB Duplicate ignored: {url}")
                else:
                    logger.error(f"DB Insert failed for {url}: {e}")

    def upsert_mana_list(self, mana_list_url: str, mana_title: str = None, local_store_path: str = None):
        self._get_or_create_mana_list(mana_list_url, mana_title, local_store_path)

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

    def get_latest_mana_lists(self) -> List[tuple]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ml.mana_list_url, ml.mana_title, MAX(cu.crawled_at) AS last_crawled
                FROM crawled_urls cu
                JOIN mana_lists ml ON ml.id = cu.mana_list_id
                GROUP BY ml.id, ml.mana_list_url, ml.mana_title
                ORDER BY last_crawled DESC
            """)
            return cursor.fetchall()

# Global Repository Instance
db = DBRepository()

import sqlite3
import os
import threading

class StateManager:
    def __init__(self, db_path="backup_state.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = None
        self._init_db()

    def _get_conn(self):
        """Returns the persistent connection, creating it if necessary."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            # Main files table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    size INTEGER,
                    mtime REAL,
                    md5 TEXT,
                    drive_id TEXT,
                    status TEXT,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Upload sessions table for resume support
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    path TEXT PRIMARY KEY,
                    upload_url TEXT,
                    upload_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Indexing for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON files(status)")
            conn.commit()

    def get_file_status(self, path):
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT size, mtime, md5, drive_id, status FROM files WHERE path = ?", (path,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def update_file(self, path, size, mtime, md5=None, drive_id=None, status="pending"):
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO files (path, size, mtime, md5, drive_id, status, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (path, size, mtime, md5, drive_id, status))
            conn.commit()

    def mark_deleted(self, path):
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files WHERE path = ?", (path,))
            conn.commit()

    def get_uploaded_metadata_map(self):
        """Returns a dict mapping path -> (size, mtime) for all uploaded files."""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT path, size, mtime FROM files WHERE status = 'uploaded'")
            rows = cursor.fetchall()
            return {row['path']: (row['size'], row['mtime']) for row in rows}

    def get_total_backed_up_count(self):
        """Returns the total number of unique files ever backed up (cumulative)."""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM files WHERE status = 'uploaded'")
            return cursor.fetchone()[0]

    def save_session(self, path, upload_url, upload_id=None):
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO sessions (path, upload_url, upload_id)
                VALUES (?, ?, ?)
            ''', (path, upload_url, upload_id))
            conn.commit()

    def get_session(self, path):
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT upload_url, upload_id FROM sessions WHERE path = ?", (path,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def clear_session(self, path):
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE path = ?", (path,))
            conn.commit()

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

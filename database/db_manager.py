import sqlite3
import datetime
from pathlib import Path

class DatabaseManager:
    def __init__(self, db_path: str = "history.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initializes the SQLite database and creates tables if they do not exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS job_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT UNIQUE NOT NULL,
                    title TEXT,
                    company TEXT,
                    status TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def add_application(self, job_id: str, title: str, company: str, status: str = "APPLIED"):
        """Records a new job application."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO job_applications (job_id, title, company, status) VALUES (?, ?, ?, ?)",
                    (job_id, title, company, status)
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            print(f"[DB] Job {job_id} already exists in database.")
            return False

    def is_job_applied(self, job_id: str) -> bool:
        """Checks if a job has already been applied to (or skipped/failed)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM job_applications WHERE job_id = ?", (job_id,))
            return cursor.fetchone() is not None

    def get_daily_application_count(self) -> int:
        """Counts how many applications were successful today."""
        today_start = datetime.datetime.now().strftime("%Y-%m-%d 00:00:00")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM job_applications WHERE status = 'APPLIED' AND applied_at >= ?",
                (today_start,)
            )
            return cursor.fetchone()[0]

# Singleton instance
db = DatabaseManager(str(Path(__file__).resolve().parent.parent / "history.db"))

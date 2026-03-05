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
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS search_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_role_index INTEGER DEFAULT 0,
                    last_date TEXT
                )
            ''')
            # Ensure there's always exactly one row
            cursor.execute("INSERT OR IGNORE INTO search_state (id, last_role_index, last_date) VALUES (1, 0, '')")
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

    def get_todays_role_index(self, total_roles: int) -> int:
        """Returns the role index for today, cycling to the next role each new day."""
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_role_index, last_date FROM search_state WHERE id = 1")
            row = cursor.fetchone()
            last_index, last_date = row[0], row[1]

            if last_date == today:
                # Same day — keep using the same role
                return last_index
            else:
                # New day — advance to next role
                new_index = (last_index + 1) % total_roles
                cursor.execute(
                    "UPDATE search_state SET last_role_index = ?, last_date = ? WHERE id = 1",
                    (new_index, today)
                )
                conn.commit()
                print(f"[DB] New day detected. Cycling role index: {last_index} → {new_index}")
                return new_index

# Singleton instance
db = DatabaseManager(str(Path(__file__).resolve().parent.parent / "history.db"))

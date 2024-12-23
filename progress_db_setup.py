# progress_db_setup.py
import sqlite3
import os

PROGRESS_DB_PATH = os.path.join(os.getcwd(), 'database', 'progress.db')

def setup_progress_db():
    os.makedirs(os.path.dirname(PROGRESS_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(PROGRESS_DB_PATH)
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
      user_id INTEGER PRIMARY KEY,
      name TEXT,
      diabetes_type TEXT,
      knowledge_level INTEGER,
      points INTEGER DEFAULT 0
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS progress (
      user_id INTEGER,
      module_id TEXT,
      lesson_id TEXT,
      completed INTEGER DEFAULT 0,
      FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS rewards (
      user_id INTEGER,
      badge TEXT,
      FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    ''')

    conn.commit()
    conn.close()

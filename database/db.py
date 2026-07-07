import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            product_name TEXT,
            search_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            results TEXT
        )
    """)
    # Check if 'results' column exists in case the table was created previously without it
    cursor.execute("PRAGMA table_info(search_history)")
    columns = [row[1] for row in cursor.fetchall()]
    if "results" not in columns:
        cursor.execute("ALTER TABLE search_history ADD COLUMN results TEXT")
    conn.commit()
    conn.close()

def save_search(query: str, product_name: str, search_type: str, results: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO search_history (query, product_name, search_type, results) VALUES (?, ?, ?, ?)",
        (query, product_name, search_type, results)
    )
    conn.commit()
    conn.close()

def get_history():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, query, product_name, search_type, created_at, results FROM search_history ORDER BY id DESC")
    rows = cursor.fetchall()
    history = [dict(row) for row in rows]
    conn.close()
    return history

def delete_history_item(item_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM search_history WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

def clear_all_history():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM search_history")
    conn.commit()
    conn.close()

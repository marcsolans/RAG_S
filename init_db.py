"""Crea l'esquema SQLite per al data layer de Chainlit (història de xats)."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "chat_history.db"

DDL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    identifier TEXT NOT NULL UNIQUE,
    metadata TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT
);

CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    createdAt TEXT,
    name TEXT,
    userId TEXT,
    userIdentifier TEXT,
    tags TEXT,
    metadata TEXT,
    FOREIGN KEY (userId) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS steps (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    threadId TEXT NOT NULL,
    parentId TEXT,
    streaming INTEGER NOT NULL DEFAULT 0,
    waitForAnswer INTEGER,
    isError INTEGER,
    metadata TEXT,
    tags TEXT,
    input TEXT,
    output TEXT,
    createdAt TEXT,
    command TEXT,
    start TEXT,
    "end" TEXT,
    generation TEXT,
    showInput TEXT,
    language TEXT,
    indent INTEGER,
    defaultOpen INTEGER,
    modes TEXT,
    FOREIGN KEY (threadId) REFERENCES threads(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS elements (
    id TEXT PRIMARY KEY,
    threadId TEXT,
    type TEXT,
    url TEXT,
    chainlitKey TEXT,
    name TEXT NOT NULL,
    display TEXT,
    objectKey TEXT,
    size TEXT,
    page INTEGER,
    language TEXT,
    forId TEXT,
    mime TEXT,
    props TEXT,
    FOREIGN KEY (threadId) REFERENCES threads(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feedbacks (
    id TEXT PRIMARY KEY,
    forId TEXT NOT NULL,
    threadId TEXT NOT NULL,
    value INTEGER NOT NULL,
    comment TEXT,
    FOREIGN KEY (threadId) REFERENCES threads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_threads_user ON threads(userIdentifier);
CREATE INDEX IF NOT EXISTS idx_steps_thread ON steps(threadId);
CREATE INDEX IF NOT EXISTS idx_elements_thread ON elements(threadId);
CREATE INDEX IF NOT EXISTS idx_feedbacks_thread ON feedbacks(threadId);
"""


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(DDL)
    conn.commit()
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    conn.close()
    print(f"✅ Base de dades inicialitzada a {DB_PATH}")
    print(f"   Taules: {tables}")


if __name__ == "__main__":
    main()

import sqlite3
import os
import time

DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "bilibili-watchlater")
DB_PATH = os.path.join(DATA_DIR, "data.db")


def get_db() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
            aid             INTEGER PRIMARY KEY,
            bvid            TEXT NOT NULL,
            title           TEXT NOT NULL,
            cover_url       TEXT,
            duration        INTEGER,
            author_name     TEXT,
            author_mid      INTEGER,
            added_at        INTEGER NOT NULL,
            ctime           INTEGER,
            fetched_at      INTEGER NOT NULL,
            is_watched      INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tags (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL UNIQUE,
            color           TEXT DEFAULT '#ffffff',
            created_at      INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS video_tags (
            video_aid       INTEGER NOT NULL,
            tag_id          INTEGER NOT NULL,
            assigned_at     INTEGER NOT NULL,
            PRIMARY KEY (video_aid, tag_id),
            FOREIGN KEY (video_aid) REFERENCES videos(aid) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS credential_store (
            key             TEXT PRIMARY KEY,
            value           TEXT NOT NULL,
            updated_at      INTEGER NOT NULL
        );
    """)


# ── Credential CRUD ──

def save_credential(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO credential_store (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, int(time.time())),
    )
    conn.commit()


def load_credentials(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT key, value FROM credential_store").fetchall()
    return {row["key"]: row["value"] for row in rows}


def clear_credentials(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM credential_store")
    conn.commit()


# ── Video CRUD ──

def upsert_video(conn: sqlite3.Connection, v: dict) -> None:
    conn.execute("""
        INSERT INTO videos (aid, bvid, title, cover_url, duration,
            author_name, author_mid, added_at, ctime, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(aid) DO UPDATE SET
            bvid=excluded.bvid, title=excluded.title, cover_url=excluded.cover_url,
            duration=excluded.duration, author_name=excluded.author_name,
            author_mid=excluded.author_mid, added_at=excluded.added_at,
            ctime=excluded.ctime, fetched_at=excluded.fetched_at
    """, (
        v["aid"], v["bvid"], v["title"], v.get("cover_url", ""),
        v.get("duration", 0), v.get("author_name", ""), v.get("author_mid", 0),
        v["added_at"], v.get("ctime", 0), int(time.time()),
    ))
    conn.commit()


def list_videos(conn: sqlite3.Connection, tag: str | None = None,
                page: int = 1, limit: int = 20, sort: str = "added") -> list:
    offset = (page - 1) * limit
    order = {"added": "v.added_at DESC", "title": "v.title ASC",
             "author": "v.author_name ASC"}.get(sort, "v.added_at DESC")

    if tag:
        rows = conn.execute(f"""
            SELECT v.*, GROUP_CONCAT(t.name, ', ') AS tag_list
            FROM videos v
            JOIN video_tags vt ON v.aid = vt.video_aid
            JOIN tags t ON vt.tag_id = t.id
            WHERE t.name = ? AND v.is_watched = 0
            GROUP BY v.aid
            ORDER BY {order}
            LIMIT ? OFFSET ?
        """, (tag, limit, offset)).fetchall()
    else:
        rows = conn.execute(f"""
            SELECT v.*, GROUP_CONCAT(t.name, ', ') AS tag_list
            FROM videos v
            LEFT JOIN video_tags vt ON v.aid = vt.video_aid
            LEFT JOIN tags t ON vt.tag_id = t.id
            WHERE v.is_watched = 0
            GROUP BY v.aid
            ORDER BY {order}
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
    return [dict(r) for r in rows]


def count_videos(conn: sqlite3.Connection, tag: str | None = None) -> int:
    if tag:
        row = conn.execute("""
            SELECT COUNT(*) AS cnt FROM videos v
            JOIN video_tags vt ON v.aid = vt.video_aid
            JOIN tags t ON vt.tag_id = t.id
            WHERE t.name = ? AND v.is_watched = 0
        """, (tag,)).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM videos WHERE is_watched = 0"
        ).fetchone()
    return row["cnt"] if row else 0


def get_video(conn: sqlite3.Connection, bvid: str) -> dict | None:
    row = conn.execute("SELECT * FROM videos WHERE bvid = ?", (bvid,)).fetchone()
    return dict(row) if row else None


def get_video_tags(conn: sqlite3.Connection, aid: int) -> list[dict]:
    rows = conn.execute("""
        SELECT t.id, t.name, t.color FROM tags t
        JOIN video_tags vt ON t.id = vt.tag_id
        WHERE vt.video_aid = ?
    """, (aid,)).fetchall()
    return [dict(r) for r in rows]


def search_videos(conn: sqlite3.Connection, query: str,
                  page: int = 1, limit: int = 20) -> list[dict]:
    offset = (page - 1) * limit
    pattern = f"%{query}%"
    rows = conn.execute("""
        SELECT v.*, GROUP_CONCAT(t.name, ', ') AS tag_list
        FROM videos v
        LEFT JOIN video_tags vt ON v.aid = vt.video_aid
        LEFT JOIN tags t ON vt.tag_id = t.id
        WHERE v.is_watched = 0 AND (v.title LIKE ? OR v.author_name LIKE ?)
        GROUP BY v.aid
        ORDER BY v.added_at DESC
        LIMIT ? OFFSET ?
    """, (pattern, pattern, limit, offset)).fetchall()
    return [dict(r) for r in rows]


def search_count(conn: sqlite3.Connection, query: str) -> int:
    pattern = f"%{query}%"
    row = conn.execute("""
        SELECT COUNT(*) AS cnt FROM videos
        WHERE is_watched = 0 AND (title LIKE ? OR author_name LIKE ?)
    """, (pattern, pattern)).fetchone()
    return row["cnt"] if row else 0


def mark_watched(conn: sqlite3.Connection, aid: int) -> None:
    conn.execute("UPDATE videos SET is_watched = 1 WHERE aid = ?", (aid,))
    conn.commit()


def stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute(
        "SELECT COUNT(*) AS cnt FROM videos WHERE is_watched = 0"
    ).fetchone()["cnt"]
    watched = conn.execute(
        "SELECT COUNT(*) AS cnt FROM videos WHERE is_watched = 1"
    ).fetchone()["cnt"]
    tags = conn.execute("SELECT COUNT(*) AS cnt FROM tags").fetchone()["cnt"]
    return {"total": total, "watched": watched, "tags": tags}


# ── Tag CRUD ──

def add_tag(conn: sqlite3.Connection, name: str, color: str = "#ffffff") -> int:
    cur = conn.execute(
        "INSERT INTO tags (name, color, created_at) VALUES (?, ?, ?)",
        (name, color, int(time.time())),
    )
    conn.commit()
    return cur.lastrowid


def remove_tag(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute("DELETE FROM tags WHERE name = ?", (name,))
    conn.commit()
    return cur.rowcount > 0


def get_tag(conn: sqlite3.Connection, name: str) -> dict | None:
    row = conn.execute("SELECT * FROM tags WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def list_tags(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("""
        SELECT t.*, COUNT(vt.video_aid) AS video_count
        FROM tags t
        LEFT JOIN video_tags vt ON t.id = vt.tag_id
        LEFT JOIN videos v ON vt.video_aid = v.aid AND v.is_watched = 0
        GROUP BY t.id
        ORDER BY t.name
    """).fetchall()
    return [dict(r) for r in rows]


def assign_tag(conn: sqlite3.Connection, aid: int, tag_name: str) -> bool:
    tag = get_tag(conn, tag_name)
    if not tag:
        return False
    conn.execute(
        "INSERT OR IGNORE INTO video_tags (video_aid, tag_id, assigned_at) VALUES (?, ?, ?)",
        (aid, tag["id"], int(time.time())),
    )
    conn.commit()
    return True


def unassign_tag(conn: sqlite3.Connection, aid: int, tag_name: str) -> bool:
    tag = get_tag(conn, tag_name)
    if not tag:
        return False
    conn.execute(
        "DELETE FROM video_tags WHERE video_aid = ? AND tag_id = ?",
        (aid, tag["id"]),
    )
    conn.commit()
    return True

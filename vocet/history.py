"""Local dictation history in SQLite (Python's built-in database, one file, no server).

Stored in %LOCALAPPDATA%\\Vocet\\history.db, and it never leaves the machine.
What we keep per dictation: the text, when, how long you spoke, which app it
went into (the program name only, e.g. "Word", never window titles, which can
contain email subjects etc.), and timings. Audio is not stored. With AI formatting,
`text` is what was pasted and `original_text` your words before the formatter changed
them, so the original is never lost.

Retention is a setting (off / 1 / 7 / 30 days / forever). Deleting is real
deletion followed by VACUUM, so the text doesn't linger in free pages of the file.
"""

import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS dictations (
    id          INTEGER PRIMARY KEY,
    created_at  REAL NOT NULL,      -- unix time
    text        TEXT NOT NULL,      -- what was inserted (the AI-formatted version, if it was used)
    raw_text    TEXT,               -- what the model heard, before snippets/dictionary
    audio_s     REAL,
    words       INTEGER,
    app         TEXT,
    app_path    TEXT,               -- program file, only to show its icon
    language    TEXT,               -- "en", "de", ...
    outcome     TEXT,               -- inserted | copied (= not pasted: kept here only)
    latency_ms  REAL,
    model       TEXT,
    original_text TEXT,             -- your words before AI formatting, if it changed them (else NULL)
    formatting  TEXT                -- what AI formatting did: formatted | skipped | timed out | rejected: ... | off
);
CREATE INDEX IF NOT EXISTS dictations_created ON dictations(created_at);
"""

TYPING_WPM = 40  # average typing speed, for the "time saved" estimate


class History:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(dictations)")}
        for column in ("app_path", "language", "original_text", "formatting"):  # databases created before these existed
            if column not in columns:
                self.db.execute(f"ALTER TABLE dictations ADD COLUMN {column} TEXT")

    def add(self, text: str, raw_text: str, audio_s: float, app: str, outcome: str,
            latency_ms: float, model: str, created_at: float | None = None, app_path: str = "",
            language: str = "", original_text: str | None = None, formatting: str = "") -> int:
        """original_text: the text before AI formatting; kept only if it differs from text."""
        if original_text == text:
            original_text = None
        cur = self.db.execute(
            "INSERT INTO dictations (created_at, text, raw_text, audio_s, words, app, app_path, language, outcome, "
            "latency_ms, model, original_text, formatting) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (created_at or time.time(), text, raw_text, audio_s, len(text.split()), app, app_path, language, outcome,
             latency_ms, model, original_text or None, formatting))
        self.db.commit()
        return cur.lastrowid

    def recent(self, limit: int = 200, query: str = "") -> list[dict]:
        sql = "SELECT * FROM dictations"
        args: list = []
        if query.strip():
            sql += " WHERE text LIKE ? ESCAPE '\\'"
            escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            args.append(f"%{escaped}%")
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.db.execute(sql, args)]

    def get(self, entry_id: int) -> dict | None:
        row = self.db.execute("SELECT * FROM dictations WHERE id = ?", (entry_id,)).fetchone()
        return dict(row) if row else None

    def delete(self, entry_id: int) -> None:
        self.db.execute("DELETE FROM dictations WHERE id = ?", (entry_id,))
        self.db.commit()

    def clear(self) -> None:
        self.db.execute("DELETE FROM dictations")
        self.db.commit()
        self.db.execute("VACUUM")

    def prune(self, keep_days: int | None) -> int:
        """keep_days: None = forever, 0 = keep nothing. Returns rows removed."""
        if keep_days is None:
            return 0
        if keep_days == 0:  # keep nothing: also a row saved in this very clock tick
            n = self.db.execute("DELETE FROM dictations").rowcount
        else:
            cutoff = time.time() - keep_days * 86400
            n = self.db.execute("DELETE FROM dictations WHERE created_at < ?", (cutoff,)).rowcount
        self.db.commit()
        if n:
            self.db.execute("VACUUM")
        return n

    def stats(self, days: int = 7, today: date | None = None) -> dict:
        """Words, speaking pace, time saved vs typing, and the daily streak."""
        today = today or date.today()
        since = datetime.combine(today - timedelta(days=days - 1), datetime.min.time()).timestamp()
        row = self.db.execute("SELECT COALESCE(SUM(words), 0) AS words, COALESCE(SUM(audio_s), 0) AS audio_s, "
                              "COUNT(*) AS n FROM dictations WHERE created_at >= ?", (since,)).fetchone()
        words, audio_s = row["words"], row["audio_s"]
        wpm = words / (audio_s / 60) if audio_s > 5 else 0
        saved_min = max(0.0, words / TYPING_WPM - audio_s / 60)
        day_set = {date.fromtimestamp(r[0]) for r in self.db.execute("SELECT created_at FROM dictations")}
        streak, d = 0, today
        if d not in day_set:
            d -= timedelta(days=1)  # a streak survives until today is over
        while d in day_set:
            streak += 1
            d -= timedelta(days=1)
        # Home's week chart: words per day, oldest first (today last), and the week before, for the
        # "+18 % vs last week" chip.
        daily = []
        for k in range(days - 1, -1, -1):
            d = today - timedelta(days=k)
            lo = datetime.combine(d, datetime.min.time()).timestamp()
            hi = datetime.combine(d + timedelta(days=1), datetime.min.time()).timestamp()
            daily.append(self.db.execute("SELECT COALESCE(SUM(words), 0) FROM dictations WHERE created_at >= ? "
                                         "AND created_at < ?", (lo, hi)).fetchone()[0])
        before = since - days * 86400
        prev = self.db.execute("SELECT COALESCE(SUM(words), 0) FROM dictations WHERE created_at >= ? AND created_at < ?",
                               (before, since)).fetchone()[0]
        return {"words": words, "dictations": row["n"], "wpm": round(wpm), "saved_min": round(saved_min),
                "streak": streak, "daily": daily, "daily_labels": [(today - timedelta(days=k)).strftime("%a")[0]
                                                                   for k in range(days - 1, -1, -1)],
                "prev_words": prev}

    def close(self) -> None:
        self.db.close()


def day_label(ts: float, today: date | None = None) -> str:
    today = today or date.today()
    d = date.fromtimestamp(ts)
    if d == today:
        return "Today"
    if d == today - timedelta(days=1):
        return "Yesterday"
    if (today - d).days < 7:
        return d.strftime("%A")
    return d.strftime("%d %B %Y").lstrip("0")

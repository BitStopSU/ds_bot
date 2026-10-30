import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    discord_id INTEGER PRIMARY KEY,
    username TEXT,
    global_name TEXT,
    first_joined_at TEXT,
    last_seen_at TEXT,
    is_on_server INTEGER DEFAULT 1,
    verified_at TEXT,
    verified_by INTEGER,
    verify_status TEXT DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS staff_branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id INTEGER NOT NULL,
    branch TEXT NOT NULL,
    rank TEXT NOT NULL,
    joined_branch_at TEXT,
    UNIQUE(discord_id, branch)
);
CREATE TABLE IF NOT EXISTS punishments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    reason TEXT,
    issued_by INTEGER,
    issued_at TEXT,
    expires_at TEXT,
    active INTEGER DEFAULT 1,
    removed_by INTEGER,
    removed_at TEXT
);
CREATE TABLE IF NOT EXISTS voice_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id INTEGER NOT NULL,
    channel_id INTEGER,
    category TEXT,
    joined_at TEXT,
    left_at TEXT,
    duration_sec INTEGER
);
CREATE TABLE IF NOT EXISTS quotas (
    branch TEXT NOT NULL,
    rank TEXT NOT NULL,
    hours_per_week REAL DEFAULT 0,
    PRIMARY KEY(branch, rank)
);
CREATE TABLE IF NOT EXISTS currency (
    discord_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    total_earned INTEGER DEFAULT 0,
    total_spent INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS join_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id INTEGER NOT NULL,
    event TEXT NOT NULL,
    timestamp TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS antinuke_whitelist (
    discord_id INTEGER PRIMARY KEY,
    added_by INTEGER,
    added_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS protected_channels (
    channel_id INTEGER PRIMARY KEY,
    protected_by INTEGER,
    protected_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS antinuke_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id INTEGER NOT NULL,
    action TEXT,
    count INTEGER,
    timestamp TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    target_id INTEGER,
    description TEXT,
    evidence TEXT,
    status TEXT DEFAULT 'open',
    handled_by INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    handled_at TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    branch TEXT NOT NULL,
    hours_per_week INTEGER,
    past_experience TEXT,
    motivation TEXT,
    discord_experience TEXT,
    timezone TEXT,
    status TEXT DEFAULT 'pending',
    handled_by INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    handled_at TEXT
);
CREATE TABLE IF NOT EXISTS active_branch (
    discord_id INTEGER PRIMARY KEY,
    branch TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pun_user ON punishments(discord_id, active);
CREATE INDEX IF NOT EXISTS idx_voice_user ON voice_sessions(discord_id);
CREATE INDEX IF NOT EXISTS idx_app_user ON applications(user_id, status);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self):
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def set_setting(self, key: str, value: str):
        await self.conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value)
        )
        await self.conn.commit()

    async def get_setting(self, key: str):
        cur = await self.conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else None

    async def upsert_user(self, discord_id, username, global_name, joined_at):
        await self.conn.execute(
            """INSERT INTO users(discord_id, username, global_name, first_joined_at, last_seen_at, is_on_server)
               VALUES (?, ?, ?, ?, ?, 1)
               ON CONFLICT(discord_id) DO UPDATE SET username=excluded.username,
               global_name=excluded.global_name, last_seen_at=excluded.last_seen_at, is_on_server=1""",
            (discord_id, username, global_name, joined_at, joined_at),
        )
        await self.conn.commit()

    async def set_user_left(self, discord_id):
        await self.conn.execute(
            "UPDATE users SET is_on_server=0, last_seen_at=datetime('now') WHERE discord_id=?", (discord_id,)
        )
        await self.conn.commit()

    async def get_user(self, discord_id):
        cur = await self.conn.execute("SELECT * FROM users WHERE discord_id=?", (discord_id,))
        return await cur.fetchone()

    async def set_verify_status(self, discord_id, status, staff_id):
        await self.conn.execute(
            "UPDATE users SET verify_status=?, verified_at=datetime('now'), verified_by=? WHERE discord_id=?",
            (status, staff_id, discord_id),
        )
        await self.conn.commit()

    async def log_join_event(self, discord_id, event):
        await self.conn.execute(
            "INSERT INTO join_history(discord_id, event, timestamp) VALUES (?, ?, datetime('now'))",
            (discord_id, event),
        )
        await self.conn.commit()

    async def count_join_events(self, discord_id, event="join"):
        cur = await self.conn.execute(
            "SELECT COUNT(*) as c FROM join_history WHERE discord_id=? AND event=?", (discord_id, event)
        )
        row = await cur.fetchone()
        return row["c"] if row else 0

    async def add_staff(self, discord_id, branch, rank):
        await self.conn.execute(
            """INSERT INTO staff_branches(discord_id, branch, rank, joined_branch_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(discord_id, branch) DO UPDATE SET rank=excluded.rank""", (discord_id, branch, rank)
        )
        await self.conn.commit()

    async def get_staff_branches(self, discord_id):
        cur = await self.conn.execute("SELECT * FROM staff_branches WHERE discord_id=?", (discord_id,))
        return await cur.fetchall()

    async def add_punishment(self, discord_id, type_, reason, issued_by, expires_at=None):
        await self.conn.execute(
            """INSERT INTO punishments(discord_id, type, reason, issued_by, issued_at, expires_at, active)
               VALUES (?, ?, ?, ?, datetime('now'), ?, 1)""", (discord_id, type_, reason, issued_by, expires_at)
        )
        await self.conn.commit()

    async def count_active_warns(self, discord_id):
        cur = await self.conn.execute(
            "SELECT COUNT(*) as c FROM punishments WHERE discord_id=? AND type='warn' AND active=1", (discord_id,)
        )
        row = await cur.fetchone()
        return row["c"] if row else 0

    async def get_history(self, discord_id):
        cur = await self.conn.execute(
            "SELECT * FROM punishments WHERE discord_id=? ORDER BY issued_at DESC", (discord_id,)
        )
        return await cur.fetchall()

    async def deactivate_punishment(self, pid, removed_by):
        await self.conn.execute(
            "UPDATE punishments SET active=0, removed_by=?, removed_at=datetime('now') WHERE id=?",
            (removed_by, pid),
        )
        await self.conn.commit()

    async def has_active_punishment(self, discord_id, type_):
        cur = await self.conn.execute(
            "SELECT 1 FROM punishments WHERE discord_id=? AND type=? AND active=1 LIMIT 1", (discord_id, type_)
        )
        return await cur.fetchone() is not None

    async def get_punishment(self, pid):
        cur = await self.conn.execute("SELECT * FROM punishments WHERE id=?", (pid,))
        return await cur.fetchone()

    async def get_expired_punishments(self):
        cur = await self.conn.execute(
            "SELECT * FROM punishments WHERE active=1 AND expires_at IS NOT NULL AND expires_at <= datetime('now')"
        )
        return await cur.fetchall()

    async def get_punished_left(self):
        cur = await self.conn.execute(
            "SELECT p.* FROM punishments p JOIN users u ON u.discord_id=p.discord_id "
            "WHERE p.active=1 AND u.is_on_server=0"
        )
        return await cur.fetchall()

    async def start_voice_session(self, discord_id, channel_id, category):
        await self.conn.execute(
            "INSERT INTO voice_sessions(discord_id, channel_id, category, joined_at) VALUES (?, ?, ?, datetime('now'))",
            (discord_id, channel_id, category),
        )
        await self.conn.commit()

    async def end_voice_session(self, discord_id):
        await self.conn.execute(
            """UPDATE voice_sessions SET left_at=datetime('now'),
               duration_sec=CAST((julianday('now')-julianday(joined_at))*86400 AS INTEGER)
               WHERE discord_id=? AND left_at IS NULL""", (discord_id,)
        )
        await self.conn.commit()

    async def get_week_hours(self, discord_id):
        cur = await self.conn.execute(
            """SELECT COALESCE(SUM(duration_sec), 0) as total FROM voice_sessions
               WHERE discord_id=? AND joined_at >= datetime('now', '-7 days')""", (discord_id,)
        )
        row = await cur.fetchone()
        return (row["total"] or 0) / 3600.0 if row else 0.0

    async def get_open_voice_sessions(self):
        cur = await self.conn.execute("SELECT * FROM voice_sessions WHERE left_at IS NULL")
        return await cur.fetchall()

    async def set_quota(self, branch, rank, hours):
        await self.conn.execute(
            """INSERT INTO quotas(branch, rank, hours_per_week) VALUES (?, ?, ?)
               ON CONFLICT(branch, rank) DO UPDATE SET hours_per_week=excluded.hours_per_week""", (branch, rank, hours)
        )
        await self.conn.commit()

    async def get_quota(self, branch, rank):
        cur = await self.conn.execute(
            "SELECT hours_per_week FROM quotas WHERE branch=? AND rank=?", (branch, rank)
        )
        row = await cur.fetchone()
        return row["hours_per_week"] if row else 0.0

    async def add_antinuke_event(self, discord_id, action, count):
        await self.conn.execute(
            "INSERT INTO antinuke_events(discord_id, action, count) VALUES (?, ?, ?)", (discord_id, action, count)
        )
        await self.conn.commit()

    async def is_whitelisted(self, discord_id):
        cur = await self.conn.execute("SELECT 1 FROM antinuke_whitelist WHERE discord_id=? LIMIT 1", (discord_id,))
        return await cur.fetchone() is not None

    async def add_whitelist(self, discord_id, added_by):
        await self.conn.execute(
            "INSERT OR IGNORE INTO antinuke_whitelist(discord_id, added_by) VALUES (?, ?)", (discord_id, added_by)
        )
        await self.conn.commit()

    async def remove_whitelist(self, discord_id):
        await self.conn.execute("DELETE FROM antinuke_whitelist WHERE discord_id=?", (discord_id,))
        await self.conn.commit()

    async def is_protected(self, channel_id):
        cur = await self.conn.execute("SELECT 1 FROM protected_channels WHERE channel_id=? LIMIT 1", (channel_id,))
        return await cur.fetchone() is not None

    async def protect_channel(self, channel_id, by):
        await self.conn.execute(
            "INSERT OR IGNORE INTO protected_channels(channel_id, protected_by) VALUES (?, ?)", (channel_id, by)
        )
        await self.conn.commit()

    async def add_report(self, author_id, category, target_id, description, evidence) -> int:
        cur = await self.conn.execute(
            "INSERT INTO reports(author_id, category, target_id, description, evidence) VALUES (?, ?, ?, ?, ?)",
            (author_id, category, target_id, description, evidence),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def set_report_status(self, report_id, status, handled_by):
        await self.conn.execute(
            "UPDATE reports SET status=?, handled_by=?, handled_at=datetime('now') WHERE id=?",
            (status, handled_by, report_id),
        )
        await self.conn.commit()

    async def add_application(self, user_id, branch, hours, past, motivation, discord_exp, timezone) -> int:
        cur = await self.conn.execute(
            """INSERT INTO applications(user_id, branch, hours_per_week, past_experience, motivation,
               discord_experience, timezone) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, branch, hours, past, motivation, discord_exp, timezone),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_active_application(self, user_id):
        cur = await self.conn.execute(
            "SELECT * FROM applications WHERE user_id=? AND status='pending' LIMIT 1", (user_id,)
        )
        return await cur.fetchone()

    async def set_application_status(self, app_id, status, handled_by):
        await self.conn.execute(
            "UPDATE applications SET status=?, handled_by=?, handled_at=datetime('now') WHERE id=?",
            (status, handled_by, app_id),
        )
        await self.conn.commit()

    async def set_active_branch(self, discord_id, branch):
        await self.conn.execute(
            "INSERT INTO active_branch(discord_id, branch) VALUES (?, ?) ON CONFLICT(discord_id) DO UPDATE SET "
            "branch=excluded.branch, updated_at=datetime('now')", (discord_id, branch)
        )
        await self.conn.commit()

    async def get_active_branch(self, discord_id):
        cur = await self.conn.execute("SELECT branch FROM active_branch WHERE discord_id=?", (discord_id,))
        row = await cur.fetchone()
        return row["branch"] if row else None

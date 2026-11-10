import sqlite3

conn = sqlite3.connect("store.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.executescript("""
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    price TEXT,
    created_by TEXT
);

CREATE TABLE IF NOT EXISTS keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    status TEXT DEFAULT 'available',
    redeemed_by TEXT,
    redeemed_at TEXT,
    FOREIGN KEY (service_id) REFERENCES services(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS claims (
    user_id TEXT NOT NULL,
    service_id INTEGER NOT NULL,
    last_claim_at TEXT NOT NULL,
    PRIMARY KEY (user_id, service_id)
);
""")
conn.commit()


def get_setting(key: str, default=None):
    row = cur.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    cur.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_last_claim(user_id: str, service_id: int):
    row = cur.execute(
        "SELECT last_claim_at FROM claims WHERE user_id = ? AND service_id = ?",
        (user_id, service_id),
    ).fetchone()
    return row["last_claim_at"] if row else None


def set_last_claim(user_id: str, service_id: int, timestamp: str):
    cur.execute(
        "INSERT INTO claims (user_id, service_id, last_claim_at) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, service_id) DO UPDATE SET last_claim_at = excluded.last_claim_at",
        (user_id, service_id, timestamp),
    )
    conn.commit()


def list_services():
    return cur.execute("SELECT * FROM services ORDER BY name").fetchall()


def get_service(name: str):
    return cur.execute("SELECT * FROM services WHERE name = ?", (name,)).fetchone()


def add_service(name: str, price: str, created_by: str):
    cur.execute(
        "INSERT INTO services (name, price, created_by) VALUES (?, ?, ?)",
        (name, price, created_by),
    )
    conn.commit()


def add_keys(service_id: int, codes: list[str]):
    cur.executemany(
        "INSERT INTO keys (service_id, code) VALUES (?, ?)",
        [(service_id, code) for code in codes],
    )
    conn.commit()


def get_available_key(service_id: int):
    return cur.execute(
        "SELECT * FROM keys WHERE service_id = ? AND status = 'available' ORDER BY id ASC LIMIT 1",
        (service_id,),
    ).fetchone()


def mark_redeemed(key_id: int, user_id: str, timestamp: str):
    cur.execute(
        "UPDATE keys SET status = 'redeemed', redeemed_by = ?, redeemed_at = ? WHERE id = ?",
        (user_id, timestamp, key_id),
    )
    conn.commit()


def rollback_redeem(key_id: int):
    cur.execute(
        "UPDATE keys SET status = 'available', redeemed_by = NULL, redeemed_at = NULL WHERE id = ?",
        (key_id,),
    )
    conn.commit()


def stock_summary():
    rows = cur.execute("""
        SELECT s.name, COUNT(k.id) as available
        FROM services s
        LEFT JOIN keys k ON k.service_id = s.id AND k.status = 'available'
        GROUP BY s.id
        ORDER BY s.name
    """).fetchall()
    if not rows:
        return "No services added yet."
    return "\n".join(f"**{r['name']}**: {r['available']} available" for r in rows)

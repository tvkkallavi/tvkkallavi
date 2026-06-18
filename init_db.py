"""
Initialize the SQLite database from schema.sql and seed a default admin.
Run once before first launch:   python init_db.py
"""
import os
import sqlite3
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "tvkkallavi.db")
SCHEMA = os.path.join(BASE_DIR, "schema.sql")

DEFAULT_ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin123")


def main():
    fresh = not os.path.exists(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON;")
    with open(SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())

    # Seed the admin only if no admin exists yet.
    row = con.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()
    if row[0] == 0:
        con.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?,?, 'admin')",
            (DEFAULT_ADMIN_USER, generate_password_hash(DEFAULT_ADMIN_PASS)),
        )
        print(f"  Admin created -> username: {DEFAULT_ADMIN_USER}  password: {DEFAULT_ADMIN_PASS}")
        print("  >> CHANGE THIS PASSWORD after first login (or set ADMIN_PASSWORD env var).")
    else:
        print("  Admin already exists, left unchanged.")

    # --- Idempotent migrations (safe to run on existing databases) ---
    # Ensure the Corruption / Bribery category exists, keep "Others" last.
    con.execute(
        "INSERT OR IGNORE INTO categories (slug, name_en, name_ta, sort_order) "
        "VALUES ('corruption', 'Corruption / Bribery', 'ஊழல் / லஞ்சம்', 8)"
    )
    con.execute("UPDATE categories SET sort_order = 9 WHERE slug = 'others'")

    # Set the official contact details.
    for key, val in [
        ("contact_number", "+91 8940524235"),
        ("contact_email", "tvkkallavi@gmail.com"),
        ("contact_address", "Kallavi - 635304"),
    ]:
        con.execute(
            "UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
            (val, key),
        )
    print("  Categories and contact details synced.")

    # Upgrade the activities table if it predates the gallery module
    # (adds location, volunteers_participated, and the 'events' type).
    info = con.execute("PRAGMA table_info(activities)").fetchall()
    cols = [r[1] for r in info]
    tbl_sql = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='activities'"
    ).fetchone()[0]
    needs_upgrade = (
        "location" not in cols
        or "volunteers_participated" not in cols
        or "'events'" not in tbl_sql
    )
    if needs_upgrade:
        loc_src = "location" if "location" in cols else "NULL"
        vp_src = "volunteers_participated" if "volunteers_participated" in cols else "NULL"
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("PRAGMA legacy_alter_table=ON")  # don't rewrite child FK references
        con.executescript(f"""
            ALTER TABLE activities RENAME TO _activities_old;
            CREATE TABLE activities (
                id              INTEGER PRIMARY KEY,
                title           TEXT    NOT NULL,
                activity_type   TEXT    NOT NULL
                                CHECK (activity_type IN
                                    ('food_donation','blood_donation','educational_support',
                                     'medical_camp','public_welfare','events')),
                activity_date   TEXT,
                location        TEXT,
                volunteers_participated INTEGER,
                description     TEXT,
                submitted_by    INTEGER NOT NULL,
                is_archived     INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (submitted_by) REFERENCES users(id)
            );
            INSERT INTO activities
                (id,title,activity_type,activity_date,location,volunteers_participated,
                 description,submitted_by,is_archived,created_at)
            SELECT id,title,activity_type,activity_date,{loc_src},{vp_src},
                 description,submitted_by,is_archived,created_at
            FROM _activities_old;
            DROP TABLE _activities_old;
        """)
        con.execute("PRAGMA legacy_alter_table=OFF")
        con.execute("PRAGMA foreign_keys=ON")
        print("  Activities table upgraded (location, volunteers, events type).")

    con.commit()
    con.close()
    print(("Created" if fresh else "Updated") + f" database at {DB_PATH}")


if __name__ == "__main__":
    main()

"""
database.py
------------
Everything related to storage lives here: creating tables, seeding
sample data, and giving the rest of the app plain functions to read
and write PHC status without writing raw SQL everywhere else.

LEARNING NOTE: SQLite stores the whole database in a single file
(phc_care.db) sitting right next to this script. That's ideal for a
hackathon demo -- no server process to start, stop, or worry about
crashing mid-pitch, and nothing to configure. The SQL below is close
enough to standard SQL that moving to PostgreSQL/MySQL later (if you
ever needed to) would mean changing very little.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "phc_care.db"

# Real Meghalaya PHC locations spread across several districts, so the
# fuzzy-matching demo has genuine variety in spelling and length.
SEED_PHCS = [
    ("Smit", "East Khasi Hills", "Dr. B. Marbaniang", "Active"),
    ("Mawryngkneng", "East Khasi Hills", "Dr. K. Lyngdoh", "Inactive"),
    ("Sohra", "East Khasi Hills", "Dr. P. Suchiang", "Active"),
    ("Mairang", "West Khasi Hills", "Dr. W. Nongrum", "Inactive"),
    ("Nongstoin", "West Khasi Hills", "Dr. D. Kharshiing", "Active"),
    ("Jowai", "West Jaintia Hills", "Dr. S. Pariat", "Active"),
    ("Nongpoh", "Ri-Bhoi", "Dr. R. Sangma", "Inactive"),
    ("Williamnagar", "East Garo Hills", "Dr. T. Momin", "Active"),
    ("Tura", "West Garo Hills", "Dr. A. Marak", "Inactive"),
    ("Baghmara", "South Garo Hills", "Dr. J. Ch. Sangma", "Active"),
]


def get_connection() -> sqlite3.Connection:
    """
    Opens a connection to the database file.
    Setting row_factory to sqlite3.Row lets us read columns by name
    (row["village_name"]) instead of by position (row[1]) -- much
    easier to read and far less error-prone as the schema grows.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(reset: bool = False) -> None:
    """
    Creates the two core tables if they don't exist yet, and seeds
    them with sample data the first time the app runs.

    PHCs         -- one row per Primary Health Centre.
    Doctors_Log  -- one row per STATUS CHANGE, not one row per PHC.
                    Keeping history (instead of overwriting a single
                    "current status" column) means you can honestly
                    tell judges "every check-in and check-out is
                    logged," which is a nice detail for Slide 4.
    """
    conn = get_connection()
    cur = conn.cursor()

    if reset:
        cur.execute("DROP TABLE IF EXISTS Doctors_Log")
        cur.execute("DROP TABLE IF EXISTS PHCs")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS PHCs (
            phc_id INTEGER PRIMARY KEY AUTOINCREMENT,
            village_name TEXT NOT NULL,
            district TEXT NOT NULL
        )
    """)

    # SQLite has no native ENUM type. A CHECK constraint does the same
    # job: this column can only ever hold 'Active' or 'Inactive'.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Doctors_Log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            phc_id INTEGER NOT NULL,
            doctor_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Active', 'Inactive')),
            last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (phc_id) REFERENCES PHCs(phc_id)
        )
    """)

    # Only seed on an empty table, so restarting the app never
    # duplicates rows.
    cur.execute("SELECT COUNT(*) FROM PHCs")
    if cur.fetchone()[0] == 0:
        for village, district, doctor, status in SEED_PHCS:
            cur.execute(
                "INSERT INTO PHCs (village_name, district) VALUES (?, ?)",
                (village, district),
            )
            phc_id = cur.lastrowid
            cur.execute(
                "INSERT INTO Doctors_Log (phc_id, doctor_name, status) VALUES (?, ?, ?)",
                (phc_id, doctor, status),
            )
        conn.commit()

    conn.close()


def get_all_phcs_with_status() -> list[dict]:
    """
    Returns every PHC with its MOST RECENT status. This powers the
    admin/monitor panel in the demo UI.

    LEARNING NOTE: because Doctors_Log keeps one row per change rather
    than updating in place, we need "the latest row per phc_id." The
    subquery finds MAX(log_id) per phc_id -- the standard SQL pattern
    for "give me the latest record in each group."
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.phc_id, p.village_name, p.district,
               d.doctor_name, d.status, d.last_updated
        FROM PHCs p
        JOIN Doctors_Log d ON d.phc_id = p.phc_id
        WHERE d.log_id = (
            SELECT MAX(log_id) FROM Doctors_Log WHERE phc_id = p.phc_id
        )
        ORDER BY p.village_name
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def toggle_status(phc_id: int) -> dict:
    """
    Flips one PHC's current status by inserting a NEW log row (rather
    than editing the old one), stamped with the current time.

    This function IS your mock IoT trigger: in the real system, a
    doctor's phone auto-connecting to the clinic's Wi-Fi would call
    this same function. For the hackathon, an admin button calls it
    instead -- the rest of the system can't tell the difference.
    """
    conn = get_connection()
    row = conn.execute("""
        SELECT doctor_name, status FROM Doctors_Log
        WHERE phc_id = ? ORDER BY log_id DESC LIMIT 1
    """, (phc_id,)).fetchone()

    if row is None:
        conn.close()
        raise ValueError(f"No PHC found with id {phc_id}")

    new_status = "Inactive" if row["status"] == "Active" else "Active"
    conn.execute(
        "INSERT INTO Doctors_Log (phc_id, doctor_name, status) VALUES (?, ?, ?)",
        (phc_id, row["doctor_name"], new_status),
    )
    conn.commit()
    conn.close()
    return {"phc_id": phc_id, "status": new_status}


def find_status_by_village(query: str, score_cutoff: int = 60) -> dict | None:
    """
    Fuzzy-matches typed text against known PHC village names, then
    returns that PHC's latest status.

    LEARNING NOTE: rapidfuzz.process.extractOne compares `query`
    against every name in a list and returns the closest match plus a
    similarity score from 0-100. score_cutoff=60 means "if nothing is
    at least 60% similar, treat it as no match" -- without this, the
    bot would confidently match completely unrelated input to
    whichever village happens to be least-wrong.
    """
    from rapidfuzz import process, fuzz

    all_phcs = get_all_phcs_with_status()
    if not all_phcs:
        return None

    village_names = [p["village_name"] for p in all_phcs]
    match = process.extractOne(
        query, village_names, scorer=fuzz.WRatio, score_cutoff=score_cutoff
    )
    if match is None:
        return None

    _matched_name, score, index = match
    result = all_phcs[index]
    result["confidence"] = round(score, 1)
    return result

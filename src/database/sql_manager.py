# """SQLite storage for policies, clauses, findings and remediation results.

# Every audit writes one row per stage, so the pipeline leaves a trace behind.
# The schema is created on first use by init_db().
# """

# import os
# import sqlite3
# from datetime import datetime, timezone

# DB_PATH = "data/database/reguard_audit.db"


# def get_connection():
#     #establishing a connection to the sql lite databse, creating parent directories if needed
#     os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
#     conn = sqlite3.connect(DB_PATH, timeout=30)
#     conn.row_factory = sqlite3.Row
#     # WAL keeps reads from being blocked by writes, and busy_timeout waits instead
#     # of raising "database is locked" when two requests arrive together.
#     conn.execute("PRAGMA journal_mode=WAL")
#     conn.execute("PRAGMA busy_timeout=30000")
#     # Foreign keys are declared below but SQLite leaves them unenforced unless
#     # this is set on every connection.
#     conn.execute("PRAGMA foreign_keys=ON")
#     return conn


# # Columns added after the first release. CREATE TABLE IF NOT EXISTS leaves an
# # existing table untouched, so these are applied separately for databases that
# # were created before the columns existed.
# ADDED_FINDING_COLUMNS = {
#     "evidence_citation": "TEXT",
#     "evidence_passage_id": "TEXT",
#     "evidence_section": "TEXT",
#     "evidence_status": "TEXT",
#     "retrieved_passage": "TEXT",
# }


# def _ensure_columns(cursor, table, columns):
#     """Add any missing columns to an existing table."""
#     existing = {row["name"] for row in cursor.execute(f"PRAGMA table_info({table})")}
#     for name, sql_type in columns.items():
#         if name not in existing:
#             cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


# def init_db():
#     #Initializes the database schema with tables for policies, clauses, findings, and remediation
#     conn = get_connection()
#     try:
#         cursor = conn.cursor()

#         #1 . Policies Table
#         cursor.execute("""
#             CREATE TABLE IF NOT EXISTS policies (
#                 policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 filename TEXT NOT NULL,
#                 full_text TEXT NOT NULL,
#                 created_at TEXT NOT NULL
#             )
#         """)

#         # 2. Policy Clauses Table
#         cursor.execute("""
#             CREATE TABLE IF NOT EXISTS clauses (
#                 clause_id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 policy_id INTEGER,
#                 clause_text TEXT NOT NULL,
#                 actor TEXT,
#                 action TEXT,
#                 limit_val TEXT,
#                 condition TEXT,
#                 risk_score REAL,
#                 FOREIGN KEY (policy_id) REFERENCES policies (policy_id)
#             )
#         """)

#         # 3. Audit Findings (Challenger & Auditor Results) Table.
#         # The evidence columns record exactly which RBI passage justified the
#         # finding, so a stored audit can be reproduced later.
#         cursor.execute("""
#             CREATE TABLE IF NOT EXISTS audit_findings (
#                 finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 policy_id INTEGER,
#                 clause_id INTEGER,
#                 attack_scenario TEXT,
#                 matched_rbi_passage_id TEXT,
#                 evidence_citation TEXT,
#                 evidence_passage_id TEXT,
#                 evidence_section TEXT,
#                 evidence_status TEXT,
#                 retrieved_passage TEXT,
#                 violation_detected BOOLEAN,
#                 explanation TEXT,
#                 severity TEXT,
#                 created_at TEXT NOT NULL,
#                 FOREIGN KEY (policy_id) REFERENCES policies (policy_id),
#                 FOREIGN KEY (clause_id) REFERENCES clauses (clause_id)
#             )
#         """)
#         _ensure_columns(cursor, "audit_findings", ADDED_FINDING_COLUMNS)

#         # 4. Remediation & Re-Test Results Table
#         cursor.execute("""
#             CREATE TABLE IF NOT EXISTS remediation_results (
#                 remediation_id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 finding_id INTEGER,
#                 patched_clause_text TEXT,
#                 asr_before REAL,
#                 asr_after REAL,
#                 status TEXT,
#                 FOREIGN KEY (finding_id) REFERENCES audit_findings (finding_id)
#             )
#         """)

#         # Indexes on the foreign keys: every audit trail query joins on these.
#         for statement in (
#             "CREATE INDEX IF NOT EXISTS idx_clauses_policy ON clauses (policy_id)",
#             "CREATE INDEX IF NOT EXISTS idx_findings_policy ON audit_findings (policy_id)",
#             "CREATE INDEX IF NOT EXISTS idx_findings_clause ON audit_findings (clause_id)",
#             "CREATE INDEX IF NOT EXISTS idx_remediation_finding ON remediation_results (finding_id)",
#         ):
#             cursor.execute(statement)

#         conn.commit()
#     finally:
#         conn.close()

#     print(f"Database initialized successfully at '{DB_PATH}'")


# def _insert(sql: str, params: tuple) -> int:
#     """Runs one INSERT and returns the new row id, always closing the connection."""
#     conn = get_connection()
#     try:
#         cursor = conn.execute(sql, params)
#         conn.commit()
#         return cursor.lastrowid
#     finally:
#         conn.close()


# def insert_policy(filename: str, full_text: str) -> int:
#     """Inserts a raw policy document record and returns its policy_id."""
#     return _insert(
#         "INSERT INTO policies (filename, full_text, created_at) VALUES (?, ?, ?)",
#         (filename, full_text, datetime.now(timezone.utc).isoformat())
#     )


# def insert_clause(policy_id: int, clause_text: str, actor: str, action: str, limit_val: str, condition: str, risk_score: float) -> int:
#     """Inserts an extracted structural clause breakdown and risk score, returning clause_id."""
#     return _insert(
#         """
#         INSERT INTO clauses (policy_id, clause_text, actor, action, limit_val, condition, risk_score)
#         VALUES (?, ?, ?, ?, ?, ?, ?)
#         """,
#         (policy_id, clause_text, actor, action, limit_val, condition, risk_score)
#     )


# def insert_audit_finding(policy_id: int, clause_id: int, attack_scenario: str, matched_rbi_passage_id: str, violation_detected: bool, explanation: str, severity: str, evidence: dict = None) -> int:
#     """Inserts an adversarial red-team audit finding record, returning finding_id.

#     The evidence block records the citation the finding rests on, so a stored
#     audit can be traced back to the RBI passage instead of just a filename.
#     """
#     evidence = evidence or {}
#     return _insert(
#         """
#         INSERT INTO audit_findings (
#             policy_id, clause_id, attack_scenario, matched_rbi_passage_id,
#             evidence_citation, evidence_passage_id, evidence_section, evidence_status,
#             retrieved_passage, violation_detected, explanation, severity, created_at
#         )
#         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
#         """,
#         (
#             policy_id,
#             clause_id,
#             attack_scenario,
#             matched_rbi_passage_id,
#             evidence.get("citation"),
#             evidence.get("passage_id"),
#             evidence.get("section"),
#             evidence.get("status"),
#             (evidence.get("passage_text") or "")[:5000],
#             violation_detected,
#             explanation,
#             severity,
#             datetime.now(timezone.utc).isoformat(),
#         )
#     )


# def insert_remediation_result(finding_id: int, patched_clause_text: str, asr_before: float, asr_after: float, status: str) -> int:
#     """Inserts remediation and ASR drop test results, returning remediation_id."""
#     return _insert(
#         """
#         INSERT INTO remediation_results (finding_id, patched_clause_text, asr_before, asr_after, status)
#         VALUES (?, ?, ?, ?, ?)
#         """,
#         (finding_id, patched_clause_text, asr_before, asr_after, status)
#     )


# if __name__ == "__main__":
#     init_db()

#     # Test insertion
#     print("\nTesting insertion helpers...")
#     p_id = insert_policy("test_policy.docx", "Sample policy body content...")
#     c_id = insert_clause(p_id, "Levy 2% fee", "Lender", "Levy fee", "2%", "On delay", 0.85)
#     f_id = insert_audit_finding(p_id, c_id, "Simulated default scenario", "RBI_Sec_4", True, "Excessive fee violation", "High")
#     r_id = insert_remediation_result(f_id, "Levy 0.5% fee capped", 0.35, 0.08, "Resolved")

#     print(f"Successfully inserted test records! IDs -> Policy: {p_id}, Clause: {c_id}, Finding: {f_id}, Remediation: {r_id}")




"""SQLite database persistence layer for policies, clauses, findings, and remediation results."""

import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = "data/database/reguard_audit.db"


def get_connection():
    """Establish a configured SQLite connection with WAL mode and foreign keys enabled."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


ADDED_FINDING_COLUMNS = {
    "evidence_citation": "TEXT",
    "evidence_passage_id": "TEXT",
    "evidence_section": "TEXT",
    "evidence_status": "TEXT",
    "retrieved_passage": "TEXT",
}


def _ensure_columns(cursor, table, columns):
    """Add missing columns to legacy tables dynamically."""
    existing = {row["name"] for row in cursor.execute(f"PRAGMA table_info({table})")}
    for name, sql_type in columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


def init_db():
    """Initialize database tables, schemas, and performance indices."""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # 1. Policies Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policies (
                policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                full_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # 2. Clauses Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clauses (
                clause_id INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_id INTEGER,
                clause_text TEXT NOT NULL,
                actor TEXT,
                action TEXT,
                limit_val TEXT,
                condition TEXT,
                risk_score REAL,
                FOREIGN KEY (policy_id) REFERENCES policies (policy_id)
            )
        """)

        # 3. Audit Findings Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_findings (
                finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_id INTEGER,
                clause_id INTEGER,
                attack_scenario TEXT,
                matched_rbi_passage_id TEXT,
                evidence_citation TEXT,
                evidence_passage_id TEXT,
                evidence_section TEXT,
                evidence_status TEXT,
                retrieved_passage TEXT,
                violation_detected BOOLEAN,
                explanation TEXT,
                severity TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (policy_id) REFERENCES policies (policy_id),
                FOREIGN KEY (clause_id) REFERENCES clauses (clause_id)
            )
        """)
        _ensure_columns(cursor, "audit_findings", ADDED_FINDING_COLUMNS)

        # 4. Remediation Results Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS remediation_results (
                remediation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                finding_id INTEGER,
                patched_clause_text TEXT,
                asr_before REAL,
                asr_after REAL,
                status TEXT,
                FOREIGN KEY (finding_id) REFERENCES audit_findings (finding_id)
            )
        """)

        # Database Indexes for rapid traversal
        for stmt in (
            "CREATE INDEX IF NOT EXISTS idx_clauses_policy ON clauses (policy_id)",
            "CREATE INDEX IF NOT EXISTS idx_findings_policy ON audit_findings (policy_id)",
            "CREATE INDEX IF NOT EXISTS idx_findings_clause ON audit_findings (clause_id)",
            "CREATE INDEX IF NOT EXISTS idx_remediation_finding ON remediation_results (finding_id)",
        ):
            cursor.execute(stmt)

        conn.commit()
    finally:
        conn.close()

    print(f"Database initialized successfully at '{DB_PATH}'")


def _insert(sql: str, params: tuple) -> int:
    """Execute a single insert query and return the new row ID safely."""
    conn = get_connection()
    try:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def insert_policy(filename: str, full_text: str) -> int:
    return _insert(
        "INSERT INTO policies (filename, full_text, created_at) VALUES (?, ?, ?)",
        (filename, full_text, datetime.now(timezone.utc).isoformat())
    )


def insert_clause(policy_id: int, clause_text: str, actor: str, action: str, limit_val: str, condition: str, risk_score: float) -> int:
    return _insert(
        """
        INSERT INTO clauses (policy_id, clause_text, actor, action, limit_val, condition, risk_score)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (policy_id, clause_text, actor, action, limit_val, condition, risk_score)
    )


def insert_audit_finding(policy_id: int, clause_id: int, attack_scenario: str, matched_rbi_passage_id: str, violation_detected: bool, explanation: str, severity: str, evidence: dict = None) -> int:
    evidence = evidence or {}
    return _insert(
        """
        INSERT INTO audit_findings (
            policy_id, clause_id, attack_scenario, matched_rbi_passage_id,
            evidence_citation, evidence_passage_id, evidence_section, evidence_status,
            retrieved_passage, violation_detected, explanation, severity, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            policy_id,
            clause_id,
            attack_scenario,
            matched_rbi_passage_id,
            evidence.get("citation"),
            evidence.get("passage_id"),
            evidence.get("section"),
            evidence.get("status"),
            (evidence.get("passage_text") or "")[:5000],
            violation_detected,
            explanation,
            severity,
            datetime.now(timezone.utc).isoformat(),
        )
    )


def insert_remediation_result(finding_id: int, patched_clause_text: str, asr_before: float, asr_after: float, status: str) -> int:
    return _insert(
        """
        INSERT INTO remediation_results (finding_id, patched_clause_text, asr_before, asr_after, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (finding_id, patched_clause_text, asr_before, asr_after, status)
    )


if __name__ == "__main__":
    init_db()
    print("\nTesting insertion helpers...")
    p_id = insert_policy("test_policy.docx", "Sample policy body content...")
    c_id = insert_clause(p_id, "Levy 2% fee", "Lender", "Levy fee", "2%", "On delay", 0.85)
    f_id = insert_audit_finding(p_id, c_id, "Simulated default scenario", "RBI_Sec_4", True, "Excessive fee violation", "High")
    r_id = insert_remediation_result(f_id, "Levy 0.5% fee capped", 0.35, 0.08, "Resolved")
    print(f"Successfully inserted test records! IDs -> Policy: {p_id}, Clause: {c_id}, Finding: {f_id}, Remediation: {r_id}")
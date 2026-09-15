import sqlite3
import os
import json
from datetime import datetime, timezone

DB_PATH = "data/database/reguard_audit.db"

def get_connection():
    #establishing a connection to the sql lite databse, creating parent directories if needed
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    #Initializes the database schema with tables for policies, clauses, findings, and remediation
    conn = get_connection()
    cursor = conn.cursor()

    #1 . Policies Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS policies (
            policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            full_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # 2. Policy Clauses Table
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


    # 3. Audit Findings (Challenger & Auditor Results) Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_findings (
            finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_id INTEGER,
            clause_id INTEGER,
            attack_scenario TEXT,
            matched_rbi_passage_id TEXT,
            violation_detected BOOLEAN,
            explanation TEXT,
            severity TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (policy_id) REFERENCES policies (policy_id),
            FOREIGN KEY (clause_id) REFERENCES clauses (clause_id)
        )
    """)


    # 4. Remediation & Re-Test Results Table
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


    conn.commit()
    conn.close()
    print(f"Database initialized successfully at '{DB_PATH}'")

def insert_policy(filename: str, full_text: str) -> int:
    """Inserts a raw policy document record and returns its policy_id."""
    conn = get_connection()
    cursor = conn.cursor()
    created_at = datetime.now(timezone.utc).isoformat()
    
    cursor.execute(
        "INSERT INTO policies (filename, full_text, created_at) VALUES (?, ?, ?)",
        (filename, full_text, created_at)
    )
    conn.commit()
    policy_id = cursor.lastrowid
    conn.close()
    return policy_id


def insert_clause(policy_id: int, clause_text: str, actor: str, action: str, limit_val: str, condition: str, risk_score: float) -> int:
    """Inserts an extracted structural clause breakdown and risk score, returning clause_id."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        INSERT INTO clauses (policy_id, clause_text, actor, action, limit_val, condition, risk_score)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (policy_id, clause_text, actor, action, limit_val, condition, risk_score)
    )
    conn.commit()
    clause_id = cursor.lastrowid
    conn.close()
    return clause_id

def insert_audit_finding(policy_id: int, clause_id: int, attack_scenario: str, matched_rbi_passage_id: str, violation_detected: bool, explanation: str, severity: str) -> int:
    """Inserts an adversarial red-team audit finding record, returning finding_id."""
    conn = get_connection()
    cursor = conn.cursor()
    created_at = datetime.now(timezone.utc).isoformat()
    
    cursor.execute(
        """
        INSERT INTO audit_findings (policy_id, clause_id, attack_scenario, matched_rbi_passage_id, violation_detected, explanation, severity, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (policy_id, clause_id, attack_scenario, matched_rbi_passage_id, violation_detected, explanation, severity, created_at)
    )
    conn.commit()
    finding_id = cursor.lastrowid
    conn.close()
    return finding_id

def insert_remediation_result(finding_id: int, patched_clause_text: str, asr_before: float, asr_after: float, status: str) -> int:
    """Inserts remediation and ASR drop test results, returning remediation_id."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        INSERT INTO remediation_results (finding_id, patched_clause_text, asr_before, asr_after, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (finding_id, patched_clause_text, asr_before, asr_after, status)
    )
    conn.commit()
    remediation_id = cursor.lastrowid
    conn.close()
    return remediation_id

if __name__ == "__main__":
    init_db()

    # Test insertion
    print("\nTesting insertion helpers...")
    p_id = insert_policy("test_policy.docx", "Sample policy body content...")
    c_id = insert_clause(p_id, "Levy 2% fee", "Lender", "Levy fee", "2%", "On delay", 0.85)
    f_id = insert_audit_finding(p_id, c_id, "Simulated default scenario", "RBI_Sec_4", True, "Excessive fee violation", "High")
    r_id = insert_remediation_result(f_id, "Levy 0.5% fee capped", 0.35, 0.08, "Resolved")
    
    print(f"Successfully inserted test records! IDs -> Policy: {p_id}, Clause: {c_id}, Finding: {f_id}, Remediation: {r_id}")
"""
ExecSearch AI - Application Tracker Database
Uses SQLite to track all scouted jobs and application statuses.
Ensures deduplication (never shows or applies to the same job twice).
"""

import os
import csv
import sqlite3
from datetime import datetime
from typing import Optional


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "job_agent.db")
CSV_EXPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "applications_tracker.csv")


def get_connection() -> sqlite3.Connection:
    """Returns a connection to the SQLite database, creating tables if needed."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            url TEXT,
            source TEXT,
            location TEXT,
            salary_info TEXT,
            description TEXT,
            status TEXT DEFAULT 'Scouted',
            match_score INTEGER DEFAULT 0,
            ai_reasoning TEXT,
            tailored_resume TEXT,
            cover_letter TEXT,
            scouted_at TEXT,
            applied_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    return conn


def generate_job_id(title: str, company: str) -> str:
    """Generates a deterministic ID from title+company to prevent duplicates."""
    raw = f"{title.strip().lower()}|{company.strip().lower()}"
    import hashlib
    return hashlib.md5(raw.encode()).hexdigest()


def is_job_seen(title: str, company: str) -> bool:
    """Check if we have already scouted or applied to this job."""
    job_id = generate_job_id(title, company)
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def save_scouted_job(job: dict) -> bool:
    """
    Save a newly scouted job to the database.
    Returns True if inserted (new job), False if already exists (duplicate).
    """
    job_id = generate_job_id(job.get("title", ""), job.get("company", ""))
    conn = get_connection()
    try:
        existing = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if existing:
            return False

        conn.execute("""
            INSERT INTO jobs (id, title, company, url, source, location, salary_info, description, status, scouted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Scouted', ?)
        """, (
            job_id,
            job.get("title", ""),
            job.get("company", ""),
            job.get("url", ""),
            job.get("source", ""),
            job.get("location", ""),
            job.get("salary_info", ""),
            job.get("description", ""),
            datetime.now().isoformat()
        ))
        conn.commit()
        return True
    finally:
        conn.close()


def update_job_status(
    title: str,
    company: str,
    status: str,
    match_score: int = 0,
    ai_reasoning: str = "",
    tailored_resume: str = "",
    cover_letter: str = ""
) -> None:
    """Update the status and AI evaluation results for a job."""
    job_id = generate_job_id(title, company)
    conn = get_connection()
    try:
        applied_at = datetime.now().isoformat() if status == "Applied" else None
        conn.execute("""
            UPDATE jobs
            SET status = ?, match_score = ?, ai_reasoning = ?,
                tailored_resume = ?, cover_letter = ?,
                applied_at = COALESCE(?, applied_at),
                updated_at = ?
            WHERE id = ?
        """, (status, match_score, ai_reasoning, tailored_resume, cover_letter,
              applied_at, datetime.now().isoformat(), job_id))
        conn.commit()
    finally:
        conn.close()


def export_to_csv() -> str:
    """Export all tracked jobs to a CSV file. Returns the file path."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT scouted_at, title, company, source, location, salary_info,
                   status, match_score, ai_reasoning, url, applied_at
            FROM jobs
            ORDER BY scouted_at DESC
        """).fetchall()

        with open(CSV_EXPORT_PATH, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Date Scouted", "Job Title", "Company", "Source Portal",
                "Location", "Salary Info", "Status", "AI Match Score",
                "AI Reasoning", "URL", "Date Applied"
            ])
            for row in rows:
                writer.writerow(list(row))

        return CSV_EXPORT_PATH
    finally:
        conn.close()


def get_stats() -> dict:
    """Get summary statistics of the job search campaign."""
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        applied = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'Applied'").fetchone()[0]
        skipped = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'Skipped'").fetchone()[0]
        rejected = conn.execute("SELECT COUNT(*) FROM jobs WHERE status LIKE 'Rejected%'").fetchone()[0]
        matched = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'Matched'").fetchone()[0]

        return {
            "total_scouted": total,
            "applied": applied,
            "skipped": skipped,
            "rejected_by_ai": rejected,
            "matched_pending": matched
        }
    finally:
        conn.close()

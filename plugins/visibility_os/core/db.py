from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from hermes_constants import get_hermes_home

DB_FILENAME = "visibility_os.db"
SCHEMA_VERSION = 1


def get_db_path() -> Path:
    return Path(get_hermes_home()) / DB_FILENAME


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS opportunities (
            id TEXT PRIMARY KEY,
            source_system TEXT NOT NULL,
            source_url TEXT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT,
            impact_score INTEGER NOT NULL,
            visibility_score INTEGER NOT NULL,
            effort_score INTEGER NOT NULL,
            safety_score INTEGER NOT NULL,
            risk_penalty INTEGER NOT NULL DEFAULT 0,
            priority_score INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            suggested_artifacts TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_visibility_opportunity_source
            ON opportunities(source_system, source_url, category);

        CREATE TABLE IF NOT EXISTS action_queue (
            id TEXT PRIMARY KEY,
            opportunity_id TEXT REFERENCES opportunities(id),
            proposed_by_agent TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target_system TEXT NOT NULL,
            target_location TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            proposed_payload TEXT NOT NULL,
            final_payload TEXT,
            evidence_links TEXT NOT NULL DEFAULT '[]',
            risk_level TEXT NOT NULL,
            impact_score INTEGER,
            visibility_score INTEGER,
            effort_score INTEGER,
            approval_required INTEGER NOT NULL DEFAULT 1,
            approval_reason TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            approved_at TEXT,
            executed_at TEXT,
            approved_by TEXT,
            execution_result TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_visibility_action_status ON action_queue(status);

        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY,
            action_id TEXT REFERENCES action_queue(id),
            event_type TEXT NOT NULL,
            actor TEXT NOT NULL,
            before_state TEXT,
            after_state TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_visibility_audit_action ON audit_log(action_id);

        CREATE TABLE IF NOT EXISTS daily_summaries (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            summary_payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS weekly_summaries (
            id TEXT PRIMARY KEY,
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            summary_payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS scan_runs (
            id TEXT PRIMARY KEY,
            scanner_name TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            finished_at TEXT,
            result_payload TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS connector_state (
            connector_name TEXT PRIMARY KEY,
            state_payload TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (SCHEMA_VERSION,))

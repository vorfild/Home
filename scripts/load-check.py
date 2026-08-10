#!/usr/bin/env python3
"""Reproducible declared-scale persistence and indexed-query check."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import time
from pathlib import Path


def elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Domovoy's declared household scale")
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--storage-items", type=int, default=50_000)
    parser.add_argument("--task-instances", type=int, default=100_000)
    parser.add_argument("--query-limit", type=float, default=3.0)
    args = parser.parse_args()
    if min(args.users, args.storage_items, args.task_instances) < 1:
        parser.error("all scale values must be positive")

    open_tasks = min(10_000, max(1_000, args.task_instances // 10))
    timings: dict[str, float] = {}
    with tempfile.TemporaryDirectory(prefix="domovoy-load-") as temporary:
        database = Path(temporary) / "load.sqlite3"
        connection = sqlite3.connect(database)
        connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE users (
                id INTEGER PRIMARY KEY, household_id INTEGER NOT NULL, name TEXT NOT NULL,
                role TEXT NOT NULL, is_active INTEGER NOT NULL
            );
            CREATE INDEX ix_users_household ON users(household_id, is_active);
            CREATE TABLE storage_items (
                id INTEGER PRIMARY KEY, household_id INTEGER NOT NULL, node_id INTEGER NOT NULL,
                name TEXT NOT NULL, normalized_name TEXT NOT NULL, category TEXT,
                archived_at TEXT
            );
            CREATE INDEX ix_storage_household_node ON storage_items(household_id, node_id);
            CREATE INDEX ix_storage_normalized ON storage_items(normalized_name);
            CREATE TABLE task_instances (
                id INTEGER PRIMARY KEY, household_id INTEGER NOT NULL, task_id INTEGER NOT NULL,
                sequence INTEGER NOT NULL, due_at TEXT, status TEXT NOT NULL,
                assignee_id INTEGER
            );
            CREATE UNIQUE INDEX uq_task_sequence ON task_instances(task_id, sequence);
            CREATE INDEX ix_task_today ON task_instances(household_id, status, due_at);
            CREATE INDEX ix_task_assignee ON task_instances(assignee_id, status);
            """
        )
        started = time.perf_counter()
        with connection:
            connection.executemany(
                "INSERT INTO users VALUES (?, 1, ?, ?, 1)",
                (
                    (index, f"Участник {index}", "child" if index % 3 == 0 else "adult")
                    for index in range(1, args.users + 1)
                ),
            )
        timings["insert_users_seconds"] = elapsed(started)

        started = time.perf_counter()
        with connection:
            connection.executemany(
                "INSERT INTO storage_items VALUES (?, 1, ?, ?, ?, ?, NULL)",
                (
                    (
                        index,
                        1 + index % 250,
                        f"Вещь {index}",
                        f"вещь {index}",
                        f"категория {index % 18}",
                    )
                    for index in range(1, args.storage_items + 1)
                ),
            )
        timings["insert_storage_seconds"] = elapsed(started)

        started = time.perf_counter()
        with connection:
            connection.executemany(
                "INSERT INTO task_instances VALUES (?, 1, ?, ?, ?, ?, ?)",
                (
                    (
                        index,
                        1 + (index - 1) // 100,
                        1 + (index - 1) % 100,
                        f"2026-08-{1 + index % 28:02d}T12:00:00Z",
                        "completed",
                        1 + index % args.users,
                    )
                    for index in range(1, args.task_instances + 1)
                ),
            )
            connection.executemany(
                "INSERT INTO task_instances VALUES (?, 1, ?, ?, ?, 'open', ?)",
                (
                    (
                        args.task_instances + index,
                        2_000_000 + (index - 1) // 100,
                        1 + (index - 1) % 100,
                        f"2026-08-{1 + index % 28:02d}T12:00:00Z",
                        1 + index % args.users,
                    )
                    for index in range(1, open_tasks + 1)
                ),
            )
        timings["insert_tasks_seconds"] = elapsed(started)

        checks = {
            "users": ("SELECT count(*) FROM users", args.users),
            "storage_items": ("SELECT count(*) FROM storage_items", args.storage_items),
            "task_instances": (
                "SELECT count(*) FROM task_instances",
                args.task_instances + open_tasks,
            ),
            "completed_task_instances": (
                "SELECT count(*) FROM task_instances WHERE status = 'completed'",
                args.task_instances,
            ),
        }
        for label, (query, expected) in checks.items():
            actual = int(connection.execute(query).fetchone()[0])
            if actual != expected:
                raise SystemExit(f"{label}: expected {expected}, found {actual}")

        queries = {
            "storage_exact": (
                "SELECT id, node_id FROM storage_items WHERE normalized_name = ?",
                (f"вещь {args.storage_items // 2}",),
            ),
            "storage_node": (
                "SELECT id, name FROM storage_items "
                "WHERE household_id = 1 AND node_id = ? AND archived_at IS NULL LIMIT 250",
                (125,),
            ),
            "today_open": (
                "SELECT id, due_at FROM task_instances "
                "WHERE household_id = 1 AND status = 'open' AND due_at <= ? LIMIT 2000",
                ("2026-08-15T23:59:59Z",),
            ),
            "member_open": (
                "SELECT id FROM task_instances WHERE assignee_id = ? AND status = 'open' LIMIT 2000",
                (args.users,),
            ),
        }
        row_counts: dict[str, int] = {}
        for label, (query, parameters) in queries.items():
            started = time.perf_counter()
            rows = connection.execute(query, parameters).fetchall()
            duration = elapsed(started)
            timings[f"query_{label}_seconds"] = duration
            row_counts[label] = len(rows)
            if duration > args.query_limit:
                raise SystemExit(f"{label} exceeded {args.query_limit:.1f}s: {duration:.3f}s")
        connection.close()

    print(
        json.dumps(
            {
                "status": "passed",
                "scale": {
                    "users": args.users,
                    "storage_items": args.storage_items,
                    "completed_task_instances": args.task_instances,
                    "open_task_instances": open_tasks,
                },
                "timings": timings,
                "query_rows": row_counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

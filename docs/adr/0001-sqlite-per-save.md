# ADR 0001: SQLite database per save slot

**Status:** Accepted (2026-09-27)

## Context
This is a single-user game that runs locally. It needs 3+ career save slots, autosaves, backups and corruption resistance. The initial preference was PostgreSQL.

## Decision
Each save slot is its own SQLite file (WAL mode).
- Play runs against `saves/slot_N/working.sqlite`.
- Saving uses the SQLite online Backup API to write a temp file. The temp file is then fsynced and passed through `PRAGMA integrity_check`. Finally, `os.replace` swaps it into `career.sqlite` atomically.
- Rotating backups are kept.
- New careers are cloned from a read-only `data/worlds/base-*.sqlite` built by the import pipeline.

## Consequences
- **Positive:** there's no server to install. Save, copy and restore are file operations. Atomic saves come almost for free, and slots are fully isolated.
- **Negative:** only one writer at a time, which is fine for one player. It also means fewer advanced SQL features than PostgreSQL. To compensate, heavy batch work is vectorised in NumPy and written back in bulk transactions.

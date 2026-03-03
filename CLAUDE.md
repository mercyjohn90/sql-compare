# CLAUDE.md — Project Guide for Claude Code

## Project Overview

SQL Compare is a pure Python (3.8+) tool for comparing SQL statements with both GUI (Tkinter) and CLI interfaces. It uses only the Python standard library — no third-party dependencies.

## Key Files

- `sql_compare.py` — Single-file application (~1000 lines) containing all logic: SQL normalization, canonical comparison, diff generation, HTML/TXT reports, and Tkinter GUI.
- `examples/A.sql`, `examples/B.sql` — Example SQL files for testing canonical comparison.
- `examples/two_queries.txt` — Stdin input example (queries separated by `---`).

## How to Run

```bash
# Run the CLI comparison (canonical mode)
python sql_compare.py examples/A.sql examples/B.sql --mode canonical

# Run with HTML report output
python sql_compare.py examples/A.sql examples/B.sql --mode both --report compare.html --report-format html

# Compare inline strings
python sql_compare.py --strings "SELECT a, b FROM t" "SELECT b, a FROM t" --mode canonical

# Launch GUI (requires Tkinter)
python sql_compare.py
```

## How to Verify Changes

There is no formal test suite. Verify changes by running:

```bash
# Quick smoke test — should exit 0 (queries are canonically equivalent)
python sql_compare.py examples/A.sql examples/B.sql --mode canonical

# Verify exact mode detects differences — should exit 1
python sql_compare.py examples/A.sql examples/B.sql --mode exact

# Verify string comparison works
python sql_compare.py --strings "SELECT 1" "SELECT 1" --mode exact
```

## Architecture Notes

- **No external dependencies** — everything uses the Python standard library.
- The tool supports three comparison modes: `exact`, `canonical`, and `both`.
- Canonical comparison normalizes SQL by: stripping comments, collapsing whitespace, uppercasing outside quotes, sorting SELECT lists, sorting WHERE AND terms, and optionally reordering JOINs.
- Exit code 0 = queries are equal; exit code 1 = queries differ.
- GUI is optional and guarded behind a `try/except` import of `tkinter`.

## Code Style

- Python with type hints on function signatures.
- Single-file architecture — all code lives in `sql_compare.py`.
- Use standard library only — do not add third-party dependencies.

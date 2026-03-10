# Copilot Custom Instructions

## Project Context
sql-compare is a Python CLI tool that compares SQL databases across two dimensions:
**schema comparison** (DDL-level structural diffs) and **data comparison** (row-level
result diffing). It targets Oracle, PostgreSQL, MySQL/MariaDB, and SQL Server.
Comparison logic is organized by driver/dialect — do not conflate cross-dialect
handling or add dialect-specific logic outside the appropriate driver module.

## Language & Runtime
* Python >= 3.8 — do not use syntax or stdlib features added after 3.8
  (e.g., `match` statements, `str.removeprefix`, `tomllib`).
* For new or modified modules, include `from __future__ import annotations`
  at the top when practical.

## Code Style
* Entry-point functions must follow the signature `main(argv=None)` so they
  work both as CLI commands and in tests.
* Use `argparse.ArgumentParser` for CLI argument parsing — no click, typer,
  or other frameworks.
* Use `pathlib.Path` for all filesystem operations — never raw `os.path` calls.
* Use `encoding='utf-8'` explicitly on all `open()` / `Path.open()` calls.
* Prefer grouped imports (stdlib, third-party, local) with one blank line
  between groups in new or modified modules.
* Prefer concise code, but avoid packing unrelated statements on one line
  in new or modified modules.
* Connection strings and DSNs must never be constructed via string
  concatenation with user input — always use parameterized driver APIs.

## Dependencies
This project is currently implemented as a single-file Python script using
only the standard library at runtime.

* Do **not** add third-party runtime dependencies (e.g., SQLAlchemy, database
  drivers, `tabulate`, `pyyaml`, etc.) unless the project is explicitly
  restructured and the maintainers agree to introduce them.
* There is no `pyproject.toml`, `setup.py`, or `setup.cfg` in use for
  packaging or dependency management; do not introduce these files unless
  the project is intentionally migrated to a packaged layout.
* When you need functionality, prefer existing standard library modules
  (`argparse`, `pathlib`, `subprocess`, `difflib`, etc.) before considering
  any external library.
* Test or development tools (if used) should be treated as optional and
  should not be assumed to be available unless they are clearly present in
  the repository configuration.
## Project Layout
* Source lives under `src/sql_compare/` (following the `src` layout convention).
  [TODO: confirm actual package name — `sql_compare` vs `sqlcompare`]
* Tests live under `tests/` and run with `pytest -q`.
* Build config is entirely in `pyproject.toml` — there is no `setup.py`
  or `setup.cfg`.
* Driver/dialect adapters live under `src/sql_compare/drivers/`; one module
  per dialect (e.g., `oracle.py`, `postgres.py`, `mysql.py`, `mssql.py`).
* Schema comparison logic lives under `src/sql_compare/schema/`.
* Data comparison logic lives under `src/sql_compare/data/`.
* Windows integration scripts (`*.bat`, `*.ps1`) are not part of the
  Python package.

## Testing
* All tests use pytest (no unittest subclasses).
* Smoke tests call CLI entry points via `subprocess.run` and assert on
  return codes.
* When adding a new module or entry point, add at least a smoke test that
  verifies `--help` exits 0.
* Never import internal modules directly in tests when the intent is to
  test the CLI interface — use subprocess.
* Database-integration tests must be gated behind a marker (e.g.,
  `@pytest.mark.integration`) and skipped by default in CI unless live
  credentials are explicitly provided via environment variables.
* Use fixtures and mocks for unit-testing comparison logic — never require
  a live DB connection for unit tests.

## Review Guidance
When reviewing pull requests, pay attention to:

1. **Python 3.8 compatibility** — flag any use of newer syntax or APIs.
2. **No new runtime dependencies** unless explicitly justified and a driver
   alternative has been evaluated.
3. **Dialect isolation** — cross-dialect logic must stay in shared utilities;
   dialect-specific SQL or introspection belongs in the relevant driver module.
4. **Parameterized queries** — all SQL executed against user-supplied
   connection targets must use bound parameters; no f-string or %-format SQL.
5. **Encoding** — all file I/O must specify `encoding='utf-8'`.
6. **Path handling** — use `pathlib.Path`, not string concatenation or
   `os.path`.
7. **Entry-point contract** — `main(argv=None)` signature, returns an int
   exit code.
8. **Test coverage** — new entry points, drivers, or comparison utilities
   need at least a smoke test; integration tests must be gated behind a marker.
9. **Security** — watch for SQL injection via unsanitized connection params
   or table/column identifiers; validate all user-supplied object names
   against an allowlist or quoted-identifier API before interpolating into DDL.
10. **Secrets** — connection passwords and DSNs must come from environment
    variables or a vault-backed config; never hardcoded or logged.
11. **CI compatibility** — CI runs on `windows-latest`  [TODO: confirm OS];
    avoid Unix-only assumptions (shebangs, forward-slash-only paths,
    Unix signals).
12. **License** — project is MIT  [TODO: confirm]; do not introduce code
    with incompatible licenses.

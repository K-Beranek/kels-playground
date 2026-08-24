# generate-synthetic-data

Populates a live database with synthetic data for one campus, by running a folder of hand-written `.sql` files against it. Unlike [`generate-full-schema`](../generate-full-schema/), this tool doesn't read `els-data-model` at all — it's a small, generic runner: substitute three parameters into each file's text, then execute the file's statements one at a time, in filename order. What the `.sql` files actually insert, and how "complexity" scales, is entirely up to whoever writes them.

## Setup

This needs a real connection to a SQL Server database, unlike `generate-full-schema` (pure local file in, local file out). Two separate things need to be installed:

```bash
pip install -r requirements.txt
```

That installs the `pyodbc` Python package — but `pyodbc` is a thin wrapper around a system-level ODBC driver, not a self-contained SQL Server client. The driver itself is a separate, OS-level install:

- **Windows:** install "ODBC Driver 18 for SQL Server" (or 17) from Microsoft. `pyodbc` will find it automatically once installed.
- **Linux (Debian/Ubuntu):** install `unixodbc` plus Microsoft's `msodbcsql18` package from Microsoft's `packages.microsoft.com` apt repository (see Microsoft's own install docs for the exact `apt` commands — they change occasionally with new Ubuntu releases).
- **macOS:** `brew tap microsoft/mssql-release && brew install msodbcsql18`.

If the driver name installed on your machine doesn't match the default (`ODBC Driver 18 for SQL Server`), pass `--odbc-driver "ODBC Driver 17 for SQL Server"` (or whatever `odbcinst -q -d` reports as installed) — this is one of the most common first-run failures with `pyodbc`, worth checking early if you get a "Data source name not found" error.

Connection details (server, database, credentials) come from the same `config/config.json` that `Invoke-ElsMigration.ps1` uses (see the component README) — copy `config/config.template.json` to `config/config.json` and fill in real values if you haven't already.

## Usage

```bash
python generate_synthetic_data.py --campus-code MAIN2 --name "Second Main Campus" --complexity 100
```

All three parameters are mandatory:

| Parameter | Type | Constraint |
|---|---|---|
| `--campus-code` | string | Non-empty, at most 20 characters — matches `Campus.code`'s length in `els-data-model` (that column has no other format constraint to check against). |
| `--name` | string | Non-empty, at most 200 characters — matches `Campus.name`'s length. |
| `--complexity` | integer | 1–1000. Purely a signal passed through to the `.sql` files; this script has no opinion on what it should scale. |

Optional flags: `--sql-dir` (default: the `sql/` folder next to this script), `--config-path` (default: `../../config/config.json`), `--odbc-driver` (default: `ODBC Driver 18 for SQL Server`).

## How the `.sql` files work

Every `.sql` file in `--sql-dir` is processed in **filename sort order** — name them with a numeric prefix (`001_campus.sql`, `002_course.sql`, ...) if order matters, which it almost always will, since a later file will typically reference rows an earlier one just inserted.

Within a file, **statements are separated by `;`** and run one at a time, in the order they appear. Before running, the script substitutes three placeholders into the file's raw text:

```sql
insert into els.campus(code, uuid, name, description)
values ('{campus_code}', newid(), '{name}', N'Generated synthetic data, complexity {complexity}');
```

`{campus_code}` and `{name}` are substituted with their command-line values, with embedded single quotes doubled (`O'Brien` → `O''Brien`) so they're safe inside the `'...'` literal the file itself supplies — the file is responsible for the surrounding quotes, the script only escapes what goes inside them. `{complexity}` is substituted as a plain integer, unquoted, so it can be used either inside a string (as in the example) or as a bare numeric literal (e.g. `TOP ({complexity})`). Any `{other_name}` placeholder that isn't one of these three causes a clear error naming the file and the unknown placeholder, rather than a confusing SQL syntax error at execution time.

### What the statement splitter does and doesn't understand

The splitter is a character scan, not a full SQL parser. It correctly handles:

- A `;` inside a `'...'` string literal (including a doubled `''` escaped quote) — doesn't end the statement.
- A `;` inside a `--` line comment or `/* */` block comment — doesn't end the statement, and comment-only text between two statements isn't treated as an (empty) statement of its own.

It deliberately does **not** understand:

- SQL Server's `GO` batch separator. `GO` is a convention understood by `sqlcmd`/SSMS/Flyway, not real T-SQL — this script sends statement text straight to the server via `pyodbc`, which would reject a literal `GO` as a syntax error. Don't put `GO` in these files.
- Any construct where an internal `;` needs to stay part of the same statement as one outside it — a `BEGIN...END` block, a multi-statement `IF`, a stored procedure body. Each embedded `;` would be incorrectly treated as its own statement boundary. Keep these files to standalone `INSERT`/`UPDATE`/`DELETE`/`SELECT` statements — if you need real procedural logic, that belongs in a real stored procedure (under `migrations/`), called from here with a single `EXEC` statement instead.

## Error handling — stop immediately, no rollback

The moment any statement fails, the script prints the file name, the line number the failed statement started on, and the database's own error text, then exits non-zero — no later files or statements run.

**No transaction management.** The script never issues `BEGIN TRAN`, `COMMIT`, or `ROLLBACK` — the connection runs in `pyodbc`'s autocommit mode, so every statement that succeeds is permanent the instant it runs. This is a deliberate, but not free, trade-off: it means a failure partway through leaves the database in a partially-populated state, with everything before the failure already committed. Concretely — if a run fails while inserting `Course` rows for a campus whose `Campus` row it already inserted successfully, simply re-running the same command will fail again immediately: `Campus.code` is unique, and the campus this run tries to insert already exists from the previous, failed attempt. Fixing the underlying problem and re-running from scratch for the *same* `--campus-code` therefore isn't safe without first cleaning up whatever the failed run already committed (or picking a new `--campus-code` for the retry). Wrapping the whole run in a single transaction would avoid this, but was explicitly left out for now — see this component's `CLAUDE.md` for the reasoning.

## Known limitations

- No dry-run mode — every statement that parses is actually executed. Test against a throwaway/dev database first, not directly against anything you care about.
- No idempotency built in. Running the same `--campus-code` twice will hit `Campus.code`'s uniqueness constraint (or whatever other unique constraints the `.sql` files' target tables carry) unless the files are written to check for existing rows first (e.g. `IF NOT EXISTS (...)`) — this script doesn't do that for you.
- `--complexity`'s meaning is not enforced or interpreted here at all; it's just a number passed through. If a `.sql` file ignores it, or two files interpret it inconsistently (one scales linearly, another exponentially), that's a modeling decision in the `.sql` files, not something this script can catch.

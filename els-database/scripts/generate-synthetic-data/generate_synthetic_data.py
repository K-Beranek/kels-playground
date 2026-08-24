#!/usr/bin/env python3
"""
generate_synthetic_data.py

Populates a database with synthetic data for one campus by running a folder of hand-written .sql
files against it, in filename order, substituting three script-level parameters into each file's
text before executing it:

    campus_code   -- becomes {campus_code} wherever it appears in a .sql file
    name          -- becomes {name}
    complexity    -- becomes {complexity}

This tool does not know or care what the .sql files actually do -- it doesn't read
els-data-model at all. It's a thin, generic "render placeholders, then run the statements"
runner; the actual data-generation logic (how many rows, which tables, what "complexity" should
scale) lives entirely in the .sql files themselves, which you write. See sql/ for the one example
file included here, and README.md for the placeholder-substitution and statement-splitting rules
those files need to follow.

Execution order and error handling:
  - Files in --sql-dir are processed in filename sort order (so name them with a numeric prefix,
    e.g. 001_campus.sql, 002_course.sql, if order matters -- it almost certainly does, since later
    files will typically reference rows the earlier ones just inserted).
  - Each file can contain more than one statement, separated by ';'. Statements run one at a time,
    in the order they appear in the file.
  - The moment any statement fails, the script prints the file name, the line number the failed
    statement started on, and the database's own error text, then stops immediately -- no later
    files or statements run.
  - The script does not manage transactions at all: no BEGIN TRAN, no COMMIT, no ROLLBACK. The
    connection runs in autocommit mode, so every statement that succeeds is permanent the moment
    it runs. This means a failure partway through leaves the database in a partially-populated
    state -- whatever ran before the failure stays. See README.md's "No transaction management"
    section for why this was the deliberate choice here, and what it means for re-running after a
    failure.

Usage:
    python generate_synthetic_data.py --campus-code MAIN2 --name "Second Main Campus" --complexity 100
    python generate_synthetic_data.py --campus-code MAIN2 --name "Second Main Campus" --complexity 100 \\
        --sql-dir ./sql --config-path ../../config/config.json --odbc-driver "ODBC Driver 17 for SQL Server"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import pyodbc
except ImportError:
    sys.exit(
        "The 'pyodbc' package is required but is not installed.\n"
        "Install it with:\n"
        "    pip install -r requirements.txt\n"
        "pyodbc also needs a Microsoft ODBC Driver for SQL Server installed at the OS level --\n"
        "see README.md's Setup section, this is not something 'pip install' can provide."
    )

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SQL_DIR = SCRIPT_DIR / "sql"
DEFAULT_CONFIG_PATH = (SCRIPT_DIR / ".." / ".." / "config" / "config.json").resolve()
DEFAULT_ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

# Matches Campus.code / Campus.name's length limits in els-data-model's entity definition
# (model/entities/campus.json). Kept as plain constants here rather than read from that JSON --
# this tool deliberately doesn't depend on els-data-model at all (see module docstring) -- so if
# those lengths ever change there, update these two numbers by hand to match.
CAMPUS_CODE_MAX_LENGTH = 20
CAMPUS_NAME_MAX_LENGTH = 200

PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def complexity_type(raw_value: str) -> int:
    """argparse type= callable for --complexity: an integer in [1, 1000]."""
    try:
        value = int(raw_value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"complexity must be an integer, got {raw_value!r}")
    if not (1 <= value <= 1000):
        raise argparse.ArgumentTypeError(f"complexity must be between 1 and 1000, got {value}")
    return value


def validate_campus_code(value: str) -> None:
    if not value:
        raise ValueError("campus_code must not be empty")
    if "\n" in value or "\r" in value:
        raise ValueError("campus_code must not contain line breaks")
    if len(value) > CAMPUS_CODE_MAX_LENGTH:
        raise ValueError(
            f"campus_code is {len(value)} characters long; Campus.code allows at most "
            f"{CAMPUS_CODE_MAX_LENGTH}"
        )


def validate_name(value: str) -> None:
    if not value:
        raise ValueError("name must not be empty")
    if "\n" in value or "\r" in value:
        raise ValueError("name must not contain line breaks")
    if len(value) > CAMPUS_NAME_MAX_LENGTH:
        raise ValueError(
            f"name is {len(value)} characters long; Campus.name allows at most "
            f"{CAMPUS_NAME_MAX_LENGTH}"
        )


def render_template(text: str, values: dict[str, str]) -> str:
    """Replace every {placeholder} in `text` with its value from `values`.

    Deliberately not Python's str.format(): format() treats a literal '{' anywhere in the text
    (there is none expected in T-SQL, but better not to assume) as the start of a replacement
    field and raises a fairly opaque KeyError/ValueError if the file has a typo'd or unknown
    placeholder. This does the same substitution but with a regex restricted to
    {identifier}-shaped tokens, and raises a clear, specific error naming the bad placeholder
    instead.
    """

    def replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            known = ", ".join(sorted(values))
            raise ValueError(f"unknown placeholder '{{{key}}}' -- known placeholders: {known}")
        return values[key]

    return PLACEHOLDER_PATTERN.sub(replace, text)


def split_statements(text: str) -> list[tuple[int, str]]:
    """Split `text` into individual SQL statements on top-level ';' characters, returning
    (line_number, statement_text) pairs. line_number is the 1-based line the statement's first
    real (non-comment, non-whitespace) character appears on.

    This is a character-by-character scan, not a real SQL parser, but it understands enough T-SQL
    to be safe for straightforward DML:
      - A ';' inside a single-quoted string ('...') does not end a statement. '' (two single
        quotes) inside a string is recognized as an escaped quote, not the string's end.
      - A ';' inside a line comment (-- ...) or block comment (/* ... */) does not end a
        statement, and comment-only text between two statements does not count as its own
        (empty) statement.
      - Leading/trailing whitespace around a statement is stripped; blank segments (e.g. a
        trailing blank line after the last ';') produce no entry.

    What it deliberately does NOT understand -- keep .sql files here to plain statements and this
    won't matter, but it's worth knowing the boundary:
      - SQL Server's `GO` batch separator. GO is a convention understood by sqlcmd/SSMS/Flyway,
        not a real T-SQL keyword -- pyodbc sends whatever text it's given straight to the server,
        which would reject a literal "GO" as a syntax error. Don't put GO in these files.
      - Any construct where a semicolon inside the statement is meant to stay part of the SAME
        statement as a semicolon outside it -- e.g. a BEGIN...END block, an IF with multiple
        statements, or a stored procedure body. Each of those would be incorrectly split into
        several separate statements here. Keep files to standalone INSERT/UPDATE/DELETE/SELECT
        statements.
    """
    statements: list[tuple[int, str]] = []
    current: list[str] = []
    start_line: int | None = None
    line = 1

    in_line_comment = False
    in_block_comment = False
    in_string = False

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if in_line_comment:
            current.append(ch)
            if ch == "\n":
                in_line_comment = False
                line += 1
            i += 1
            continue

        if in_block_comment:
            current.append(ch)
            if ch == "\n":
                line += 1
            if ch == "*" and nxt == "/":
                current.append(nxt)
                i += 2
                in_block_comment = False
                continue
            i += 1
            continue

        if in_string:
            current.append(ch)
            if ch == "'":
                if nxt == "'":
                    current.append(nxt)
                    i += 2
                    continue
                in_string = False
            elif ch == "\n":
                line += 1
            i += 1
            continue

        # Not inside a comment or a string literal.
        if ch == "-" and nxt == "-":
            in_line_comment = True
            current.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "*":
            in_block_comment = True
            current.append(ch)
            i += 1
            continue

        if ch == "'":
            in_string = True
            if start_line is None:
                start_line = line
            current.append(ch)
            i += 1
            continue

        if ch == ";":
            statement_text = "".join(current).strip()
            if statement_text and start_line is not None:
                statements.append((start_line, statement_text))
            current = []
            start_line = None
            i += 1
            continue

        if ch == "\n":
            line += 1
            if current:
                current.append(ch)
            i += 1
            continue

        if ch.isspace():
            if current:
                current.append(ch)
            i += 1
            continue

        # A real, non-whitespace, non-comment character: this is where a statement starts.
        if start_line is None:
            start_line = line
        current.append(ch)
        i += 1

    # Trailing comment-only or whitespace-only text after the last statement (start_line is None
    # because no real, non-comment character was ever seen) is harmless and ignored. Trailing text
    # that DOES include real content (start_line is set) means the file ended mid-statement, with
    # no closing ';' -- that's a genuine authoring mistake worth failing loudly on rather than
    # silently executing a statement the author might not have meant to end there.
    trailing = "".join(current).strip()
    if trailing and start_line is not None:
        raise ValueError(
            f"file ends with an unterminated statement starting at line {start_line} "
            "-- every statement must end with ';'"
        )

    return statements


def build_connection_string(config: dict, odbc_driver: str) -> str:
    sql_server = config["sqlServer"]
    auth = config["auth"]

    instance_name = sql_server.get("instanceName") or ""
    if instance_name:
        server = f"{sql_server['host']}\\{instance_name}"
    else:
        server = f"{sql_server['host']},{sql_server.get('port', 1433)}"

    encrypt = "yes" if sql_server.get("encrypt", True) else "no"
    trust_cert = "yes" if sql_server.get("trustServerCertificate", False) else "no"

    return (
        f"DRIVER={{{odbc_driver}}};"
        f"SERVER={server};"
        f"DATABASE={sql_server['database']};"
        f"UID={auth['user']};"
        f"PWD={auth['password']};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust_cert};"
    )


def run_sql_folder(
    connection: "pyodbc.Connection", sql_dir: Path, values: dict[str, str]
) -> int:
    sql_files = sorted(p for p in sql_dir.glob("*.sql") if p.is_file())
    if not sql_files:
        print(f"Error: no .sql files found in {sql_dir}", file=sys.stderr)
        return 1

    cursor = connection.cursor()
    total_statements = 0

    for sql_file in sql_files:
        raw_text = sql_file.read_text(encoding="utf-8")

        try:
            rendered_text = render_template(raw_text, values)
            statements = split_statements(rendered_text)
        except ValueError as e:
            print(f"FAILED: {sql_file.name}: {e}", file=sys.stderr)
            return 1

        for line_number, statement in statements:
            try:
                cursor.execute(statement)
            except pyodbc.Error as e:
                print(
                    f"FAILED: {sql_file.name}, line {line_number}: {e}",
                    file=sys.stderr,
                )
                return 1
            total_statements += 1

    print(f"Executed {total_statements} statement(s) across {len(sql_files)} file(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--campus-code", required=True,
        help="Value to substitute for {campus_code} -- must fit Campus.code's format "
             f"(non-empty, at most {CAMPUS_CODE_MAX_LENGTH} characters).",
    )
    parser.add_argument(
        "--name", required=True,
        help="Value to substitute for {name} -- becomes Campus.name "
             f"(non-empty, at most {CAMPUS_NAME_MAX_LENGTH} characters).",
    )
    parser.add_argument(
        "--complexity", required=True, type=complexity_type,
        help="Value to substitute for {complexity} -- an integer from 1 to 1000 indicating how "
             "large the generated data set should be. What it actually controls is entirely up "
             "to the .sql files -- this script just passes the number through.",
    )
    parser.add_argument(
        "--sql-dir", type=Path, default=DEFAULT_SQL_DIR,
        help="Folder of .sql files to run, in filename sort order (default: %(default)s)",
    )
    parser.add_argument(
        "--config-path", type=Path, default=DEFAULT_CONFIG_PATH,
        help="Path to the JSON config file with sqlServer/auth connection details, same file "
             "used by Invoke-ElsMigration.ps1 (default: %(default)s)",
    )
    parser.add_argument(
        "--odbc-driver", default=DEFAULT_ODBC_DRIVER,
        help="Name of the installed Microsoft ODBC driver for SQL Server to connect with "
             "(default: %(default)s). Change this if your machine has a different version "
             "installed -- see README.md.",
    )
    args = parser.parse_args()

    try:
        validate_campus_code(args.campus_code)
        validate_name(args.name)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not args.sql_dir.is_dir():
        print(f"Error: --sql-dir '{args.sql_dir}' is not a folder", file=sys.stderr)
        return 1

    if not args.config_path.exists():
        print(
            f"Error: config file not found at '{args.config_path}'. Copy "
            "config/config.template.json to config/config.json (or another gitignored name) "
            "and fill in real values first.",
            file=sys.stderr,
        )
        return 1

    config = json.loads(args.config_path.read_text(encoding="utf-8"))

    # Escaped for safe use inside a T-SQL '...' string literal -- the same doubling-single-quotes
    # rule generate-full-schema's sql_string_literal() uses. Each .sql file is still responsible
    # for supplying the surrounding quotes itself (see the module docstring's example), this only
    # escapes the *content* being substituted in.
    values = {
        "campus_code": args.campus_code.replace("'", "''"),
        "name": args.name.replace("'", "''"),
        "complexity": str(args.complexity),
    }

    connection_string = build_connection_string(config, args.odbc_driver)
    try:
        # autocommit=True: see the module docstring's "Execution order and error handling"
        # section -- this script deliberately does no transaction management of its own.
        connection = pyodbc.connect(connection_string, autocommit=True)
    except pyodbc.Error as e:
        print(f"Error: could not connect to the database: {e}", file=sys.stderr)
        return 1

    try:
        return run_sql_folder(connection, args.sql_dir, values)
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())

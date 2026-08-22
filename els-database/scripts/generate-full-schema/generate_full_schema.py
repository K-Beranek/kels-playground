#!/usr/bin/env python3
"""
generate_full_schema.py

Reads the entity definitions in els-data-model (validating each one against its JSON Schema) and
generates a single T-SQL script that builds the "els" schema from scratch: CREATE SCHEMA, one
CREATE TABLE per entity, ALTER TABLE ... ADD CONSTRAINT for foreign keys, and — since SQL Server has
no ANSI COMMENT ON support — calls to utils.set_table_comment / utils.set_column_comment (see
migrations/utils/) for any entity/column `comment` in the model. Those procedures store the comment
as an 'MS_Description' extended property, the convention SSMS and most third-party
schema-documentation tools already read, and set it idempotently regardless of whether it was
already set.

PREREQUISITE: the `utils` schema's migrations (migrations/utils/) must already be deployed before
running the output of this script — it calls utils.set_table_comment/set_column_comment, it doesn't
define them. This isn't checked by the generated script itself (see els-database/CLAUDE.md for why),
only documented here and in the generated file's own header comment.

The output is a *reference*, not a Flyway migration: it represents the full desired state of the
schema according to the model, written to full_db_model/wip/ so it can be compared against
full_db_model/current/ when deciding what an actual migration needs to contain.

Determinism is a hard requirement, not a nice-to-have: running this script twice against an
unchanged model must produce a byte-identical file, and adding a new entity or column must never
change the relative order of statements that were already there. That's achieved here by:

  - Sorting entities by name immediately after loading them, rather than trusting directory-listing
    order (which isn't guaranteed stable) or the order they happened to be added in.
  - Never using a Python `set()` for anything that affects output order — string hashing is
    randomized per-process by default, so set iteration order can vary between runs even for
    identical input.
  - Never writing a timestamp, or anything else non-reproducible, into the generated file itself.
  - Writing with a fixed encoding (UTF-8) and fixed line endings (\\n) regardless of platform.

Usage:
    python generate_full_schema.py
    python generate_full_schema.py --check
    python generate_full_schema.py --model-dir ../../../els-data-model --db-schema els
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    sys.exit(
        "The 'jsonschema' package is required but is not installed.\n"
        "Install it with:\n"
        "    pip install -r requirements.txt"
    )

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_DIR = (SCRIPT_DIR / ".." / ".." / ".." / "els-data-model").resolve()
DEFAULT_OUTPUT = (SCRIPT_DIR / ".." / ".." / "full_db_model" / "wip" / "els_full_schema.sql").resolve()

# Abstract model types (from els-data-model's model.schema.json) -> SQL Server types.
# Extend this dict as new abstract types are added to the model.
SQL_SERVER_TYPES = {
    "integer": lambda column: "INT",
    "boolean": lambda column: "BIT",
    "date": lambda column: "DATE",
    "datetime": lambda column: "DATETIME2",
    "text": lambda column: "NVARCHAR(MAX)",
    "string": lambda column: f"NVARCHAR({column.get('length', 255)})",
    # The model doesn't carry precision/scale yet, so this is a fixed default until it does.
    "decimal": lambda column: "DECIMAL(18, 2)",
}


def load_entities(model_dir: Path) -> list[dict]:
    """Load every entity definition, validate it against the model's JSON Schema, and return
    them sorted by entity name.

    Sorting immediately after loading (rather than relying on filesystem/glob order) is what
    makes every downstream statement order deterministic and stable under insertion: two entities'
    relative order depends only on comparing their two names, never on what else exists or when
    things were added.
    """
    schema_path = model_dir / "model" / "schema" / "model.schema.json"
    entities_dir = model_dir / "model" / "entities"

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found at {schema_path}")
    if not entities_dir.is_dir():
        raise FileNotFoundError(f"Entities folder not found at {entities_dir}")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    entities = []
    for entity_file in entities_dir.glob("*.json"):
        entity = json.loads(entity_file.read_text(encoding="utf-8"))
        try:
            jsonschema.validate(entity, schema)
        except jsonschema.exceptions.ValidationError as e:
            # Re-raise with the source filename attached — the raw error's `instance` may be a
            # nested part of the document (e.g. one column), not the whole entity, so it can't
            # reliably be used to name which entity file is at fault.
            raise jsonschema.exceptions.ValidationError(
                f"{entity_file.name}: {e.message}"
            ) from e
        entities.append(entity)

    if not entities:
        raise ValueError(f"No entity definitions found in {entities_dir}")

    entities.sort(key=lambda e: e["entity"])
    return entities


def render_column(column: dict) -> str:
    type_fn = SQL_SERVER_TYPES.get(column["type"])
    if type_fn is None:
        raise ValueError(f"No SQL Server mapping defined for abstract type '{column['type']}'")
    sql_type = type_fn(column)

    is_identity = column.get("identity", False)
    if is_identity and column["nullable"]:
        # The model's JSON Schema already forbids this combination (see the column `allOf`/`if`/
        # `then` rule), so this should only trip if the schema and this script have drifted apart —
        # kept here anyway as a clear, specific error rather than trusting that alone.
        raise ValueError(
            f"Column '{column['name']}' is marked identity but nullable=true — "
            "SQL Server identity columns cannot allow NULL."
        )
    identity_clause = " IDENTITY(1,1)" if is_identity else ""

    nullability = "NULL" if column["nullable"] else "NOT NULL"
    return f"    {column['name']} {sql_type}{identity_clause} {nullability}"


def render_unique_constraints(entity: dict) -> list[str]:
    """Render standalone (`unique: true`) and composite (`uniqueWith: [...]`) constraint lines.

    A column marked `primaryKey` is skipped entirely — the primary key already guarantees
    uniqueness, so a redundant UNIQUE constraint would add nothing.

    The constraint name is always `UQ_<table>_<column>`, using only the column that carries the
    `unique`/`uniqueWith` property -- unaffected by whether the constraint ends up single- or
    multi-column. For a composite constraint, the generated column order is `uniqueWith`'s names
    in the order listed, followed by the annotated column itself (e.g. `uniqueWith: ["campus_id"]`
    on `course_number` produces `UNIQUE (campus_id, course_number)`).

    `column_names` below is a set used only for an O(1) membership check (does a referenced name
    actually exist on this entity) -- not for anything that affects output order, so it doesn't
    run into the "avoid set() for anything order-affecting" rule this generator otherwise follows.
    """
    column_names = {c["name"] for c in entity["columns"]}
    lines = []

    for column in entity["columns"]:
        if column.get("primaryKey"):
            continue

        is_unique = column.get("unique", False)
        unique_with = column.get("uniqueWith")

        if is_unique and unique_with:
            # The model's JSON Schema already forbids this combination (see the column `allOf`/
            # `if`/`then` rule), so this should only trip if the schema and this script have
            # drifted apart -- kept here anyway, same reasoning as the identity/nullable check.
            raise ValueError(
                f"{entity['entity']}.{column['name']}: 'unique' and 'uniqueWith' cannot both be "
                "set on the same column -- use 'unique' for a standalone constraint or "
                "'uniqueWith' for a composite one, not both."
            )

        if unique_with:
            # Unlike the mutual-exclusivity check above, the JSON Schema has no practical way to
            # confirm these names refer to real sibling columns (that would need cross-referencing
            # the rest of the same array), so this check exists only here, not at the schema layer.
            for other in unique_with:
                if other == column["name"]:
                    raise ValueError(
                        f"{entity['entity']}.{column['name']}: 'uniqueWith' lists its own column "
                        "-- remove it, it's implied."
                    )
                if other not in column_names:
                    raise ValueError(
                        f"{entity['entity']}.{column['name']}: 'uniqueWith' references unknown "
                        f"column '{other}'."
                    )
            constraint_columns = [*unique_with, column["name"]]
            lines.append(
                f"    CONSTRAINT UQ_{entity['table']}_{column['name']} "
                f"UNIQUE ({', '.join(constraint_columns)})"
            )
        elif is_unique:
            lines.append(
                f"    CONSTRAINT UQ_{entity['table']}_{column['name']} UNIQUE ({column['name']})"
            )

    return lines


def render_create_table(entity: dict, db_schema: str) -> str:
    table = f"{db_schema}.{entity['table']}"
    lines = [render_column(column) for column in entity["columns"]]

    # Primary key: always a named table-level constraint, even for a single column, so composite
    # keys (multiple columns) don't need special-casing. Column order = array order in the JSON,
    # which is the documented convention for composite key column order.
    pk_columns = [c["name"] for c in entity["columns"] if c.get("primaryKey")]
    if pk_columns:
        lines.append(f"    CONSTRAINT PK_{entity['table']} PRIMARY KEY ({', '.join(pk_columns)})")

    lines.extend(render_unique_constraints(entity))

    body = ",\n".join(lines)
    return f"CREATE TABLE {table} (\n{body}\n);"


def render_foreign_keys(entity: dict, table_by_entity: dict[str, str], db_schema: str) -> list[str]:
    """Foreign keys are emitted as ALTER TABLE statements, run only after every CREATE TABLE has
    already happened. That sidesteps needing to topologically sort tables by dependency — it
    doesn't matter which table is created first, since no FK is added until all of them exist."""
    statements = []
    for column in entity["columns"]:
        fk = column.get("foreignKey")
        if not fk:
            continue
        ref_table = table_by_entity[fk["entity"]]
        table = f"{db_schema}.{entity['table']}"
        constraint = f"FK_{entity['table']}_{column['name']}"
        statements.append(
            f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
            f"FOREIGN KEY ({column['name']}) REFERENCES {db_schema}.{ref_table} ({fk['column']});"
        )
    return statements


def sql_string_literal(value: str) -> str:
    """Render a Python string as a T-SQL Unicode string literal, escaping embedded single quotes
    by doubling them (the standard T-SQL escape — there is no backslash-escaping in T-SQL)."""
    return "N'" + value.replace("'", "''") + "'"


def render_comments(entity: dict, db_schema: str) -> list[str]:
    """Table- and column-level `comment` text (if present) is set via utils.set_table_comment /
    utils.set_column_comment (migrations/utils/) rather than calling sys.sp_addextendedproperty /
    sys.sp_updateextendedproperty directly here. Those procedures already do the "does this
    already have an MS_Description? add vs. update" check idempotently — duplicating that branch
    in this generator would be the same logic maintained in two places. The trade-off: this
    generated script now depends on `utils` being deployed first (see the PREREQUISITE note in
    this module's docstring and in the generated file's own header). Entities/columns with no
    `comment` produce no statement — there's nothing meaningful to set a comment to."""
    statements = []

    table_comment = entity.get("comment")
    if table_comment:
        statements.append(
            "EXEC utils.set_table_comment "
            f"@schema_name = N'{db_schema}', "
            f"@table_name = N'{entity['table']}', "
            f"@comment = {sql_string_literal(table_comment)};"
        )

    for column in entity["columns"]:
        column_comment = column.get("comment")
        if not column_comment:
            continue
        statements.append(
            "EXEC utils.set_column_comment "
            f"@schema_name = N'{db_schema}', "
            f"@table_name = N'{entity['table']}', "
            f"@column_name = N'{column['name']}', "
            f"@comment = {sql_string_literal(column_comment)};"
        )

    return statements


def generate_sql(entities: list[dict], db_schema: str) -> str:
    table_by_entity = {e["entity"]: e["table"] for e in entities}

    parts = [
        "-- Auto-generated by scripts/generate-full-schema/generate_full_schema.py. Do not edit by hand.",
        "-- Source: els-data-model/model/entities/*.json",
        "-- Regenerate with: python generate_full_schema.py",
        "--",
        "-- This file deliberately carries no generation timestamp: regenerating it from an",
        "-- unchanged model must produce a byte-identical file.",
        "--",
        "-- PREREQUISITE: this script calls utils.set_table_comment / utils.set_column_comment for",
        "-- table/column comments, so the 'utils' schema's migrations (migrations/utils/) must",
        "-- already be deployed before this script is run. Not checked here by design — see",
        "-- els-database/CLAUDE.md.",
        "",
        f"IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = '{db_schema}')",
        "BEGIN",
        f"    EXEC('CREATE SCHEMA {db_schema}');",
        "END",
        "GO",
        "",
    ]

    for entity in entities:
        parts.append(render_create_table(entity, db_schema))
        parts.append("")

    parts.append("GO")
    parts.append("")

    fk_statements = []
    for entity in entities:
        fk_statements.extend(render_foreign_keys(entity, table_by_entity, db_schema))

    if fk_statements:
        parts.append("-- Foreign key constraints.")
        parts.extend(fk_statements)
        parts.append("")
        parts.append("GO")
        parts.append("")

    comment_statements = []
    for entity in entities:
        comment_statements.extend(render_comments(entity, db_schema))

    if comment_statements:
        parts.append(
            "-- Table/column comments, set via utils.set_table_comment/set_column_comment "
            "(requires the utils schema to be deployed first — see header above)."
        )
        parts.extend(comment_statements)
        parts.append("")
        parts.append("GO")
        parts.append("")

    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--model-dir", type=Path, default=DEFAULT_MODEL_DIR,
        help="Path to the els-data-model component (default: %(default)s)",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="Path to write the generated .sql file to (default: %(default)s)",
    )
    parser.add_argument(
        "--db-schema", default="els",
        help="Target SQL Server schema name (default: %(default)s)",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Don't write anything — generate in memory and exit non-zero if it would differ from "
             "the existing output file. Useful to confirm the model and the generated file haven't "
             "drifted apart.",
    )
    args = parser.parse_args()

    try:
        entities = load_entities(args.model_dir)
        sql = generate_sql(entities, args.db_schema)
    except jsonschema.exceptions.ValidationError as e:
        print(f"Entity validation failed: {e.message}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.check:
        if not args.output.exists():
            print(f"NO EXISTING FILE: {args.output} has not been generated yet.", file=sys.stderr)
            return 1
        existing = args.output.read_text(encoding="utf-8")
        if existing == sql:
            print(f"OK: {args.output} is up to date with the model.")
            return 0
        print(f"DRIFT: {args.output} does not match what the current model would generate.", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as f:
        f.write(sql)

    print(f"Wrote {len(entities)} table(s) to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# generate-full-schema

Reads the entity definitions in [`els-data-model`](../../../els-data-model/), validates them against its JSON Schema, and generates a single T-SQL script that builds the `els` schema from scratch — `CREATE SCHEMA`, one `CREATE TABLE` per entity, `ALTER TABLE ... ADD CONSTRAINT` for foreign keys, then calls to `utils.set_table_comment`/`utils.set_column_comment` for any `comment` text in the model.

The output is written to `full_db_model/wip/els_full_schema.sql` (gitignored — see the component README). It's a *reference* of the full desired schema, not a Flyway migration: the idea is to compare it against `full_db_model/current/` to work out what an actual migration needs to contain. Schema only — seed data is out of scope here; a separate tool will handle data.

**Prerequisite:** the generated script calls `utils.set_table_comment`/`utils.set_column_comment` (see [`../../migrations/utils/`](../../migrations/utils/)), so the `utils` schema must already be deployed (`Invoke-ElsMigration.ps1 -Schema utils`) before the generated `.sql` file can run successfully. This tool doesn't check that for you — see [the component `CLAUDE.md`](../../CLAUDE.md) for why.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
python generate_full_schema.py                  # writes full_db_model/wip/els_full_schema.sql
python generate_full_schema.py --check           # exits non-zero if the model and the existing file have drifted apart, without writing anything
python generate_full_schema.py --db-schema els   # override the target schema name (default: els)
python generate_full_schema.py --model-dir /path/to/els-data-model --output /path/to/out.sql
```

## Determinism

This was a specific requirement, not an accident: regenerating from an unchanged model must produce a byte-identical file, and adding a new entity or column must never reorder statements that were already there. That's why:

- Entities are sorted by name right after loading, not processed in whatever order the filesystem happens to list them. A sort is stable under insertion — two existing entities' relative order can never change just because a third one was added, since it only ever depends on comparing those two names to each other.
- The file has no generated-on timestamp or anything else that would differ between two runs of an unchanged model.
- Output is written with fixed encoding (UTF-8) and fixed line endings (`\n`), so the same model produces the same bytes regardless of platform.
- Nothing in the code relies on Python `set()` ordering for anything that ends up in the output — set iteration order isn't guaranteed stable across runs.

## Column features supported

- Primary keys, single-column or composite (always a named table-level `CONSTRAINT PK_<table>`, even for one column).
- Standalone unique constraints (`unique: true`) and composite ones (`uniqueWith: ["other_column", ...]`) — both render as `CONSTRAINT UQ_<table>_<column>`, named after whichever column carries the property, with a composite constraint's column list ordered as `uniqueWith`'s names followed by that column (e.g. `Course.course_number`'s `uniqueWith: ["campus_id"]` renders `UNIQUE (campus_id, course_number)`). The two are mutually exclusive on one column (enforced by the model's JSON Schema); a `uniqueWith` entry naming a column that doesn't exist on the entity, or naming itself, is caught here with a clear error, since that check isn't practical to express in JSON Schema alone.
- Foreign keys, always added via `ALTER TABLE` after every table is created, specifically so table order never has to account for dependencies between entities.
- `identity: true` columns render as `IDENTITY(1,1)`. An identity column must also be `nullable: false` — this is enforced both by the model's own JSON Schema and, redundantly, by this script (`render_column` raises a clear error if it's ever reached with the contradiction).
- Entity/column `comment` text (if present) is rendered as calls to `utils.set_table_comment` / `utils.set_column_comment` (see [`../../migrations/utils/`](../../migrations/utils/)), which set an `MS_Description` extended property idempotently — the convention SSMS itself uses, and that most third-party schema-documentation tools (Redgate SQL Doc, ApexSQL Doc, etc.) already read. SQL Server has no ANSI `COMMENT ON`, unlike Oracle/Snowflake, so this is the native equivalent. Entities/columns with no `comment` produce no statement. This tool used to call `sys.sp_addextendedproperty` directly; it was switched to call the `utils` procedures once they existed, so the add-vs-update decision lives in one place instead of being duplicated here.

## Known limitations

- `decimal` columns render with a fixed `DECIMAL(18, 2)` — the model doesn't carry precision/scale yet. Not an issue today since no entity uses `decimal`, but worth knowing if one is added.
- `string` columns with no `length` fall back to `NVARCHAR(255)`. Every entity so far specifies a length explicitly.

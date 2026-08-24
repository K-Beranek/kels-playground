# eLearning System Database (`els-database`)

SQL Server database code for the fictional eLearning System: Flyway migration scripts, the tooling to run them, and a working area for modeling schema changes before they become migrations. This component owns the physical database — the [`els-data-model`](../els-data-model/) component owns the logical entity definitions it's derived from.

## Layout

```
els-database/
├── full_db_model/
│   ├── current/    A full, current-state snapshot of the deployed schema (source-of-truth reference)
│   └── wip/         Scratch/in-progress model drafts — tracked as a folder, contents gitignored
├── migrations/
│   ├── utils/      Flyway migration scripts for the "utils" schema (reusable tooling)
│   └── els/        Flyway migration scripts for the "els" schema
├── config/
│   ├── config.template.json   Committed template — copy it, real configs are gitignored
│   └── (config.json, etc.)    Real, local-only configs — never committed
└── scripts/
    ├── Invoke-ElsMigration.ps1     Runs Flyway against one schema's migrations using a local config file
    ├── generate-full-schema/       Python tool: els-data-model -> full_db_model/wip/*.sql
    └── generate-synthetic-data/    Python tool: runs a folder of hand-written .sql files against a live database
```

### `full_db_model`

Holds a full definition of the target schema, split into `current` (what's actually deployed — a reference point, not something edited by hand) and `wip` (drafts of the *next* change, before it's turned into a proper Flyway migration). `wip`'s contents are gitignored on purpose — the folder is tracked (via `wip/.gitignore` itself) so it exists in a fresh clone, but nothing dropped into it becomes part of the repo.

`scripts/generate-full-schema/` writes `wip/els_full_schema.sql`: the full schema as `els-data-model` currently defines it, regenerated on demand. `current/` is still empty — it's meant to hold the schema as actually deployed, and there's nothing deployed yet. See [Schema change workflow](#schema-change-workflow) below for how `wip` and `current` are meant to be used together once there is.

### `migrations/els`

One subfolder per schema, so a second schema later (if one shows up) gets its own `migrations/<schema>` folder rather than mixing files together. Flyway migration files follow Flyway's own naming rules:

- `V<version>__<description>.sql` — versioned migrations, applied once each, in order, and never changed after being applied.
- `R__<description>.sql` — repeatable migrations, re-applied whenever their content changes (after all pending versioned ones), typically used for views, stored procedures, functions, and permission grants that are fully replaced on every run rather than incrementally altered.

`R__placeholder.sql` is a no-op stand-in so this folder and the deploy script have something real to run end-to-end before any actual schema objects exist.

### `migrations/utils`

Reusable database tooling that isn't specific to the `els` schema — the kind of helper you'd want in any SQL Server database, not just this one. Currently three repeatable migrations that together provide an idempotent way to set table/column comments:

- `R__01_set_extended_property.sql` — `utils.set_extended_property`, the internal engine procedure. Given `@schema_name`, `@table_name`, an optional `@column_name`, and `@comment`, it checks the table (and column, if given) actually exists, checks whether an `MS_Description` extended property is already set on that exact target, and calls `sp_addextendedproperty` or `sp_updateextendedproperty` accordingly. Not meant to be called directly.
- `R__02_set_table_comment.sql` — `utils.set_table_comment(@schema_name, @table_name, @comment)`, a thin wrapper over the engine procedure with no column parameter.
- `R__03_set_column_comment.sql` — `utils.set_column_comment(@schema_name, @table_name, @column_name, @comment)`, the column-level counterpart.

```sql
EXEC utils.set_table_comment  @schema_name = 'els', @table_name = 'course', @comment = 'A single offered course.';
EXEC utils.set_column_comment @schema_name = 'els', @table_name = 'course', @column_name = 'id', @comment = 'Surrogate key.';

-- Safe to run again with the same or different text — it updates in place rather than erroring
-- on an extended property that's already set.
EXEC utils.set_table_comment  @schema_name = 'els', @table_name = 'course', @comment = 'An offered course.';
```

The `utils` schema itself has no explicit `CREATE SCHEMA` migration — like `els`, it relies on Flyway's `createSchemas` setting, which defaults to `true` (Flyway creates any schema listed in `-schemas` that doesn't already exist before running migrations against it).

The numeric prefixes (`01`/`02`/`03`) are a hint for humans reading the folder, not a functional requirement — SQL Server resolves a procedure body's object references at execution time ("deferred name resolution"), so `set_table_comment` could technically be created before `set_extended_property` exists and it would still work, as long as both exist by the time either is actually called. Flyway runs repeatable migrations in alphabetical order of the description anyway, so the numbers just happen to make dependency order match read order too.

### `config`

Holds exactly one file in the repo, `config.template.json` — the shape every real config must follow. Real config files (e.g. `config.json`, `config.local.json`) are created locally by copying the template and filling in real values, and `config/.gitignore` makes sure they can never be committed by accident.

JSON was chosen over YAML/TOML/INI because both PowerShell (`ConvertFrom-Json`/`ConvertTo-Json`) and Python (`json`) read and write it natively, with no extra dependency — useful here since this repo intentionally mixes scripting languages across components.

`flyway.schemas` is a dictionary keyed by schema name, not a single schema/path pair — each key is both the SQL Server schema name and the lookup key `Invoke-ElsMigration.ps1`'s `-Schema` parameter uses, with a `migrationsPath` telling it where that schema's migrations live:

```json
"flyway": {
  "schemas": {
    "utils": { "migrationsPath": "../migrations/utils" },
    "els": { "migrationsPath": "../migrations/els" }
  }
}
```

To set up a local config:

```powershell
Copy-Item config/config.template.json config/config.json
# then edit config/config.json with real server, database, and credentials
```

### `scripts`

`Invoke-ElsMigration.ps1` is a thin wrapper: given `-Schema`, it looks up that schema's entry in `config/config.json` (or a path you point it at), builds the SQL Server JDBC URL and Flyway command-line arguments from it, and calls `flyway` scoped to just that one schema. It never hardcodes or stores credentials itself. PowerShell was chosen for this one as the idiomatic tool for Windows + SQL Server ops scripting; a Python equivalent may follow later as a deliberate redundant twin, per this repo's convention of comparing approaches across languages.

Flyway is run one schema at a time on purpose, not all schemas together: each run gets its own `flyway_schema_history` tracking table inside the schema it targeted, so `-Schema utils` and `-Schema els` are genuinely independent histories with independent cadences — re-run `utils` only when something under `migrations/utils` actually changes, and run `els` as often as you like.

```powershell
# Requires the Flyway CLI on PATH — see the project docs for install/config instructions.
./scripts/Invoke-ElsMigration.ps1 -Schema els                          # flyway migrate against "els" (default command)
./scripts/Invoke-ElsMigration.ps1 -Schema els -FlywayCommand info       # inspect without changing anything
./scripts/Invoke-ElsMigration.ps1 -Schema utils                        # migrate "utils" — only needed when its migrations change
./scripts/Invoke-ElsMigration.ps1 -Schema els -ConfigPath ./config/config.local.json
```

`-Schema` is mandatory — there's no default — so a run always states which schema it targets rather than risking an accidental run against the wrong one.

`scripts/generate-full-schema/` is a Python tool: it reads `els-data-model`'s entity definitions, validates them against its JSON Schema, and generates a T-SQL script that builds the `els` schema from scratch, writing it to `full_db_model/wip/els_full_schema.sql`. Schema only — it doesn't touch seed data. Its output is guaranteed deterministic: regenerating from an unchanged model produces a byte-identical file, and adding a new entity or column never reorders statements that already existed (entities are sorted by name, and a sort's relative ordering of two existing items can never change just because a third was added). See [its own README](scripts/generate-full-schema/README.md) for usage and the details behind that guarantee.

```bash
cd scripts/generate-full-schema
pip install -r requirements.txt
python generate_full_schema.py          # writes full_db_model/wip/els_full_schema.sql
python generate_full_schema.py --check  # exit non-zero if the model and the file have drifted apart
```

`scripts/generate-synthetic-data/` is a separate Python tool for a different job: rather than deriving anything from `els-data-model`, it runs a folder of hand-written `.sql` files against a real database connection, in filename order, substituting three parameters (`--campus-code`, `--name`, `--complexity`) as `{campus_code}`/`{name}`/`{complexity}` placeholders into each file's text first. It stops at the first statement that fails, reporting the file name, the line number, and the database's own error text, and does no transaction management of its own — see [its own README](scripts/generate-synthetic-data/README.md) for the full placeholder/statement-splitting rules and the consequences of that no-rollback choice.

```bash
cd scripts/generate-synthetic-data
pip install -r requirements.txt
python generate_synthetic_data.py --campus-code MAIN2 --name "Second Main Campus" --complexity 100
```

## Schema change workflow

`full_db_model/wip` and `full_db_model/current` only earn their keep together: `wip` is always "what the model currently says the schema should be," `current` is always "what's actually deployed," and the gap between the two is exactly what a schema change needs to cover. The process for turning a model change into a deployed schema change is:

1. Run `python generate_full_schema.py` to regenerate `wip/els_full_schema.sql` from the current state of `els-data-model`.
2. Diff `wip/els_full_schema.sql` against `current/els_full_schema.sql` (a plain text diff) to see exactly what changed.
3. Write a new versioned migration under `migrations/els/` (`V<n>__<description>.sql`) that produces that change. Some of it can be copied straight out of `wip` — a brand-new `CREATE TABLE` for a new entity, say — but anything touching an existing table has to be translated by hand into `ALTER TABLE ...` statements, since a live table with data in it can't just be dropped and recreated the way `wip` regenerates it from scratch. The generator does not do this translation; that step is entirely manual.
4. Deploy the new migration (`Invoke-ElsMigration.ps1 -Schema els`) against a real database, fix whatever doesn't work, and repeat steps 3–4 until it deploys cleanly and the schema it produces is validated.
5. Once validated, copy `wip/els_full_schema.sql` over `current/els_full_schema.sql`, replacing the previous snapshot. `current` now reflects the newly deployed state and is ready to be diffed against for the next change.

`generate-full-schema`'s whole role in this workflow is step 1: producing the two files there are to compare. It has no opinion about how a diff should become a migration, and it never will — see [`CLAUDE.md`](CLAUDE.md#out-of-scope-here) for why that stays a manual step rather than something worth automating into the generator.

## Status

Folder structure and tooling scaffolded. `utils` schema has its first real migrations (idempotent table/column comment procedures, see above). `els` schema still has no real migrations yet beyond the placeholder. `scripts/generate-synthetic-data/` exists with one placeholder/example `.sql` file — real data-generation scripts are still to be written. See [`docs/els-database.md`](../docs/els-database.md) for the broader review/decisions log.

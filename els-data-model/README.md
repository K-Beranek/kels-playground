# eLearning System — Data Model (`els-data-model`)

Canonical definition of the fictional eLearning System's data model: the entities that exist, their attributes and constraints, an entity-relationship diagram, and starter data. Other components (a future SQL DDL generator, ETL pipelines, APIs, ...) are expected to treat this component as the source of truth for the domain shape rather than each inventing their own.

## Contents

```
els-data-model/
├── diagrams/erd.md              Entity-relationship diagram (Mermaid)
├── model/
│   ├── schema/model.schema.json JSON Schema that validates every file in entities/
│   └── entities/*.json          One file per entity: columns, types, keys, constraints
└── data/*.json                  One file per entity: seed data as a JSON array of records
```

## Entities

### Campus

A physical or virtual location where courses are offered.

| Column | Type | Nullable | Key |
|---|---|---|---|
| id | integer | no | primary key, identity |
| name | string(200) | no | |
| description | text | yes | |

### Course

A course offered at a specific campus. `id` is a database-generated (`identity`) surrogate key, unique across the whole system, not just within a campus. `campus_id` is a plain foreign key, not part of the primary key. `course_number` is a separate, human-readable code — unique *within a campus*, not system-wide, so the same code can be reused at a different campus (e.g. two campuses can each have their own `"CS101"`).

| Column | Type | Nullable | Key |
|---|---|---|---|
| campus_id | integer | no | foreign key → Campus.id |
| id | integer | no | primary key, identity |
| name | string(200) | no | |
| course_number | string(50) | no | unique with campus_id |
| description | text | yes | |

See [`diagrams/erd.md`](diagrams/erd.md) for the diagram.

## Machine-readable model format

The brief was: describe the model in a machine-readable format that a later component can parse to generate SQL DDL. A few options exist in the wild:

- **DBML** (Database Markup Language, the format behind dbdiagram.io) is a real, widely-used format for exactly this, and already has libraries (`@dbml/core`, `dbml2sql`) that turn it straight into DDL for several dialects. Using it would mean the future "generate DDL" component is mostly gluing an existing library together — quick, but not much of a learning exercise in parsing/codegen.
- **JSON Schema** is the standard way to describe the *shape* of JSON data, but it has no native vocabulary for relational concepts like composite primary keys or foreign keys — modeling those would mean bolting on non-standard custom keywords, which defeats the point of using a standard.
- A **small custom JSON format**, purpose-built for this domain (columns, abstract types, primary/foreign keys, uniqueness), gives full control and keeps the future DDL-generation component a genuine exercise in reading a schema and emitting SQL.

This component uses the third option — a custom format under `model/entities/*.json` — but borrows the *right tool from option two*: `model/schema/model.schema.json` is a real JSON Schema (2020-12) that validates the structure of every entity file. So the format itself is bespoke and fit for purpose, but its correctness is checked with a standard, well-known tool rather than ad hoc code. Any editor/IDE with JSON Schema support (VS Code included) will give inline validation and autocomplete on the entity files for free by pointing `$schema` at that file, or it can be validated on demand with any JSON Schema validator (e.g. Python's `jsonschema`, or `ajv` on Node).

Types in the entity files are **abstract** (`integer`, `decimal`, `string`, `text`, `boolean`, `date`, `datetime`) rather than SQL types — mapping each one to a concrete column type (e.g. Snowflake `NUMBER` vs. SQL Server `INT` vs. Postgres `integer`) is deliberately left to whichever component generates DDL for a specific target, since that mapping differs per dialect.

## Conventions

- Entity names: `PascalCase`, singular (`Campus`, `Course`).
- Table and column names: `snake_case`, singular table names.
- For a composite primary key, the order of `primaryKey: true` columns in the `columns` array would be the key's column order — the format supports this, though no current entity needs it (both `Campus` and `Course` now use a single-column identity key).
- A column marked `"identity": true` is a database-generated surrogate key (SQL Server `IDENTITY`). It must also be `"nullable": false` — the JSON Schema enforces this combination directly (see `model.schema.json`'s column `if`/`then` rule), and `els-database`'s schema generator checks it again before rendering DDL, so both layers catch a mistake here, not just one.
- `"unique": true` gives a column its own standalone uniqueness constraint. `"uniqueWith": ["other_column", ...]` instead makes it part of a *composite* constraint together with the named sibling column(s) — e.g. `Course.course_number` has `"uniqueWith": ["campus_id"]`, meaning the pair `(campus_id, course_number)` must be unique, not `course_number` alone. The two are mutually exclusive on the same column (the JSON Schema rejects setting both); `uniqueWith`'s column-name references are checked for typos/self-reference by `els-database`'s generator instead, since that kind of cross-reference check isn't practical to express in JSON Schema alone.
- Each entity/column may carry an optional `"comment"` field — a human-readable note about what it represents. This is metadata about the definition, distinct from an actual column that happens to be *named* `description` (both `Campus` and `Course` have one) — don't confuse the two.
- Seed data files are plain JSON arrays of objects, one object per row, using the same column names as the corresponding entity file.

## Extending the model

To add a new entity: create `model/entities/<entity>.json` following the existing files (it will validate against `model/schema/model.schema.json`), create a matching `data/<entity>.json` with a few starter rows, and add it to the diagram in `diagrams/erd.md` and the table above.

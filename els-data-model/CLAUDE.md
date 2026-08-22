# Notes for working in this component

Purpose: this component *is* the schema — there's no application code here, just entity definitions, seed data, and a diagram. See the repo root `CLAUDE.md` for conventions that apply repo-wide.

## Where things live

- `model/entities/*.json` — one file per entity, validated by `model/schema/model.schema.json` (JSON Schema draft 2020-12).
- `data/*.json` — seed data per entity, plain JSON array of row objects, column names matching the entity file.
- `diagrams/erd.md` — Mermaid `erDiagram`, kept in sync by hand with `model/entities/*.json`.

## Adding or changing an entity

1. Add/edit `model/entities/<entity>.json`. Keep it valid against `model/schema/model.schema.json` — for composite primary keys, the order of `primaryKey: true` columns in the array is the key's column order. A column with `"identity": true` must also have `"nullable": false`; the schema enforces this itself. For a composite *unique* constraint (as opposed to a composite primary key), use `"uniqueWith": ["other_column"]` on one column rather than `"unique": true` — the schema rejects setting both on the same column, and `els-database`'s generator will error clearly if `uniqueWith` names a column that doesn't exist on the entity.
2. Add/edit `data/<entity>.json` with a few plausible, fully synthetic rows (see repo root `CLAUDE.md` — no real PII, ever).
3. Update `diagrams/erd.md` and the entity table in `README.md` to match.

There is currently no automated validation script wired up (no CI yet for this component) — changes are checked by hand against the JSON Schema. If a validation script or CI workflow gets added later, document it here.

## Out of scope here

Generating actual SQL DDL from these definitions is a separate, not-yet-built component. This component only needs to stay a faithful, valid source of truth — it should not grow DDL-generation logic itself.

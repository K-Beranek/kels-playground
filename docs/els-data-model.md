# Review: eLearning System Data Model (`els-data-model`)

## What it is

The foundation component: entity definitions (Campus, Course), a Mermaid ER diagram, a machine-readable schema per entity, and synthetic seed data. Nothing here executes — it's a source of truth other components read.

## Key decisions

- **Custom JSON format for entities, not DBML.** DBML already has libraries that turn it into DDL directly, which would make the eventual DDL-generation component trivial rather than a real exercise. A small purpose-built format keeps that future work meaningful.
- **JSON Schema used for validation, not for the model itself.** JSON Schema has no native concept of primary/foreign keys, so it wasn't a good fit as the *model* format — but it's the right tool to validate the custom format's structure, so `model/schema/model.schema.json` fills that role.
- **Abstract, dialect-independent types.** Column types (`integer`, `string`, ...) intentionally don't map to any specific database's type system. That mapping is future work for whatever component generates DDL for a specific target (e.g. Snowflake vs. SQL Server).
- **Single-column identity primary keys, not composite.** `Course` originally used a composite key (`campus_id`, `id`) to exercise that case deliberately; it was later changed to a single `id` identity column (database-generated, unique system-wide), with `campus_id` demoted to a plain foreign key. The format still supports composite keys (order of `primaryKey: true` columns in the array = key order) — it's just not exercised by either current entity anymore.
- **`identity` is schema-enforced alongside `nullable`.** A column can't be `identity: true` and `nullable: true` at once (SQL Server wouldn't allow it) — the JSON Schema itself rejects that combination via an `if`/`then` rule, and `els-database`'s generator checks it again before emitting DDL, so a mistake here is caught at two independent layers.
- **`description` renamed to `comment`** for the entity/column-level documentation field, to avoid ambiguity with the fact that both entities also have an actual column literally *named* `description`. The rename only touched that metadata key — the real `description` column, and all seed data, were untouched.
- **Composite uniqueness via `uniqueWith`, kept separate from the existing `unique` boolean.** When `Course.course_number` needed to be unique per-campus rather than system-wide, the option considered first was overloading `unique` itself (boolean → string, presence/value both carrying meaning) — rejected in favor of a second, purpose-specific field (`uniqueWith: ["campus_id"]`) so `unique`'s meaning never depends on its value's content, and every existing standalone-unique column needed no migration. The two are mutually exclusive on one column, enforced structurally by the JSON Schema (same `if`/`then` pattern as `identity`/`nullable`); a `uniqueWith` entry naming a column that doesn't exist on the entity is a check the JSON Schema can't practically express (it would need to cross-reference sibling array entries by name), so that one lives only in `els-database`'s generator.

## How other components should use this

- Treat `model/entities/*.json` as read-only input, not something to fork or reinterpret. If a component needs an entity that doesn't exist yet, add it here first.
- A DDL-generation component (not yet built) is expected to read `model/entities/*.json` and emit `CREATE TABLE` statements per target dialect, resolving the abstract types and composite keys described above.
- `data/*.json` is meant for seeding — loading it into a real database once one exists, for other components (ETL, reporting, etc.) to have something to work against.

## Deployment

Nothing to deploy — this component is static definition files, consumed by other components rather than run on its own.

## Status

In progress. Two entities defined (Campus, Course), both now using single-column identity primary keys. No automated validation/CI wired up yet.

Note on a ripple effect from the `Course` primary-key change: `id` was previously unique only *within* a campus (part of the composite key), so the seed data reused small id values (`1`) across different campuses. With `id` now the sole, globally-unique primary key, those seed rows were renumbered (`1`–`4`) to stay valid — `campus_id` values were left unchanged. `els-database`'s schema generator was re-run and confirmed to still produce deterministic, correctly-constrained output against the updated model.

A related but separate change: `course_number` moved from a standalone system-wide unique constraint to a composite one with `campus_id` (`uniqueWith`), meaning the same course number is now allowed to exist at two different campuses. The existing seed data needed no changes — all four rows already had distinct `course_number` values, which trivially satisfies the new, looser constraint too.

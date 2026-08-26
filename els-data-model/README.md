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
| uuid | string(36) | no | unique |
| code | string(20) | no | unique |
| name | string(200) | no | |
| description | text | yes | |

`uuid` is a stable external identifier — meant for anything outside the database (an API response, an integration with another system) that shouldn't expose or depend on the internal, auto-incrementing `id`. It's modeled as a plain `string`, not a dedicated UUID/GUID type — the abstract type system here doesn't have one yet (see "Extending the model" if that's ever worth adding), and SQL Server's native equivalent (`UNIQUEIDENTIFIER`) is a possible future refinement rather than something assumed here.

`code` is a third, distinct kind of identifier, sitting between the other two: `id` is stable but not human-friendly (and not meant to be typed or remembered), `uuid` is stable and external-facing but far too long to remember or type, and `code` is a short, human-memorable static string (e.g. `"MAIN"`) — the kind of thing someone might actually type into a URL or say out loud. It's a standalone `unique: true` column, not `uniqueWith` — unlike `Course.course_number` or `StudyProgram.code`, `Campus` has no parent entity to scope uniqueness within, so it's unique system-wide by construction.

### Course

A course offered at a specific campus. `id` is a database-generated (`identity`) surrogate key, unique across the whole system, not just within a campus. `campus_id` is a plain foreign key, not part of the primary key. `course_number` is a separate, human-readable code — unique *within a campus*, not system-wide, so the same code can be reused at a different campus (e.g. two campuses can each have their own `"CS101"`).

| Column | Type | Nullable | Key |
|---|---|---|---|
| campus_id | integer | no | foreign key → Campus.id |
| course_type | string(30) | no | foreign key → CourseType.code |
| id | integer | no | primary key, identity |
| name | string(200) | no | |
| course_number | string(50) | no | unique with campus_id |
| description | text | yes | |

`course_type` is a foreign key to `CourseType.code` — the natural key, not a surrogate id, since `CourseType` doesn't have one (see below). This is a normal-looking FK on the referencing side (`REFERENCES els.course_type (code)`); what's unusual is only on the *referenced* side, where the target column happens to be a string primary key instead of an integer identity.

### CourseType

A lookup table of allowed course delivery types (`In Person`, `Online`, `Hybrid`, `N/A`) — the standard pattern for a limited, GUI-facing list of values: a small reference table with a stable machine code, a human-readable label, an explicit display order, and an active/inactive flag, rather than a `CHECK` constraint or magic numbers scattered through application code. Referenced by `Course.course_type`, a foreign key to `code`.

| Column | Type | Nullable | Key |
|---|---|---|---|
| code | string(30) | no | primary key |
| display_name | string(100) | no | unique |
| sort_order | integer | no | |
| is_active | boolean | no | |

Unlike `Campus` and `Course`, `CourseType` has no separate surrogate `id` — `code` (`IN_PERSON`, `ONLINE`, `HYBRID`, `NA`) is the primary key directly, since it's already the entity's natural, stable identifier. Adding a surrogate `id` on top would just create a second key nobody uses: application code would reach for the meaningless `id`, humans would reach for `display_name`, and `code` — the one column actually designed to be keyed off — would sit unused. `display_name` stays independently unique as the GUI-facing label, expected to be able to change wording without disturbing `code`. `sort_order` controls presentation order explicitly rather than relying on `code` or alphabetical order (`N/A` sorting after the real options despite alphabetical order putting it first). `is_active` lets a type be retired from new selections without invalidating any existing row that already references it — nothing here does that referencing yet, but the column exists for when it does.

### StudyProgram

A program of study offered at a campus (e.g. a degree or certificate track).

| Column | Type | Nullable | Key |
|---|---|---|---|
| campus_id | integer | no | foreign key → Campus.id |
| id | integer | no | primary key, identity |
| code | string(50) | no | unique with campus_id |
| name | string(200) | no | |
| description | text | yes | |

Same shape as `Course`: `code` is a human-readable program code, unique *within a campus* rather than system-wide, and `id` is the surrogate primary key. `description` uses the unbounded `text` abstract type, the same choice already made for `Campus.description` and `Course.description` — kept consistent for the same free-text "may or may not be present, no realistic length cap" role, rather than introducing a bounded `string` for this one entity.

### SemesterType

A lookup table of allowed semester types (`Winter`, `Summer`), same shape as `CourseType`.

| Column | Type | Nullable | Key |
|---|---|---|---|
| code | string(30) | no | primary key |
| display_name | string(100) | no | unique |
| sort_order | integer | no | |
| is_active | boolean | no | |

### CurriculumType

A lookup table of allowed curriculum types for a course within a term (`Mandatory`, `Optional`), same shape as `CourseType`.

| Column | Type | Nullable | Key |
|---|---|---|---|
| code | string(30) | no | primary key |
| display_name | string(100) | no | unique |
| sort_order | integer | no | |
| is_active | boolean | no | |

### Semester

A specific semester (a semester type within an academic year) at a campus.

| Column | Type | Nullable | Key |
|---|---|---|---|
| campus_id | integer | no | foreign key → Campus.id |
| semester_type | string(30) | no | foreign key → SemesterType.code |
| id | integer | no | primary key, identity |
| academic_year | integer | no | |
| code | string(50) | no | unique with campus_id |

`semester_type` is a foreign key to `SemesterType.code`, the same natural-key FK shape as `Course.course_type` → `CourseType.code`. `code` (e.g. `2026-WIN`) is, again, unique *within a campus*, not system-wide.

### Term

A specific offering of a study program during a semester at a campus — the thing courses actually get scheduled into.

| Column | Type | Nullable | Key |
|---|---|---|---|
| campus_id | integer | no | foreign key → Campus.id, part of composite UK with study_program_id/semester_id |
| study_program_id | integer | no | foreign key → StudyProgram.id, part of composite UK |
| semester_id | integer | no | foreign key → Semester.id, unique with campus_id/study_program_id |
| id | integer | no | primary key, identity |

`campus_id` here is deliberate — see "Campus scoping (`campus_id`)" below for why every campus-scoped entity carries its own copy rather than requiring a join to find out. `Term` has no `code` or `name` of its own; it's identified by the combination of program, semester, and campus, and that combination is now enforced unique (`UNIQUE (campus_id, study_program_id, semester_id)`) — a study program can't have two terms in the same semester at the same campus.

### TermCourse

A course scheduled within a specific term, with a curriculum type (`Mandatory`/`Optional`) for that term.

| Column | Type | Nullable | Key |
|---|---|---|---|
| campus_id | integer | no | foreign key → Campus.id, part of composite UK with term_id/course_id |
| term_id | integer | no | foreign key → Term.id, part of composite UK |
| course_id | integer | no | foreign key → Course.id, unique with campus_id/term_id |
| curriculum_type | string(30) | no | foreign key → CurriculumType.code |
| id | integer | no | primary key, identity |

Same deliberate `campus_id` as `Term` above — see "Campus scoping (`campus_id`)" below. `course_id` is now unique together with `campus_id` and `term_id` (`UNIQUE (campus_id, term_id, course_id)`) — the same course can't be scheduled twice into the same term.

### Person

A person known to the system — may hold one or more course roles (student, instructor, owner) via `CoursePerson`.

| Column | Type | Nullable | Key |
|---|---|---|---|
| campus_id | integer | no | foreign key → Campus.id |
| id | integer | no | primary key, identity |
| uuid | string(36) | no | unique |
| first_name | string(100) | no | |
| last_name | string(100) | no | |

Same `id` + `uuid` shape as `Campus`: `id` is the internal surrogate, `uuid` a stable external identifier, standalone-unique system-wide (no `uniqueWith` — a person isn't scoped to be unique only *within* a campus). Note that `Person` currently has no natural human-facing code (nothing like `Campus.code`); if one is ever needed (e.g. a student ID), it would follow the same "third identifier" reasoning documented under `Campus` above.

### CourseContentType

A lookup table of allowed course content types (`Introduction`, `Lecture`, `Announcement`), same shape as `CourseType`.

| Column | Type | Nullable | Key |
|---|---|---|---|
| code | string(30) | no | primary key |
| display_name | string(100) | no | unique |
| sort_order | integer | no | |
| is_active | boolean | no | |

### CoursePersonRole

A lookup table of allowed roles a person can hold on a course (`Student`, `Instructor`, `Owner`), same shape as `CourseType`.

| Column | Type | Nullable | Key |
|---|---|---|---|
| code | string(30) | no | primary key |
| display_name | string(100) | no | unique |
| sort_order | integer | no | |
| is_active | boolean | no | |

### CourseContent

A piece of content (introduction, lecture, announcement, ...) attached to a course.

| Column | Type | Nullable | Key |
|---|---|---|---|
| campus_id | integer | no | foreign key → Campus.id |
| course_id | integer | no | foreign key → Course.id |
| content_type | string(30) | no | foreign key → CourseContentType.code |
| id | integer | no | primary key, identity |
| ordering_position | integer | no | |
| active | boolean | no | |
| document_text | string(4000) | yes | |

`document_text` is a bounded `string(4000)`, not the unbounded `text` type used for `description` columns elsewhere in this model — 4000 is SQL Server's largest `NVARCHAR` size that isn't `MAX` (`NVARCHAR(MAX)` behaves differently under the hood: it can't be indexed the same way, and some operations on it are slower). This is the model's first column to make that trade-off explicitly rather than defaulting to `text`.

`course_id` was added shortly after this entity was first built without one — confirmed with Karel that a content item does belong to a specific course, matching the more common LMS shape. `content_type` stays a plain foreign key to the lookup table, not part of any composite key — a course can have any number of introduction/lecture/announcement items, with no uniqueness constraint tying `course_id` and `content_type` together.

### CourseTest

A test (quiz/exam) belonging to a course, with a possible and required score.

| Column | Type | Nullable | Key |
|---|---|---|---|
| campus_id | integer | no | foreign key → Campus.id |
| course_id | integer | no | foreign key → Course.id |
| id | integer | no | primary key, identity |
| code | string(50) | no | unique with course_id |
| active | boolean | no | |
| test_questions | string(4000) | yes | |
| possible_score | integer | no | |
| required_score | integer | no | |

`code` is unique *within its course* (`UNIQUE (course_id, code)`) — as specified, scoped by `course_id` alone, not also by `campus_id` the way `Course.course_number` is scoped by `campus_id`. In practice this is almost the same guarantee, since a `Course` only ever belongs to one campus, but note the constraint as written doesn't literally mention `campus_id` — see "Campus scoping" below for the broader point about `campus_id` consistency across a row's other foreign keys not being enforced here anyway. `test_questions` uses the same bounded `string(4000)` trade-off as `CourseContent.document_text`.

### CoursePerson

A person's role (student, instructor, owner) on a course.

| Column | Type | Nullable | Key |
|---|---|---|---|
| campus_id | integer | no | foreign key → Campus.id |
| course_id | integer | no | foreign key → Course.id |
| person_id | integer | no | foreign key → Person.id, unique with campus_id/course_id |
| course_role | string(30) | no | foreign key → CoursePersonRole.code |
| id | integer | no | primary key, identity |

`person_id` is unique together with `campus_id` and `course_id` (`UNIQUE (campus_id, course_id, person_id)`) — the same person can't be assigned twice to the same course. Note this allows the *same* person to hold *different* roles on the *same* course only via separate rows that would collide on this constraint — as specified, a person gets exactly one role per course, not a set of roles. If a person needing multiple simultaneous roles on one course ever comes up, this constraint would need to move to `(campus_id, course_id, person_id, course_role)` instead.

### Submission

A person's attempt at a course test.

| Column | Type | Nullable | Key |
|---|---|---|---|
| campus_id | integer | no | foreign key → Campus.id |
| course_person_id | integer | no | foreign key → CoursePerson.id |
| course_test_id | integer | no | foreign key → CourseTest.id |
| id | integer | no | primary key, identity |
| submitted_time | datetime | no | |
| submission_text | string(4000) | yes | |
| attempt_number | integer | no | unique with campus_id/course_person_id/course_test_id |
| score | integer | no | |

`submitted_time` is the model's first real use of the abstract `datetime` type (added to `model.schema.json` alongside `date` early on, but unused by any entity until now) — it renders as SQL Server `DATETIME2` in the generated schema. `date` (calendar date only, no time-of-day) remains unused so far.

`attempt_number` is unique together with `campus_id`, `course_person_id`, and `course_test_id` — the same attempt number can't be recorded twice for the same course-person/test pair, while still allowing multiple attempts (`1`, `2`, ...) at the same test.

`course_person_id` and `course_test_id` each carry their own `course_id` indirectly (`CoursePerson.course_id` and `CourseTest.course_id`), and those two need to agree — a submission's course-person and course-test should always be for the same course. This is the same shape of gap as the `campus_id` cross-table integrity gap discussed below, just one level further removed (through `CoursePerson`/`CourseTest` rather than directly on `Submission`'s own columns): nothing in this model enforces it. As specified, it's deliberately left unenforced — see the `course_test_id` column's comment in `model/entities/submission.json` for where this is called out in the model itself, and see "Campus scoping" below for the general pattern this follows.

See [`diagrams/erd.md`](diagrams/erd.md) for the diagram.

## Campus scoping (`campus_id`)

Every entity that holds per-campus data (`Course`, `StudyProgram`, `Semester`, `Term`, `TermCourse`, `Person`, `CourseContent`, `CourseTest`, `CoursePerson`, `Submission`) carries its own `campus_id` column, even when that campus is also reachable indirectly through another foreign key already on the same row. `Term.campus_id` is reachable via `study_program_id` → `StudyProgram.campus_id` or `semester_id` → `Semester.campus_id`; `TermCourse.campus_id` is reachable via `term_id` or `course_id`. Keeping a direct copy anyway is a deliberate denormalization, not an oversight: it means any query that needs "which campus does this row belong to" can read it straight off the row, with no join required — useful for row-level filtering/security by campus, which is expected to matter once this model has any real access-control layer on top of it.

The trade-off is an integrity rule this model doesn't currently enforce: when a row has more than one foreign key that each carry their own `campus_id` (e.g. `TermCourse.term_id` and `TermCourse.course_id`, or `Term.study_program_id` and `Term.semester_id`), all of those referenced rows' `campus_id` values need to actually agree with the row's own `campus_id` — a `TermCourse` should never reference a `Term` and a `Course` from two different campuses. Nothing in the JSON entity format, the JSON Schema that validates it, or `els-database`'s generator can express or check this today; it's a genuine cross-table consistency constraint, not a single-table one. In a production system this would need real enforcement — a `CHECK` constraint isn't expressive enough for a cross-table rule like this, so it would take a trigger, or application/service-layer validation before writes. For now this component's seed data was built and hand-verified to be consistent, but that consistency is a manual discipline, not something the system guarantees — worth remembering before assuming any future seed data or generated data is automatically safe here.

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

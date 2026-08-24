# Entity-Relationship Diagram

Rendered with [Mermaid](https://mermaid.js.org/), which GitHub renders natively inside Markdown — no extra tooling needed to view it.

```mermaid
erDiagram
    CAMPUS ||--o{ COURSE : offers
    COURSE_TYPE ||--o{ COURSE : categorizes
    CAMPUS ||--o{ STUDY_PROGRAM : offers
    CAMPUS ||--o{ SEMESTER : has
    SEMESTER_TYPE ||--o{ SEMESTER : categorizes
    CAMPUS ||--o{ TERM : has
    STUDY_PROGRAM ||--o{ TERM : "offered as"
    SEMESTER ||--o{ TERM : "runs in"
    CAMPUS ||--o{ TERM_COURSE : has
    TERM ||--o{ TERM_COURSE : schedules
    COURSE ||--o{ TERM_COURSE : "scheduled as"
    CURRICULUM_TYPE ||--o{ TERM_COURSE : categorizes
    CAMPUS ||--o{ PERSON : has
    CAMPUS ||--o{ COURSE_CONTENT : has
    COURSE ||--o{ COURSE_CONTENT : has
    COURSE_CONTENT_TYPE ||--o{ COURSE_CONTENT : categorizes
    CAMPUS ||--o{ COURSE_TEST : has
    COURSE ||--o{ COURSE_TEST : has
    CAMPUS ||--o{ COURSE_PERSON : has
    COURSE ||--o{ COURSE_PERSON : has
    PERSON ||--o{ COURSE_PERSON : holds
    COURSE_PERSON_ROLE ||--o{ COURSE_PERSON : categorizes
    CAMPUS ||--o{ SUBMISSION : has
    COURSE_PERSON ||--o{ SUBMISSION : makes
    COURSE_TEST ||--o{ SUBMISSION : "attempted via"

    CAMPUS {
        int id PK "identity"
        string uuid UK
        string code UK
        string name
        string description
    }

    COURSE {
        int campus_id FK "part of composite UK with course_number"
        string course_type FK
        int id PK "identity"
        string name
        string course_number UK "composite with campus_id"
        string description
    }

    COURSE_TYPE {
        string code PK
        string display_name UK
        int sort_order
        boolean is_active
    }

    STUDY_PROGRAM {
        int campus_id FK "part of composite UK with code"
        int id PK "identity"
        string code UK "composite with campus_id"
        string name
        string description
    }

    SEMESTER_TYPE {
        string code PK
        string display_name UK
        int sort_order
        boolean is_active
    }

    SEMESTER {
        int campus_id FK "part of composite UK with code"
        string semester_type FK
        int id PK "identity"
        int academic_year
        string code UK "composite with campus_id"
    }

    TERM {
        int campus_id FK "deliberate denormalization; part of composite UK with study_program_id/semester_id"
        int study_program_id FK "part of composite UK"
        int semester_id FK UK "composite with campus_id/study_program_id"
        int id PK "identity"
    }

    CURRICULUM_TYPE {
        string code PK
        string display_name UK
        int sort_order
        boolean is_active
    }

    TERM_COURSE {
        int campus_id FK "deliberate denormalization; part of composite UK with term_id/course_id"
        int term_id FK "part of composite UK"
        int course_id FK UK "composite with campus_id/term_id"
        string curriculum_type FK
        int id PK "identity"
    }

    PERSON {
        int campus_id FK
        int id PK "identity"
        string uuid UK
        string first_name
        string last_name
    }

    COURSE_CONTENT_TYPE {
        string code PK
        string display_name UK
        int sort_order
        boolean is_active
    }

    COURSE_CONTENT {
        int campus_id FK
        int course_id FK
        string content_type FK
        int id PK "identity"
        int ordering_position
        boolean active
        string document_text "bounded string(4000), not text"
    }

    COURSE_TEST {
        int campus_id FK "deliberate denormalization"
        int course_id FK "part of composite UK"
        int id PK "identity"
        string code UK "composite with course_id only, not campus_id"
        boolean active
        string test_questions "bounded string(4000), not text"
        int possible_score
        int required_score
    }

    COURSE_PERSON_ROLE {
        string code PK
        string display_name UK
        int sort_order
        boolean is_active
    }

    COURSE_PERSON {
        int campus_id FK "deliberate denormalization; part of composite UK with course_id/person_id"
        int course_id FK "part of composite UK"
        int person_id FK UK "composite with campus_id/course_id"
        string course_role FK
        int id PK "identity"
    }

    SUBMISSION {
        int campus_id FK "deliberate denormalization; part of composite UK"
        int course_person_id FK "part of composite UK; course_id must match course_test_id's, unenforced"
        int course_test_id FK "part of composite UK"
        int id PK "identity"
        string submission_text "bounded string(4000), not text"
        int attempt_number UK "composite with campus_id/course_person_id/course_test_id"
        int score
    }
```

`PK` marks primary-key columns, `FK` marks a foreign key, `UK` marks a unique constraint, and the quoted note (Mermaid supports an optional comment per attribute) adds detail — `"identity"` flags a database-generated `IDENTITY` column, and the notes on `campus_id`/`course_number` call out that their `UK` is a single *composite* constraint spanning both columns, not two independent ones. Both `CAMPUS.id` and `COURSE.id` are single-column identity primary keys, unique across the whole system — `COURSE.campus_id` is a plain foreign key, not part of the primary key. `course_number` is a human-readable code that only needs to be unique *within* a campus (`UNIQUE (campus_id, course_number)`), so the same code can be reused at a different campus. `CAMPUS.uuid` is a separate, externally-facing stable identifier alongside the internal `id`, and `CAMPUS.code` is a third identifier again: short and human-memorable (unlike `uuid`) and static (unlike `id`), unique system-wide since `Campus` has no parent entity to scope it within — a standalone `UK`, not a composite one like `course_number`'s.

`COURSE_TYPE` is a lookup table referenced by `COURSE.course_type`, a foreign key to `code` rather than to a surrogate id — `COURSE_TYPE` doesn't have one. It exists as a reusable list of allowed course delivery types (`code`/`display_name` pairs, ordered by `sort_order`, toggled via `is_active`). `code` is the primary key directly, since it's already the table's natural, stable identifier — a surrogate key alongside it would go unused (application code would key off `id` instead of `code`, defeating the point of having a stable code at all). The foreign key pointing at it looks and behaves like any other FK; what differs is only that its target is a string natural key instead of an integer identity column. `SEMESTER_TYPE` and `CURRICULUM_TYPE` are two more lookup tables of the same shape, referenced the same way — by `SEMESTER.semester_type` and `TERM_COURSE.curriculum_type` respectively.

`STUDY_PROGRAM` is a program of study at a campus, following the same "campus-scoped code" shape as `COURSE`: `code` is unique *within* a campus (`UNIQUE (campus_id, code)`), not system-wide, and `id` is the surrogate primary key.

`SEMESTER` is a specific semester (a `SEMESTER_TYPE` within an `academic_year`) at a campus, again with a campus-scoped `code`.

`TERM` ties a `STUDY_PROGRAM` to a `SEMESTER` at a `CAMPUS` — it's the concrete offering courses actually get scheduled into. Its three foreign keys are jointly unique (`UNIQUE (campus_id, study_program_id, semester_id)`): a study program can't have two terms in the same semester at the same campus. `TERM_COURSE` follows the same pattern one level down — it schedules a `COURSE` into a `TERM` with a `CURRICULUM_TYPE` (`Mandatory`/`Optional`), and is likewise unique on `(campus_id, term_id, course_id)`: the same course can't be scheduled twice into the same term.

Every campus-scoped entity here (`COURSE`, `STUDY_PROGRAM`, `SEMESTER`, `TERM`, `TERM_COURSE`, `PERSON`, `COURSE_CONTENT`, `COURSE_TEST`, `COURSE_PERSON`, `SUBMISSION`) carries its own `campus_id`, deliberately, even where the campus is already reachable indirectly through another foreign key on the same row (`TERM.campus_id` via `study_program_id`/`semester_id`; `TERM_COURSE.campus_id` via `term_id`/`course_id`; and so on for the newer entities). The point is to be able to answer "which campus does this row belong to" by reading the row itself, no join required. The cost: nothing in this model — not the JSON Schema, not `els-database`'s generator — can check that a row's `campus_id` actually agrees with the campus of everything else it references (e.g. that a `TERM_COURSE`'s `TERM` and `COURSE` are at the same campus as the `TERM_COURSE` itself, and as each other). That's a genuine cross-table integrity rule, out of scope for now — enforcing it for real would need a trigger or application-layer validation, not just a `CHECK` constraint. Seed data here was built and verified consistent by hand; nothing guarantees it stays that way automatically.

`PERSON` is a person known to the system, campus-scoped like the rest, with the same `id`/`uuid` shape as `CAMPUS` (an internal surrogate plus a stable, standalone-unique external identifier). `COURSE_CONTENT_TYPE` and `COURSE_PERSON_ROLE` are two more lookup tables of exactly `COURSE_TYPE`'s shape. `COURSE_CONTENT` belongs to a `COURSE` (`course_id`, added shortly after the entity was first built without one) and is categorized by `COURSE_CONTENT_TYPE` — no uniqueness constraint ties `course_id` and `content_type` together, so a course can have any number of content items of the same type.

`COURSE_TEST` belongs to a `COURSE`, with `code` unique *within that course* (`UNIQUE (course_id, code)`) — scoped by `course_id` alone, not additionally by `campus_id` the way `COURSE.course_number` is scoped by `campus_id`. `COURSE_PERSON` links a `PERSON` to a `COURSE` with a `COURSE_PERSON_ROLE`, unique on `(campus_id, course_id, person_id)` — one role per person per course. `SUBMISSION` records a `COURSE_PERSON`'s attempt at a `COURSE_TEST`, unique on `(campus_id, course_person_id, course_test_id, attempt_number)` so the same attempt number can't be recorded twice for the same pairing. `SUBMISSION` carries a second, more indirect version of the same kind of unenforced cross-table rule as `campus_id` above: the `COURSE` referenced (indirectly) via `course_person_id` and the `COURSE` referenced (indirectly) via `course_test_id` are expected to always be the same course, but nothing in this model checks that either — deliberately, as specified, and noted directly on the `course_test_id` column's comment in `model/entities/submission.json`.

## Why an ER diagram instead of a UML class diagram

Mermaid supports both `classDiagram` (UML class notation — attributes, methods, associations) and `erDiagram` (entity-relationship notation — tables, keys, cardinality). `erDiagram` was used here because it maps directly onto relational concepts like composite primary keys and foreign keys, which is what this model actually is. If a later component models these entities as application-level classes (an ORM layer, a domain model in C# or Python), a `classDiagram` view showing that object model would be a reasonable and complementary addition at that point — the two notations answer different questions.

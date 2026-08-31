# Karel's eLearning System (fictional)

This repository is a portfolio project: a **fictional** eLearning System, built one component at a time to practice and demonstrate a range of technologies (SQL, Snowflake, AWS, Python, JavaScript, C#, PowerShell, bash, CI/CD, Infrastructure as Code, and more). It is not a real product and none of its data represents real people or institutions.

Some pieces are deliberately implemented more than once, in different technologies, so the trade-offs between approaches can be compared directly (for example, the same transformation written in Python, in C#, and as a database stored procedure).

## Repository layout

Each component lives in its own top-level folder with its own `README.md`, `CLAUDE.md`, and `LICENSE.md`. Cross-component documentation — how components relate to each other, integration notes, and short reviews of each one — lives in [`docs/`](docs/).

## Components

| Component | Folder | Description | Status |
|---|---|---|---|
| eLearning System Data Model | [`els-data-model`](els-data-model/) | Canonical entity definitions, ER diagram, machine-readable schema, and seed data for the fictional domain. | in progress |
| eLearning System Database | [`els-database`](els-database/) | SQL Server database code: Flyway migrations, deployment tooling, and schema-modeling workspace. | in progress |
| eLearning System Transformation | [`els_transform`](els_transform/) | dbt project transforming the raw `els` schema into a dimensional model (dimension/fact tables) for reporting. | in progress |

See [`docs/README.md`](docs/README.md) for more on how components are documented and how they're meant to fit together.

## License

All code and documentation in this repository is licensed under the MIT License unless a specific file states otherwise (for example, if a component ever incorporates third-party data or assets under a different license). See [`LICENSE.md`](LICENSE.md).

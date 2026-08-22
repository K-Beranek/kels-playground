# Repository-wide conventions

This file orients any Claude session (or human) working in this repository. It's a portfolio project: a fictional eLearning System, built one component at a time to practice technologies. See each component's own `CLAUDE.md` for details specific to that component; this file only covers conventions that apply repo-wide.

## Structure

- One top-level folder per component. Each component folder has its own `README.md` (reference documentation: what it is, how to use it), `CLAUDE.md` (notes for future coding sessions: build/test commands, architecture, gotchas), and `LICENSE.md`.
- `docs/` holds cross-component documentation: how components relate, deployment/integration notes, and short reviews of each component. It is not a substitute for a component's own README.

## License

Default license is **MIT**, applied repo-wide to both code and documentation. If a component incorporates something that cannot be MIT-licensed (e.g. a third-party dataset with its own license), that must be called out explicitly in that component's `README.md` and excluded from the blanket license — flag this to the user rather than assuming.

## Data

All data in this repository — seed data, sample datasets, fixtures — must be synthetic/fictional. Never use real people's names, emails, or other real PII, even as "realistic-looking" placeholder data. Don't import real third-party datasets without first checking their license is compatible.

## CI/CD

Default is **GitHub Actions** for any component that needs a pipeline (it's a public GitHub repo — no infrastructure to run, free minutes, README badges). Jenkins may be used deliberately for a specific component as a dedicated exercise, but it is not the default.

## Secrets

Never commit credentials or secrets. Use a `.env.example` pattern for anything that needs local configuration, and rely on `.gitignore` to keep real `.env` files out of the repo.

## Redundant implementations

When a component is deliberately re-implemented in multiple technologies to compare approaches, each variant's README should say what it's a redundant twin of and note any real trade-offs observed — not just confirm that it works.

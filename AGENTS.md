# Agent instructions

Read this before changing anything in this repository.

## What this is
An Ocelescope module (FastAPI backend + React frontend) for location-based object-centric process mining.
The concept (definitions, levels, flags, page contents) is defined by Nina Graves outside this repo; the implementation follows it.

## Working rules
- Conceptualisation is Nina's: never add, change or reinterpret a content element (anything shown to the user: key numbers, charts, tables, flags, derived values) without her agreement. Propose first, build after approval.
- Work iteratively: one agreed step at a time, each reviewed by Nina before the next.
- Every content element is documented in `docs/pages/` or `docs/resources/` (see `docs/README.md` for what each entry must contain). Code and docs change together.
- General tool functionality (caching, storage, plumbing, build) is documented more briefly in `docs/hosting/`.
- Every Python function and every exported TypeScript function/component has a docstring.
- Code style: modular and generic; content logic in polars (lazy) on the DuckDB-backed OCEL, never pandas. British English in code, comments and docs.
- Commits and pull requests contain no co-author or tool attribution lines.

## Where to look
- `docs/README.md`: documentation map and documentation rules.
- `docs/hosting/architecture.md`: how backend, frontend and Ocelescope fit together.
- `docs/hosting/running-and-testing.md`: install, run, test, ports.
- `docs/hosting/dependencies.md`: versions and why.

# Dependencies

- Python 3.13 (`.python-version`), managed with uv; Node 24 (`.nvmrc`), pnpm 11 (pinned in `package.json`).
- `ocelescope-backend` and `ocelescope-module-ocel` ≥ 0.10.2 (`pyproject.toml`). The `ocelescope` library brings DuckDB and polars.
- Frontend packages use `catalog:` versions from `@ocelescope/pnpm-plugin-catalog`, so they follow the Ocelescope release.
- `pnpm-workspace.yaml` waits a day before installing newly published npm packages, except `@ocelescope/*`.
- Next.js is pinned to 16.4.3 via `overrides` in `pnpm-workspace.yaml`, because the catalog's 16.4.0 has a known security vulnerability. Remove the override once the Ocelescope catalog ships ≥ 16.4.3.

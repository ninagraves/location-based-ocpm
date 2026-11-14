# Dependencies

- Python 3.13 (`.python-version`), managed with uv; Node 24 (`.nvmrc`), pnpm 11 (pinned in `package.json`).
- `ocelescope-backend` and `ocelescope-module-ocel` ≥ 0.10.2 (`pyproject.toml`). The `ocelescope` library brings DuckDB and polars.
- Frontend packages use `catalog:` versions from `@ocelescope/pnpm-plugin-catalog`, so they follow the Ocelescope release.
- `pnpm-workspace.yaml` waits a day before installing newly published npm packages, except `@ocelescope/*`.
- Next.js is pinned to 16.4.3 via `overrides` in `pnpm-workspace.yaml`, because the catalog's 16.4.0 has a known security vulnerability. Remove the override once the Ocelescope catalog ships ≥ 16.4.3.
- DuckDB is pinned below 2 in the root `pyproject.toml`: ocelescope 0.10.2 uses the lambda syntax DuckDB 2 rejects ("Deprecated lambda arrow"), so reading or uploading any log fails with DuckDB 2. Remove the pin once ocelescope supports DuckDB 2.
- Plotly click events: react-plotly.js 4.1.0 (used by `@r4pm/components`' `ThemedPlot`) loses `onClick` / `onSunburstClick` when React runs effects twice in development, and Plotly only honours the last listener's return value. `components/plots.tsx`, `ThemedPlot`, therefore attaches both handlers itself on every `onInitialized` (and once more right after react-plotly.js adds its own listeners). Remove that once react-plotly.js keeps its handlers.
- `@xyflow/react` (^12.11.3) and `elkjs` (^0.12.0) draw and lay out the directly-follows graph. They are not in the Ocelescope catalog, so `frontend-modules/location-ocpm/package.json` names the versions that `@ocelescope/resources` 0.10.2 requires (its graph viewer uses the same two packages). Align them when Ocelescope moves on. React Flow's stylesheet comes with `@ocelescope/core/styles.css`.

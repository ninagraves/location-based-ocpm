# Dependencies

- Python 3.13 (`.python-version`), managed with uv; Node 24 (`.nvmrc`), pnpm 11 (pinned in `package.json`).
- `ocelescope-backend` and `ocelescope-module-ocel` ≥ 0.13.0 (`pyproject.toml`). The `ocelescope` library brings DuckDB and polars.
- Ocelescope's filters live in a separate module pair since 0.13 (`ocelescope-module-filter` / `@ocelescope/filter`); this instance does not include it, as before. A filter is shown to other modules as a view of the log (see `state-and-caching.md`, log version).
- Frontend packages use `catalog:` versions from `@ocelescope/pnpm-plugin-catalog`, so they follow the Ocelescope release.
- `pnpm-workspace.yaml` waits a day before installing newly published npm packages, except `@ocelescope/*`.
- DuckDB stays below 2: `ocelescope` 0.13 itself requires `duckdb>=1.5.4,<2` (0.10.2 did not, and broke with DuckDB 2's lambda syntax, so the root `pyproject.toml` used to pin it).
- Plotly click events: react-plotly.js 4.1.0 (used by `@r4pm/components`' `ThemedPlot`) loses `onClick` / `onSunburstClick` when React runs effects twice in development, and Plotly only honours the last listener's return value. `components/plots.tsx`, `ThemedPlot`, therefore attaches both handlers itself on every `onInitialized` (and once more right after react-plotly.js adds its own listeners). Remove that once react-plotly.js keeps its handlers.
- `@xyflow/react` and `elkjs` draw and lay out the directly-follows graph. Since Ocelescope 0.13 both are in the Ocelescope catalog (`catalog:` in `frontend-modules/location-ocpm/package.json`; 12.12.0 and 0.12.0 at the time of writing), so they move with Ocelescope. React Flow's stylesheet comes with `@ocelescope/core/styles.css`.
- `jspdf` (Ocelescope catalog) writes the vector PDF of the DFG download (`lib/dfgDownload.ts`, drawing commands only, no plugins). `html-to-image` is no longer used (the DFG download redraws the graph as SVG shapes since 2026-11-23).

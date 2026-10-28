# Architecture

## Parts
- **Ocelescope instance** (this repo's root): the published `ocelescope-backend` host (Python, uv workspace) and the Next.js app in `app/` (pnpm workspace). Both come from the Ocelescope instance template.
- **Backend module** `backend-modules/location-ocpm/`: a FastAPI app. `ocelescope-backend` discovers it through the entry point `ocelescope_backend.modules` in its `pyproject.toml` and serves it under `/modules/locationBasedOcpm/v1`.
  - `module.py`: module class `LocationBasedOcpm` (key, version, app creation).
  - `routes.py`: API routes. Currently only `GET /status`.
  - `derivation/`: location derivation (content; documented in `docs/resources/location-derivation.md`).
- **Frontend module** `frontend-modules/location-ocpm/`: React (Mantine UI), registered in `app/ocelescope.config.ts`.
  - `src/index.ts`: module definition and pages.
  - `src/routes/`: one file per page.
  - `src/components/ModulePage.tsx`: frame of every page (title, shared header, content).
  - `src/components/plots.tsx`: theme-aware Plotly chart (`ThemedPlot`) and the chart toolbar (`plotConfig`: download PNG, download SVG, reset axes).
  - `src/lib/palette.ts`: the only source of colours (categorical, sequential, diverging, UI roles).
  - `src/api/`: typed API client generated from the backend's OpenAPI schema by Orval (`pnpm run build:modules`); not committed.

## Data
- Ocelescope (≥ 0.10.2) keeps each OCEL as a DuckDB connection with flat tables (events, objects, e2o, o2o, …).
- Each table is readable as a DuckDB relation (`.table`), a lazy polars frame (`.pl`) or pandas (`.df`). This module uses `.pl` only.
- Context tables (e.g. user-provided locations) can come from Ocelescope's table resource or from CSV.

## Not built yet
Configuration (shared header), caching of derived results, page state, CSV exports. They will be documented here when built.

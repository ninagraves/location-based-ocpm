# Running and testing

## First setup
```bash
cp .env.example .env
cp app/.env.example app/.env.local
pnpm run sync          # uv sync (Python 3.13, .venv) + pnpm install + build the module
```

## Run
```bash
pnpm run dev           # backend http://localhost:8002 (auto-reload), app http://localhost:3002
```
- Ports: backend 8002 (`dev:backend` in `package.json`, `EXTERNAL_API_BASE_URL` in `app/.env.local`), app 3002 (`dev` in `app/package.json`).
- "Address already in use": an old backend can survive Ctrl+C. Run `lsof -ti :8002 | xargs kill`, check `lsof -nP -i :8002 -i :3002` is empty, start again.
- After changing backend routes or models: `pnpm run build:modules` (regenerates the typed API client; stale TypeScript errors usually mean it was not rerun).

## Test data
The running example log is `data/running_example/running_example.sqlite` (upload it in the app); see `data/running_example/README.md`.

## Tests
```bash
uv run pytest
```
Tests live in `backend-modules/location-ocpm/tests/` and compare the derivation with the running example's expected results (`data/running_example/expected/`). Configured in the root `pyproject.toml` (`[tool.pytest.ini_options]`; pytest is in the `dev` dependency group, installed by `uv sync`).

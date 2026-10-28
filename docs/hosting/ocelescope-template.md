# Ocelescope instance template

A starter monorepo for running your own [Ocelescope](https://www.ocelescope.org)
instance and building your own modules.

It's a single repo with two workspaces:

- **Frontend** (pnpm) — the Next.js app in `app/`, plus your custom frontend
  modules in `frontend-modules/`.
- **Backend** (uv) — the published `ocelescope-backend` host, plus your custom
  Python modules in `backend-modules/`.

Modules are added with scripts that use the
[backend](https://github.com/promi4s/create-ocelescope-backend-module) and
[frontend](https://github.com/promi4s/create-ocelescope-frontend-module) module
templates ([Copier](https://copier.readthedocs.io)).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python ≥ 3.11)
- [pnpm](https://pnpm.io/) ≥ 10 and Node ≥ 20

## Getting started

```bash
cp .env.example .env                 # backend config (optional)
cp app/.env.example app/.env.local   # frontend config (optional)

pnpm run add:module my-module        # create your first module
pnpm run sync                        # install backend + frontend
pnpm run dev                         # run everything
```

The backend runs on <http://localhost:8000>, the frontend on
<http://localhost:3000>.

## Adding modules

```bash
pnpm run add:module <folder>     # backend-modules/<folder> + frontend-modules/<folder>
pnpm run add:backend <folder>    # backend module only
pnpm run add:frontend <folder>   # frontend module only
```

Each script asks for the module's name, description and author (and, for a
frontend module, its npm package name and the backend module to generate a typed
API client for), creates the module and registers it:

- backend modules are added to the root `pyproject.toml`,
- frontend modules are added to `app/package.json`, `app/ocelescope.config.ts`
  and the `paths` in `app/tsconfig.json` (so `pnpm run dev` uses their sources).

Run `pnpm run sync` afterwards. Extra arguments go to `copier copy`, e.g.
`pnpm run add:module ocel-stats --defaults`. To use another template (e.g. a
local checkout), set `OCELESCOPE_BACKEND_TEMPLATE` / `OCELESCOPE_FRONTEND_TEMPLATE`.

Modules remember their answers in `.copier-answers.yml`; to pull in template
changes, commit your work and run `uvx copier update` in the module's folder.

## Dependency versions

Frontend dependencies use `catalog:` versions from
[`@ocelescope/pnpm-plugin-catalog`](https://www.npmjs.com/package/@ocelescope/pnpm-plugin-catalog),
so the app and all modules use the versions of the Ocelescope release they
build against. To move to a new Ocelescope release:

```bash
pnpm add --config @ocelescope/pnpm-plugin-catalog@latest
uv add "ocelescope-backend>=<version>" "ocelescope-module-ocel>=<version>"
```

## Scripts

| Script | What it does |
| --- | --- |
| `pnpm run add:module` / `add:backend` / `add:frontend` | Adds a module (see above). |
| `pnpm run sync` | Full setup: backend then frontend. |
| `pnpm run dev` | Runs the backend and frontend together. |
| `pnpm run dev:modules` | Watch-rebuild local frontend modules while editing them. |
| `pnpm run build:modules` | Builds local frontend modules (regenerates their API clients). |
| `pnpm run docker` | Builds and runs the app (backend + frontend) in Docker. |
| `pnpm run docker:down` | Stops the Docker containers. |

## Docker

```bash
pnpm run docker        # docker compose up --build
pnpm run docker:down   # docker compose down
```

This builds images for the backend and the frontend (including your modules)
and serves the app on <http://localhost:3000> and the backend on
<http://localhost:8000>. Uploaded data lives in Docker volumes; use
`docker compose down -v` to remove it too.

If the build can't download packages (e.g. while a VPN is active, which can
break Docker's default network), build with the host network by creating a
`compose.override.yaml`:

```yaml
services:
  backend:
    build:
      network: host
  frontend:
    build:
      network: host
```

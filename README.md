# Location-based OCPM

An [Ocelescope](https://www.ocelescope.org) module for location-based object-centric process mining in production and logistics.
It derives the locations of handling units from an object-centric event log and analyses them on dedicated pages.

- Backend module: `backend-modules/location-ocpm` (Python package `ocelescope_module_location_based_ocpm`, key `locationBasedOcpm`)
- Frontend module: `frontend-modules/location-ocpm` (`@instance/location-based-ocpm`)
- Documentation: `docs/` (start with `docs/README.md`)

## Run it locally

Requires [uv](https://docs.astral.sh/uv/), Node ≥ 20 and pnpm ≥ 11 (pnpm switches to the version pinned in `package.json`).

```bash
cp .env.example .env                 # once; backend config
cp app/.env.example app/.env.local   # once; frontend config (points to the backend on port 8002)
pnpm run sync                        # install backend + frontend, build the module
pnpm run dev                         # backend on http://localhost:8002, app on http://localhost:3002
```

The module appears in the sidebar as "Location-based OCPM".
Ports 8002/3002 are chosen so that other Ocelescope instances (8000/3000, 8001/3001) can run alongside.
After changing backend routes, run `pnpm run build:modules` to regenerate the typed API client.
More in `docs/hosting/running-and-testing.md`.

This repo started from the Ocelescope instance template; its general documentation is in `docs/hosting/ocelescope-template.md`.

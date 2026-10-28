# Location-based OCPM

Location-based object-centric process mining for production and logistics

An [Ocelescope](https://www.ocelescope.org) frontend module (`@instance/location-based-ocpm`).

- `src/index.ts` — module definition (name `locationBasedOcpm`, label, routes)
- `src/routes/` — pages
- `src/api/` — typed API client for the `locationBasedOcpm` backend module,
  generated from its OpenAPI schema by `pnpm run build` (not committed)

Dependencies use `catalog:` versions from
[`@ocelescope/pnpm-plugin-catalog`](https://www.npmjs.com/package/@ocelescope/pnpm-plugin-catalog),
so the module needs to live in a pnpm workspace with that config dependency
(like an Ocelescope module project).

## Scripts

| Script | What it does |
| --- | --- |
| `pnpm run build` | Regenerates the API client and builds the module into `dist/`. |
| `pnpm run dev` | Rebuilds on changes. |
| `pnpm run typecheck` | Type-checks the module. |

## Updating from the template

This module was generated with [Copier](https://copier.readthedocs.io). To pull
in later changes from the template, commit your work and run in this folder:

```sh
uvx copier update
```

# Documentation

## Map
- `pages/`: one note per page of the module (e.g. `overview.md`); one section per content element.
- `resources/`: one note per special resource used by several pages (e.g. `location-derivation.md`, later HU timelines).
- `hosting/`: general tool functionality (architecture, caching, storage, running, testing, dependencies).

## Content documentation (detailed)
Goal: you can find, understand and edit the code of every content element from its doc.
For every content element (key number, chart, table, flag, derived value) the doc states:
1. **What it shows.**
2. **How it is calculated**, referring to the concept definitions instead of restating them.
3. **Example** on the running example log (`data/running_example/`).
4. **Filtering**: how each page filter affects it, or that it ignores filters.
5. **Settings and defaults**, if any.
6. **Where it lives in the code**: file and function names, their parameters and return values.
7. **How to change it**: which function or parameter to edit for typical changes, and what else then has to adapt (other elements, tests, expected example tables).
8. **Alternatives** that were considered, and why they were not chosen.

A page doc links the resource docs it uses instead of repeating them.

## Hosting documentation (lighter)
Goal: another developer or coding agent can take over without further context.
Covers what exists, where it is, how to run and change it; no per-function detail beyond docstrings.

## Running example
- One running example log, used in the concept and in all docs.
- Every event has its own colour, consistently in all tables.
- Example tables are sorted by handling unit, then time.

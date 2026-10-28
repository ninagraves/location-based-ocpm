# Expected results of the running example

Transcribed from the example tables of `overview/Deriving Locations.md` (section "Deriving Current locations" and the flags table); the tests compare the implementation against these files.
An empty cell is ⊥ (no location).

- `levels.csv`: $loc_0$ to $loc_3$ per hu-event relation (table "Overview of all levels").
- `ploc_1.csv`: $puloc$, $before_{loc_1}$ and $ploc_1$ (table of the "Location before an event" example).
- `agreement.csv`: locatedness, agreement and $eloc$ of selected events at selected levels (table of the "Locatedness" example).
- `flags.csv`: flagged events and handling units at Level 3 (flags table, "Example" column).

If the concept's example changes, update these files by hand from the note, then rerun the tests.

"""Location derivation: from the user's inputs to current and previous locations, agreement and flags.

The concept is defined in `overview/Deriving Locations.md` (outside this repo); the
documentation of this package is `docs/resources/location-derivation.md`.

Data flow:
1. `config` describes the user's choices for each input.
2. `inputs` resolves them on an OCEL into one frame of hu-event relations (`Relations`),
   with reports and blocking errors.
3. `requirements` checks RQ1-RQ3 (blocking).
4. `levels` adds loc_0 to loc_3, before and ploc.
5. `locatedness` gives the locatedness of relations, events and handling units; `agreement` agreement and eloc; `flags` the flags F1-F5.
6. `pipeline.derive` runs all steps.
7. `level_files` saves and loads the mapping of each level (used by the notebooks).
"""

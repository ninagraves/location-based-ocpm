"""Column names of the frames used for visits (`overview/concepts/Visit Mappings.md`).

One place for the names, so a rename is a single edit.
The columns of the relations frame itself (event, hu, time, ...) are in `derivation/columns.py`.
"""

# --- relations frame (one row per hu-event relation) ---
#: High-level location hat-hl((e, hu)) of a relation; null = ⊥.
HIGH_LEVEL = "high_level"
#: AS4 group of the relation's event for ties in time: 0 = movement, 1 = processing operation, 2 = other
#: (`order.tie_rank`).
TIE_RANK = "tie_rank"
#: Position of the relation in otrace(hu), starting at 1 (time, then tie_rank, then event id).
POSITION = "position"
#: Excursion tolerance κ(hat-hl) of the relation's own high-level location (0 for ⊥).
KAPPA = "kappa"
#: Gap g_j before the relation: number of events of the handling unit since its previous relation at the
#: same high-level location (null if there is none).
GAP = "gap"
#: Number of distinct timestamps of the deviating infix before the relation (the events strictly between
#: p_{j-1} and p_j); 0 if it is empty, null for the first relation at a high-level location (DD-V1).
GAP_TIMESTAMPS = "gap_timestamps"
#: Duration of the deviating infix before the relation: time(p_j) - time(p_{j-1} + 1), i.e. from its first
#: event until the first event back at the high-level location; 0 if it is empty, null as above (DD-V1).
GAP_DURATION = "gap_duration"
#: True if the relation starts a new maximal visit at its high-level location.
STARTS_VISIT = "starts_visit"
#: Visit id of the maximal visit at the relation's own high-level location.
VISIT_ID = "visit_id"

# --- visits frame (one row per visit) ---
#: First and last position of the visit's infix otrace(hu)[i:k].
FIRST_POSITION = "first_position"
LAST_POSITION = "last_position"
#: First event e_i (= the entry event e_in) and last event e_k of the visit.
FIRST_EVENT = "first_event"
LAST_EVENT = "last_event"
#: Exit event e_out: the event after the last one (otrace(hu)[k+1]), or e_k if the trace ends there.
EXIT_EVENT = "exit_event"
#: Times of the entry event, the last event and the exit event.
ENTRY_TIME = "entry_time"
LAST_TIME = "last_time"
EXIT_TIME = "exit_time"
#: True if the trace of the handling unit ends with the visit (e_out = e_k; the duration is a lower bound).
ENDS_TRACE = "ends_trace"
#: Visit duration d = time(e_out) - time(e_in).
DURATION = "duration"
#: |σ| = number of relations of the visit, and the number of them at the visit's high-level location.
N_RELATIONS = "n_relations"
N_AT_LOCATION = "n_at_location"
#: True if some relation of the visit is not at its high-level location.
INTERRUPTED = "interrupted"

# --- visit relations frame (one row per visit and relation r ∈ R(ν)) ---
#: High-level location of the visit the row belongs to (the relation's own one is HIGH_LEVEL).
VISIT_HIGH_LEVEL = "visit_high_level"
#: True if the relation is at the visit's high-level location (hat-hl(r) = hl, ⊥ = ⊥ for ⊥ visits).
AT_LOCATION = "at_location"
#: True if the relation's low-level location is a vehicle (loc ∈ V); false for ⊥.
ON_VEHICLE = "on_vehicle"
#: True if the relation is a stop of the visit.
IS_STOP = "is_stop"
#: True if the event is a processing operation (e ∈ P), wherever it happens.
IS_PROCESSING_EVENT = "is_processing_event"
#: True if the relation is a processing operation of the visit (e ∈ P and at the visit's high-level location).
IS_PROCESSING = "is_processing"
#: True if the relation takes the handling unit out of a storage unit (loc_{j-1} ∈ W, loc_j ∉ W).
IS_STORAGE_REMOVAL = "is_storage_removal"

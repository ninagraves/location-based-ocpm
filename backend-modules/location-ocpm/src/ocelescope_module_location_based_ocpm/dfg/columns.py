"""Column names of the frames of the directly-follows graph.

The event columns (event, time, activity, object_type) are those of `derivation/columns.py`.
"""

#: Object id (any object type, not only handling units).
OBJECT = "object"
#: Position of an event in the trace of its object, starting at 1.
POSITION = "position"
#: Variant of an object: the activities of its trace, joined by `VARIANT_SEPARATOR`.
VARIANT = "variant"
#: Separator of the activities in a variant (a character that does not occur in activity names).
VARIANT_SEPARATOR = "␞"
#: Source activity of an arc; null = the start node of the object type.
SOURCE = "source"
#: Target activity of an arc; null = the end node of the object type.
TARGET = "target"
#: Number of times an arc is traversed (an object repeating it counts once per traversal).
COUNT = "count"
#: Number of distinct objects (or events, for activity nodes) counted.
OBJECTS = "objects"
#: Number of distinct events counted.
EVENTS = "events"

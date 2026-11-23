"""API route of the module-wide object type order (documented in `docs/resources/object-type-colours.md`).

Every page colours object types from this one order (`useObjectTypeColours` in the frontend), so that a type,
above all a handling-unit type, has the same colour on every page, chart and download (Nina, 2026-11-23).
The order is cached (small LRU per process), keyed by the cache key of the current derivation.
"""

from collections import OrderedDict

import polars as pl
from fastapi import APIRouter
from ocelescope_backend.app.dependencies import ApiOcel
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.configuration_routes import CurrentDerivation, State
from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.inputs import OCEL_OID, OCEL_TYPE
from ocelescope_module_location_based_ocpm.dfg import columns as d
from ocelescope_module_location_based_ocpm.dfg.graph import type_overview

router = APIRouter()

#: Number of cached orders (one per derivation key).
CACHE_SIZE = 4
_orders: OrderedDict[str, list["ObjectTypeEntry"]] = OrderedDict()


class ObjectTypeEntry(BaseModel):
    """An object type of the log, in the order that fixes its colour.

    Attributes:
        object_type: The object type.
        objects: Its handling units (for a type with handling units), else its objects.
        handling_units: True if the type contains handling units.
    """

    object_type: str
    objects: int
    handling_units: bool


def object_type_order(objects: pl.DataFrame, handling_units: pl.Series) -> list[ObjectTypeEntry]:
    """All object types of the log in colour order: most objects first (handling units for a handling-unit type), then by name.

    The frontend gives the handling-unit types the first colours (in this order) and the other types the next ones
    (in this order), so only the order within each group matters.

    Example: objects pallet p1, p2, p3 (all handling units), box b1, b2 (b1 a handling unit), order o1, o2, o3, o4
    give order (4 objects), pallet (3 handling units), box (1 handling unit); handling-unit types pallet, box.

    Args:
        objects: All objects, columns object and object_type.
        handling_units: The handling units HU.

    Returns:
        list[ObjectTypeEntry]: The object types, as `dfg.graph.type_overview` orders them.
    """
    overview = type_overview(objects, handling_units.to_list())
    return [ObjectTypeEntry(**row) for row in overview.iter_rows(named=True)]


@router.get("/{ocel_id}/object-types", operation_id="getObjectTypes")
def get_object_types(ocel_id: str, ocel: ApiOcel, derivation: CurrentDerivation, state: State) -> list[ObjectTypeEntry]:
    """All object types of the log in colour order (most objects first; handling units for a handling-unit type)."""
    key = state.cache[ocel_id].key
    if key in _orders:
        _orders.move_to_end(key)
        return _orders[key]
    objects = ocel.objects.pl.select(OCEL_OID, OCEL_TYPE).collect().rename({OCEL_OID: d.OBJECT, OCEL_TYPE: c.OBJECT_TYPE})
    order = _orders[key] = object_type_order(objects, derivation.handling_units[c.HU])
    while len(_orders) > CACHE_SIZE:
        _orders.popitem(last=False)
    return order

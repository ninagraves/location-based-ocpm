"""Precomputing the directly-follows graph when a derivation is cached (Nina, 2026-11-16; `dfg_routes.py`)."""

from ocelescope_module_location_based_ocpm import dfg_routes
from ocelescope_module_location_based_ocpm.configuration_routes import ON_DERIVED
from ocelescope_module_location_based_ocpm.dfg.graph import DfgRequest, TypeThresholds
from ocelescope_module_location_based_ocpm.state import CachedDerivation


def test_page_default_request_has_the_key_of_the_precomputed_graph():
    """The page's default request (empty lists, arc settings that only the browser uses) hits the precomputed answer."""
    page_default = DfgRequest(object_types=None, variant_threshold=None, type_thresholds=[], activities={}, excluded_categories=[])
    assert dfg_routes.request_key(page_default) == dfg_routes.request_key(DfgRequest())
    assert dfg_routes.request_key(DfgRequest(arc_threshold=10, stay_connected=False)) == dfg_routes.request_key(DfgRequest())
    own = DfgRequest(type_thresholds=[TypeThresholds(object_type="coil", variant_threshold=50)])
    assert dfg_routes.request_key(own) != dfg_routes.request_key(DfgRequest())


def test_precompute_fills_the_cache(ocel, derivation):
    """After `precompute_default_graph`, the default graph is answered from the cache."""
    assert dfg_routes.precompute_default_graph in ON_DERIVED
    closed = []
    opened = type("Opened", (), {"__getattr__": lambda _, name: getattr(ocel, name), "close": lambda _: closed.append(True)})()
    dfg_routes.precompute_default_graph("log", lambda: opened, CachedDerivation(key="test-key", derivation=derivation))
    assert closed == [True]
    graph = dfg_routes._graphs[("test-key", dfg_routes.request_key(DfgRequest()))]
    assert {t.object_type for t in graph.object_types if t.selected} == {"coil", "slab"}
    assert dfg_routes._graph("test-key", ocel, derivation, DfgRequest()) is graph

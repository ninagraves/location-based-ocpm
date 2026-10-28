"""Module class through which `ocelescope-backend` discovers and serves this module."""

from fastapi import FastAPI
from ocelescope_backend.app.modules import Module, ModuleMeta
from packaging.version import Version

from ocelescope_module_location_based_ocpm.routes import router


class LocationBasedOcpm(Module):
    """The backend module, served under `/modules/locationBasedOcpm/v1` (v = major version of `meta`)."""

    meta = ModuleMeta(key="locationBasedOcpm", version=Version("1.0"))

    def create_app(self) -> FastAPI:
        """Create the FastAPI app holding all routes of the module.

        Returns:
            FastAPI: The module's app; `ocelescope-backend` mounts it.
        """
        app = FastAPI(title="Location-based OCPM", version=str(self.meta.version))
        app.include_router(router)
        return app

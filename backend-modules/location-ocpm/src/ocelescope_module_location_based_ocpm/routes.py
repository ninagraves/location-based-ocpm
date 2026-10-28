"""API routes of the module."""

from importlib.metadata import version

from fastapi import APIRouter
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.configuration_routes import router as configuration_router

router = APIRouter()
router.include_router(configuration_router)


class StatusResponse(BaseModel):
    """Versions of the running backend, shown on the pages to confirm the connection."""

    module_version: str
    ocelescope_version: str


@router.get("/status", operation_id="getStatus", response_model=StatusResponse)
def get_status() -> StatusResponse:
    """Report that the backend module is running, with the installed versions.

    Returns:
        StatusResponse: Version of this module and of the `ocelescope` library.
    """
    return StatusResponse(
        module_version=version("ocelescope-module-location-based-ocpm"),
        ocelescope_version=version("ocelescope"),
    )

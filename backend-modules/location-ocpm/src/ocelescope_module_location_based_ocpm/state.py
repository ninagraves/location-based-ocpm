"""Per-session state of the module: uploaded tables, the applied configuration per log, and the cache.

The state is kept in memory per backend session (`SessionStates`, keyed by the session id), so it
survives page switches and browser reloads, and is lost with "Reset session" or a backend restart.
Ocelescope's own module state (`session.module_states`, since 0.13) only holds JSON-serialisable
pydantic models and serialises them on every update, which does not fit polars frames and cached
derivations.
Documented in docs/hosting/state-and-caching.md.
"""

import hashlib
import io
from collections.abc import Iterable
from dataclasses import dataclass, field

import polars as pl

from ocelescope_module_location_based_ocpm.derivation.config import DerivationConfig
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation



@dataclass
class UploadedTable:
    """A CSV table uploaded in the configuration form, every column read as text.

    Attributes:
        name: File name; the configuration refers to the table by it.
        frame: The table contents.
        digest: Hash of the file contents, part of the cache key.
    """

    name: str
    frame: pl.DataFrame
    digest: str


@dataclass
class CachedDerivation:
    """The derivation of one log under one configuration, log version and set of tables.

    Attributes:
        key: Fingerprint of everything the derivation depends on (see `fingerprint`).
        derivation: The result.
    """

    key: str
    derivation: Derivation


@dataclass
class ModuleState:
    """Everything the module keeps per session.

    Attributes:
        tables: Uploaded tables by file name; uploading a file with the same name replaces it.
        configs: Applied configuration per log id.
        cache: Latest derivation per log id (one entry per log, replaced when its key changes).
    """

    tables: dict[str, UploadedTable] = field(default_factory=dict)
    configs: dict[str, DerivationConfig] = field(default_factory=dict)
    cache: dict[str, CachedDerivation] = field(default_factory=dict)

    def add_table(self, name: str, content: bytes) -> UploadedTable:
        """Read a CSV upload, every column as text, and store it under its file name.

        Args:
            name: File name.
            content: Raw CSV bytes.

        Returns:
            UploadedTable: The stored table.

        Raises:
            polars.exceptions.PolarsError: If the file cannot be read as CSV.
        """
        frame = pl.read_csv(io.BytesIO(content), infer_schema=False)
        table = UploadedTable(name=name, frame=frame, digest=hashlib.sha256(content).hexdigest())
        self.tables[name] = table
        return table

    def frames(self) -> dict[str, pl.DataFrame]:
        """All uploaded tables by name, as the derivation expects them.

        Returns:
            dict[str, pl.DataFrame]: Table contents by file name.
        """
        return {name: table.frame for name, table in self.tables.items()}


def table_names(config: DerivationConfig) -> list[str]:
    """Names of all tables a configuration refers to.

    Args:
        config: The configuration.

    Returns:
        list[str]: Table names, sorted, without duplicates.
    """
    processing = config.processing_operations
    inputs = (
        config.handling_units,
        config.movement_events,
        config.transformation_events,
        config.target_locations,
        config.pickup_locations,
        config.high_level_locations,
        config.vehicles,
        config.storage_units,
        processing.selection if processing is not None else None,
    )
    names = {option.table for option in inputs if option is not None and option.option == "table"}
    return sorted(names | set(config.role_tables()))


def fingerprint(config: DerivationConfig, log_version: str, tables: dict[str, UploadedTable]) -> str:
    """Cache key of a derivation: configuration (incl. level), log version and used tables.

    Args:
        config: The configuration.
        log_version: Anything identifying the current version of the log, e.g. its active
            Ocelescope view (see `configuration_routes.log_version`).
        tables: Uploaded tables by name; only those the configuration refers to are hashed.

    Returns:
        str: A hex digest; equal digests mean the cached derivation can be reused.
    """
    used = [f"{name}:{tables[name].digest if name in tables else '-'}" for name in table_names(config)]
    raw = "|".join([config.model_dump_json(), log_version, *used])
    return hashlib.sha256(raw.encode()).hexdigest()


class SessionStates:
    """The module states of all backend sessions, by session id.

    A state is created on first use. States of sessions the backend no longer knows (after "Reset
    session") are dropped on the next access, so they do not pile up.
    """

    def __init__(self) -> None:
        """Start without any state."""
        self._states: dict[str, ModuleState] = {}

    def get(self, session_id: str, live_ids: Iterable[str] | None = None) -> ModuleState:
        """The state of a session, created on first use.

        Args:
            session_id: Id of the backend session.
            live_ids: Ids of all sessions the backend still knows; states of other sessions are
                dropped. `None` keeps every state.

        Returns:
            ModuleState: The session's state.
        """
        if live_ids is not None:
            keep = set(live_ids) | {session_id}
            for stale in [key for key in self._states if key not in keep]:
                del self._states[stale]
        return self._states.setdefault(session_id, ModuleState())

    def __len__(self) -> int:
        """Number of stored states."""
        return len(self._states)

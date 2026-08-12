"""Shared SQL Server row -> DatabaseInstance mapping.

`fn_BasesDeDatosPorUsuario`, `fn_ObtenerBD`, and `sp_ListarTodasLasBasesDatos`
all return the same row shape (Spanish, snake_case column names, e.g.
`id_bd`, `nombre_bd`, `estado`, `fecha_creacion`, `espacio_maximo_mb`). This
module is the single place that knows those column names, so
`DatabaseService` and `AdminService` never have to agree on the mapping
independently.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.databases.schemas.database_schemas import DatabaseInstance, DatabaseStatus

# `estado` comes back as the Spanish stored-procedure literal, not the
# internal English enum value.
_SPANISH_STATUS: dict[str, DatabaseStatus] = {
    "activa": DatabaseStatus.ACTIVE,
    "pausada": DatabaseStatus.PAUSED,
    "eliminada": DatabaseStatus.DELETED,
}


def normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Lower-case every column name so lookups are case-insensitive."""

    return {str(key).lower(): value for key, value in row.items()}


def pick_first(data: Mapping[str, Any], *keys: str) -> Any:
    """Return the first present, non-None value among `keys`.

    Plain `a or b or c` chains treat `0`/`0.0` as "not found" and skip
    straight to the next fallback, which silently turns a genuine "0 MB
    used" or "0 active connections" into `None`. This checks presence and
    `is not None` instead, so falsy-but-real values survive.
    """

    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def parse_database_status(value: Any) -> DatabaseStatus:
    """Parse a `status`/`estado` column value into `DatabaseStatus`.

    Accepts both the internal English enum literals and the Spanish
    stored-procedure literals (`ACTIVA`, `PAUSADA`, `ELIMINADA`).
    """

    status_value = str(value or "").strip().lower()
    if not status_value:
        return DatabaseStatus.UNKNOWN
    try:
        return DatabaseStatus(status_value)
    except ValueError:
        return _SPANISH_STATUS.get(status_value, DatabaseStatus.UNKNOWN)


def row_to_database_instance(row: Mapping[str, Any]) -> DatabaseInstance:
    """Map a raw SQL Server row into a `DatabaseInstance` DTO."""

    data = normalize_row(row)
    return DatabaseInstance(
        database_id=str(pick_first(data, "database_id", "id_bd", "basedatosid", "id") or ""),
        name=pick_first(data, "name", "nombre_bd", "nombre"),
        status=parse_database_status(pick_first(data, "status", "estado")),
        created_at=pick_first(data, "created_at", "fecha_creacion", "fechacreacion"),
        ttl_expires_at=pick_first(data, "ttl_expires_at", "fecha_expiracion", "fechaexpiracion"),
        storage_limit_mb=pick_first(data, "storage_limit_mb", "espacio_maximo_mb", "limitealmacenamientomb"),
        storage_used_mb=pick_first(data, "storage_used_mb", "espacio_actual_mb", "almacenamientousadomb"),
    )

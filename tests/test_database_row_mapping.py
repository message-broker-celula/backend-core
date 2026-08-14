from datetime import datetime, timezone

from app.databases.row_mapping import parse_database_status, row_to_database_instance
from app.databases.schemas.database_schemas import DatabaseStatus

# Shape actually returned by fn_BasesDeDatosPorUsuario / fn_ObtenerBD in SQL
# Server, confirmed against production: id_bd, nombre_bd, estado (Spanish
# literal), fecha_creacion, fecha_expiracion, espacio_maximo_mb,
# espacio_actual_mb (snake_case, not no-separator guesses).
SQL_SERVER_ROW = {
    "id_bd": "8B20E32F-8B3A-457A-8CC5-13C93CA5423B",
    "nombre_bd": "brayhan_test",
    "motor": "MYSQL",
    "version_motor": "8.4",
    "host": "mysql",
    "puerto": 3306,
    "estado": "ACTIVA",
    "espacio_actual_mb": 0,
    "espacio_maximo_mb": 20,
    "conexiones_maximas": 5,
    "conexiones_actuales": 0,
    "fecha_creacion": "2026-08-11T10:00:00Z",
    "ultima_actividad": "2026-08-11T10:00:00Z",
    "fecha_expiracion": "2026-09-10T10:00:00Z",
    "id_celula": None,
}


def test_row_to_database_instance_maps_real_sql_server_columns() -> None:
    instance = row_to_database_instance(SQL_SERVER_ROW)

    assert instance.database_id == "8B20E32F-8B3A-457A-8CC5-13C93CA5423B"
    assert instance.name == "brayhan_test"
    assert instance.status == DatabaseStatus.ACTIVE
    assert instance.created_at == datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)
    assert instance.ttl_expires_at == datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    assert instance.storage_limit_mb == 20
    assert instance.host == "mysql"
    assert instance.port == 3306
    assert instance.engine == "MYSQL"
    assert instance.last_activity == datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)


def test_row_to_database_instance_keeps_zero_storage_used_instead_of_dropping_it() -> None:
    # espacio_actual_mb=0 is a real, common value (freshly created database)
    # -- it must not be silently swallowed by an `or`-chain fallback.
    instance = row_to_database_instance(SQL_SERVER_ROW)

    assert instance.storage_used_mb == 0


def test_parse_database_status_accepts_spanish_stored_procedure_literals() -> None:
    assert parse_database_status("ACTIVA") == DatabaseStatus.ACTIVE
    assert parse_database_status("PAUSADA") == DatabaseStatus.PAUSED
    assert parse_database_status("ELIMINADA") == DatabaseStatus.DELETED


def test_parse_database_status_accepts_internal_english_literals() -> None:
    assert parse_database_status("active") == DatabaseStatus.ACTIVE


def test_parse_database_status_falls_back_to_unknown() -> None:
    assert parse_database_status(None) == DatabaseStatus.UNKNOWN
    assert parse_database_status("") == DatabaseStatus.UNKNOWN
    assert parse_database_status("something-else") == DatabaseStatus.UNKNOWN

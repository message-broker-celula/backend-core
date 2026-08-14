from app.engines import get_engine_spec


def test_get_engine_spec_returns_mysql_case_insensitive() -> None:
    spec = get_engine_spec("MySQL")

    assert spec is not None
    assert spec.image == "mysql"
    assert spec.internal_port == 3306


def test_get_engine_spec_returns_none_for_unsupported_engine() -> None:
    assert get_engine_spec("oracle") is None


def test_mysql_env_builder_maps_all_fields() -> None:
    spec = get_engine_spec("mysql")

    env = spec.env_builder("app_db", "app_user", "pw", "rootpw")

    assert env == {
        "MYSQL_ROOT_PASSWORD": "rootpw",
        "MYSQL_DATABASE": "app_db",
        "MYSQL_USER": "app_user",
        "MYSQL_PASSWORD": "pw",
    }


def test_get_engine_spec_returns_postgres_case_insensitive() -> None:
    spec = get_engine_spec("Postgres")

    assert spec is not None
    assert spec.image == "postgres"
    assert spec.internal_port == 5432
    assert spec.data_dir == "/var/lib/postgresql/data"


def test_postgres_env_builder_ignores_root_password() -> None:
    spec = get_engine_spec("postgres")

    env = spec.env_builder("app_db", "app_user", "pw", "rootpw")

    assert env == {
        "POSTGRES_USER": "app_user",
        "POSTGRES_PASSWORD": "pw",
        "POSTGRES_DB": "app_db",
    }


def test_postgres_footprint_is_capped_lighter_than_mysql() -> None:
    # The whole point of tuning both engines is that Postgres, being the
    # lighter of the two by default, never gets a *larger* budget than
    # MySQL -- if this regresses, the concurrency math behind
    # max_concurrent_containers in config.py no longer holds.
    mysql_spec = get_engine_spec("mysql")
    postgres_spec = get_engine_spec("postgres")

    def _mb(mem_limit: str) -> int:
        return int(mem_limit.rstrip("m"))

    assert _mb(postgres_spec.mem_limit) <= _mb(mysql_spec.mem_limit)
    assert postgres_spec.command is not None
    assert mysql_spec.command is not None

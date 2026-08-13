from app.engines import get_engine_spec


def test_get_engine_spec_returns_mysql_case_insensitive() -> None:
    spec = get_engine_spec("MySQL")

    assert spec is not None
    assert spec.image == "mysql"
    assert spec.internal_port == 3306


def test_get_engine_spec_returns_none_for_unsupported_engine() -> None:
    assert get_engine_spec("postgres") is None


def test_mysql_env_builder_maps_all_fields() -> None:
    spec = get_engine_spec("mysql")

    env = spec.env_builder("app_db", "app_user", "pw", "rootpw")

    assert env == {
        "MYSQL_ROOT_PASSWORD": "rootpw",
        "MYSQL_DATABASE": "app_db",
        "MYSQL_USER": "app_user",
        "MYSQL_PASSWORD": "pw",
    }

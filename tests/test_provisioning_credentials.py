from app.provisioning.credentials import (
    generate_password,
    generate_username,
    sanitize_database_name,
)
from app.provisioning.naming import container_name_for_port


def test_generate_username_is_fixed_and_valid() -> None:
    assert generate_username() == "app_user"


def test_generate_password_respects_requested_length_budget() -> None:
    password = generate_password(24)

    # token_urlsafe(n) yields ~1.3 chars per byte of entropy, not exactly n
    # characters -- assert a safe floor instead of exact length.
    assert len(password) >= 24
    assert password.isascii()


def test_generate_password_is_not_deterministic() -> None:
    assert generate_password(24) != generate_password(24)


def test_sanitize_database_name_lowercases_and_replaces_invalid_chars() -> None:
    assert sanitize_database_name("My Cool DB!") == "my_cool_db"


def test_sanitize_database_name_strips_leading_and_trailing_underscores() -> None:
    assert sanitize_database_name("--weird--") == "weird"


def test_sanitize_database_name_truncates_long_names() -> None:
    result = sanitize_database_name("a" * 100)

    assert len(result) <= 40


def test_sanitize_database_name_falls_back_when_empty_after_sanitizing() -> None:
    assert sanitize_database_name("!!!") == "app_db"


def test_container_name_for_port_is_deterministic() -> None:
    assert container_name_for_port(30001) == "dbinst-30001"
    assert container_name_for_port(30001) == container_name_for_port(30001)

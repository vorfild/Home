from app.core.security import (
    digest_token,
    generate_temporary_password,
    hash_secret,
    normalize_login,
    validate_password_strength,
    verify_secret,
)


def test_passwords_use_one_way_argon2_hashes() -> None:
    encoded = hash_secret("Strong-family-Password-7")

    assert encoded.startswith("$argon2id$")
    assert "Strong-family-Password-7" not in encoded
    assert verify_secret("Strong-family-Password-7", encoded)
    assert not verify_secret("wrong", encoded)


def test_temporary_password_meets_policy() -> None:
    password = generate_temporary_password()

    assert validate_password_strength(password) == []
    assert len(password) == 16


def test_tokens_are_digested_and_logins_are_normalized() -> None:
    assert digest_token("secret") != "secret"
    assert len(digest_token("secret")) == 64
    assert normalize_login("  Alex.Home  ") == "alex.home"

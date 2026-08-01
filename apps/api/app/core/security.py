from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

LOGIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def normalize_login(login: str) -> str:
    return login.strip().casefold()


def is_valid_login(login: str) -> bool:
    return LOGIN_PATTERN.fullmatch(normalize_login(login)) is not None


def validate_password_strength(password: str) -> list[str]:
    errors: list[str] = []
    if len(password) < 12:
        errors.append("Пароль должен содержать не менее 12 символов")
    if not any(character.islower() for character in password):
        errors.append("Добавьте строчную букву")
    if not any(character.isupper() for character in password):
        errors.append("Добавьте заглавную букву")
    if not any(character.isdigit() for character in password):
        errors.append("Добавьте цифру")
    return errors


def hash_secret(secret: str) -> str:
    return password_hasher.hash(secret)


def verify_secret(secret: str, encoded: str | None) -> bool:
    if encoded is None:
        return False
    try:
        return password_hasher.verify(encoded, secret)
    except (VerificationError, InvalidHashError):
        return False


def opaque_token(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


def digest_token(token: str) -> str:
    key = get_settings().secret_key.get_secret_value().encode("utf-8")
    return hmac.new(key, token.encode("utf-8"), hashlib.sha256).hexdigest()


def constant_time_digest_matches(token: str, digest: str) -> bool:
    return hmac.compare_digest(digest_token(token), digest)


def generate_temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits + "-_.!"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(16))
        if not validate_password_strength(password):
            return password

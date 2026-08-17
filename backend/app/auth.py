import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError


# =========================================================
# JWT CONFIG
# =========================================================

SECRET_KEY = "CHANGE_THIS_SECRET_KEY_FOR_PRODUCTION"

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24


# =========================================================
# PASSWORD HASHING
# =========================================================

def hash_password(password: str) -> str:
    """
    Secure password hashing using Python's built-in scrypt.
    No bcrypt/passlib required.
    """

    if not isinstance(password, str):
        raise ValueError("Password must be a string")

    password_bytes = password.encode("utf-8")

    if len(password_bytes) < 8:
        raise ValueError(
            "Password must contain at least 8 characters"
        )

    # Unique salt for every password
    salt = secrets.token_bytes(16)

    derived_key = hashlib.scrypt(
        password_bytes,
        salt=salt,
        n=16384,
        r=8,
        p=1,
        dklen=64,
    )

    salt_encoded = base64.b64encode(
        salt
    ).decode("utf-8")

    key_encoded = base64.b64encode(
        derived_key
    ).decode("utf-8")

    return f"scrypt${salt_encoded}${key_encoded}"


def verify_password(
    plain_password: str,
    stored_password: str,
) -> bool:

    try:

        parts = stored_password.split("$")

        if len(parts) != 3:
            return False

        algorithm, salt_encoded, key_encoded = parts

        if algorithm != "scrypt":
            return False

        salt = base64.b64decode(
            salt_encoded
        )

        stored_key = base64.b64decode(
            key_encoded
        )

        derived_key = hashlib.scrypt(
            plain_password.encode("utf-8"),
            salt=salt,
            n=16384,
            r=8,
            p=1,
            dklen=64,
        )

        return hmac.compare_digest(
            derived_key,
            stored_key,
        )

    except Exception:
        return False


# =========================================================
# JWT
# =========================================================

def create_access_token(data: dict):

    payload = data.copy()

    expire = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    payload["exp"] = expire

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str):

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        return payload

    except JWTError:

        return None
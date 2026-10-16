"""Email delivery and OTP hashing helpers for login verification."""

import hashlib
import hmac
import os
import secrets
import smtplib
import ssl
from email.message import EmailMessage


OTP_LENGTH = 6
OTP_TTL_SECONDS = 5 * 60
OTP_MAX_ATTEMPTS = 5
OTP_MAX_RESENDS = 3
OTP_RESEND_COOLDOWN_SECONDS = 60
LOGIN_SEND_COOLDOWN_SECONDS = 20


def generate_login_otp() -> str:
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


def hash_login_otp(challenge_id: str, otp: str) -> str:
    secret = os.getenv("OTP_HASH_SECRET", "").strip()

    if len(secret) < 32:
        raise RuntimeError(
            "OTP_HASH_SECRET must be configured with at least 32 characters."
        )

    payload = f"{challenge_id}:{otp}".encode("utf-8")

    return hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


def send_login_otp_email(recipient: str, otp: str) -> None:
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    sender = os.getenv("SMTP_FROM_EMAIL", username).strip()

    port = int(os.getenv("SMTP_PORT", "587"))

    use_ssl = (
        os.getenv("SMTP_USE_SSL", "false").strip().lower()
        in {"1", "true", "yes"}
    )

    use_tls = (
        os.getenv("SMTP_USE_TLS", "true").strip().lower()
        in {"1", "true", "yes"}
    )

    if not host or not username or not password or not sender:
        raise RuntimeError("SMTP email delivery is not configured.")

    if use_ssl and use_tls:
        raise RuntimeError(
            "Set only one of SMTP_USE_SSL or SMTP_USE_TLS to true."
        )

    message = EmailMessage()
    message["Subject"] = (
        "Your Disaster Intelligence Platform login code"
    )
    message["From"] = sender
    message["To"] = recipient

    message.set_content(
        "Your Disaster Intelligence Platform login verification code is: "
        f"{otp}\n\n"
        "This code expires in 5 minutes and can be used only once. "
        "If you did not try to sign in, you can ignore this email. "
        "Do not share this code with anyone.\n"
    )

    timeout_seconds = 15

    if use_ssl:
        with smtplib.SMTP_SSL(
            host,
            port,
            timeout=timeout_seconds,
            context=ssl.create_default_context(),
        ) as server:
            server.login(username, password)
            server.send_message(message)

    else:
        with smtplib.SMTP(
            host,
            port,
            timeout=timeout_seconds,
        ) as server:
            server.ehlo()

            if use_tls:
                server.starttls(
                    context=ssl.create_default_context()
                )
                server.ehlo()

            server.login(username, password)
            server.send_message(message)
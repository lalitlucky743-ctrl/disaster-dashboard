
"""Email delivery and OTP hashing helpers for login verification."""

import base64
import hashlib
import hmac
import json
import os
import secrets
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .gmail_oauth_store import get_encrypted_credentials


OTP_LENGTH = 6
OTP_TTL_SECONDS = 5 * 60
OTP_MAX_ATTEMPTS = 5
OTP_MAX_RESENDS = 3
OTP_RESEND_COOLDOWN_SECONDS = 60
LOGIN_SEND_COOLDOWN_SECONDS = 20
GMAIL_SCOPE = ["https://www.googleapis.com/auth/gmail.send"]


# Keep your existing OTP hashing functions here unchanged.


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
    encryption_key = os.getenv(
        "GMAIL_TOKEN_ENCRYPTION_KEY", ""
    ).strip()
    sender = os.getenv(
        "GMAIL_SENDER_EMAIL", "lucybisht77@gmail.com"
    ).strip()

    if not encryption_key or not sender:
        raise RuntimeError("Gmail configuration is incomplete.")

    encrypted = get_encrypted_credentials()
    if not encrypted:
        raise RuntimeError(
            "Gmail is not authorized. Complete the OAuth setup first."
        )

    try:
        cipher = Fernet(encryption_key.encode())
        credentials_json = cipher.decrypt(
            encrypted.encode()
        ).decode()

        credentials = Credentials.from_authorized_user_info(
            json.loads(credentials_json),
            scopes=GMAIL_SCOPE,
        )

        message = MIMEMultipart("alternative")
        message["To"] = recipient
        message["From"] = sender
        message["Subject"] = (
            "Your Uttarakhand Disaster Intelligence Platform login code"
        )

        message.attach(MIMEText(
            f"Your login verification code is: {otp}\n\n"
            "This code expires in 5 minutes. "
            "Do not share it with anyone.",
            "plain",
        ))

        message.attach(MIMEText(
            "<p>Your login verification code is:</p>"
            f"<h2>{escape(otp)}</h2>"
            "<p>This code expires in 5 minutes. "
            "Do not share it with anyone.</p>",
            "html",
        ))

        raw = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode("utf-8")

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

        result = service.users().messages().send(
            userId="me",
            body={"raw": raw},
        ).execute()

        if not result.get("id"):
            raise RuntimeError("Gmail did not confirm email submission.")

    except Exception as exc:
        # Keep OTPs, OAuth tokens and credentials out of error logs.
        raise RuntimeError(
            "Gmail OTP delivery failed. Check Gmail OAuth configuration."
        ) from exc




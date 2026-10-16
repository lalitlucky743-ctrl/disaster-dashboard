
import hmac
import json
import os

from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Query
from google_auth_oauthlib.flow import Flow
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from pydantic import BaseModel

from ..auth import SECRET_KEY
from ..gmail_oauth_store import save_encrypted_credentials

router = APIRouter()

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
REDIRECT_URI = os.getenv("GMAIL_OAUTH_REDIRECT_URI", "").strip()


class OAuthStartRequest(BaseModel):
    setup_secret: str


def _client_config():
    client_id = os.getenv("GMAIL_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GMAIL_OAUTH_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret or not REDIRECT_URI:
        raise HTTPException(503, "Gmail OAuth configuration is incomplete.")

    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }


def _serializer():
    return URLSafeTimedSerializer(SECRET_KEY, salt="gmail-oauth-state")


@router.post("/start")
def start_oauth(data: OAuthStartRequest):
    expected = os.getenv("GMAIL_OAUTH_SETUP_SECRET", "")
    if not expected or not hmac.compare_digest(data.setup_secret, expected):
        raise HTTPException(403, "Invalid setup authorization.")

    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    state = _serializer().dumps({"purpose": "gmail-setup"})
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )

    return {"authorization_url": url}


@router.get("/callback")
def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(default=None),
):
    if error:
        raise HTTPException(400, "Google authorization was not completed.")

    try:
        payload = _serializer().loads(state, max_age=600)
    except (BadSignature, SignatureExpired):
        raise HTTPException(400, "Invalid or expired OAuth state.")

    if payload.get("purpose") != "gmail-setup":
        raise HTTPException(400, "Invalid OAuth state.")

    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI,
    )

    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials

        if not credentials.refresh_token:
            raise HTTPException(
                400,
                "Google did not return a refresh token. Re-authorize with consent.",
            )

        encryption_key = os.getenv("GMAIL_TOKEN_ENCRYPTION_KEY", "").strip()
        if not encryption_key:
            raise HTTPException(503, "Token encryption is not configured.")

        cipher = Fernet(encryption_key.encode())
        encrypted = cipher.encrypt(credentials.to_json().encode()).decode()
        save_encrypted_credentials(encrypted)

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            502,
            "Gmail authorization failed. Check OAuth settings and server logs.",
        )

    return {
        "status": "authorized",
        "message": "Gmail authorization saved. You can now test OTP email delivery.",
    }




import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import (
    create_access_token,
    hash_password,
    verify_password,
)
from ..database import get_db
from ..models import LoginOTPChallenge, User
from ..otp_email import (
    LOGIN_SEND_COOLDOWN_SECONDS,
    OTP_MAX_ATTEMPTS,
    OTP_MAX_RESENDS,
    OTP_RESEND_COOLDOWN_SECONDS,
    OTP_TTL_SECONDS,
    generate_login_otp,
    hash_login_otp,
    send_login_otp_email,
)
from ..schemas import (
    LoginOTPResendResponse,
    LoginOTPResponse,
    LoginRequest,
    RegisterRequest,
    ResendLoginOTPRequest,
    TokenResponse,
    UserResponse,
    VerifyLoginOTPRequest,
)


router = APIRouter()
logger = logging.getLogger(__name__)


def _mask_email(email: str) -> str:
    local, separator, domain = email.partition("@")

    if not separator or not local:
        return "your registered email"

    if len(local) == 1:
        masked_local = "*"
    elif len(local) == 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[:2] + "*" * min(
            len(local) - 2,
            8,
        )

    return f"{masked_local}@{domain}"


def _deliver_otp_or_fail(
    db: Session,
    challenge: LoginOTPChallenge,
    email: str,
    otp: str,
) -> None:
    try:
        send_login_otp_email(email, otp)

    except Exception as exc:
        logger.exception("Login OTP email delivery failed")

        challenge.consumed = True
        db.commit()

        detail = (
            "Unable to send the login verification email. "
            "Check the email service configuration and try again."
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        ) from exc


# =========================================================
# REGISTER
# =========================================================

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db),
):
    normalized_email = str(data.email).strip().lower()

    existing_user = (
        db.query(User)
        .filter(User.email == normalized_email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        name=data.name.strip(),
        email=normalized_email,
        hashed_password=hash_password(data.password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


# =========================================================
# LOGIN: PASSWORD CHECK, THEN EMAIL OTP
# No JWT is returned at this stage.
# =========================================================

@router.post(
    "/login",
    response_model=LoginOTPResponse,
)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    normalized_email = str(data.email).strip().lower()

    user = (
        db.query(User)
        .filter(User.email == normalized_email)
        .first()
    )

    if not user or not verify_password(
        data.password,
        user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    now = datetime.utcnow()

    latest = (
        db.query(LoginOTPChallenge)
        .filter(LoginOTPChallenge.user_id == user.id)
        .order_by(LoginOTPChallenge.id.desc())
        .first()
    )

    if latest and latest.last_sent_at:
        seconds_since_last_send = (
            now - latest.last_sent_at
        ).total_seconds()

        if seconds_since_last_send < LOGIN_SEND_COOLDOWN_SECONDS:
            wait = max(
                1,
                int(
                    LOGIN_SEND_COOLDOWN_SECONDS
                    - seconds_since_last_send
                ),
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Please wait {wait} seconds before "
                    "requesting another login code."
                ),
            )

    challenge_id = secrets.token_urlsafe(32)
    otp = generate_login_otp()

    try:
        otp_hash = hash_login_otp(challenge_id, otp)

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Login OTP security is not configured on the server."
            ),
        ) from exc

    # Invalidate older unused challenges for this account.
    (
        db.query(LoginOTPChallenge)
        .filter(
            LoginOTPChallenge.user_id == user.id,
            LoginOTPChallenge.consumed.is_(False),
        )
        .update(
            {LoginOTPChallenge.consumed: True},
            synchronize_session=False,
        )
    )

    challenge = LoginOTPChallenge(
        user_id=user.id,
        challenge_id=challenge_id,
        otp_hash=otp_hash,
        created_at=now,
        last_sent_at=now,
        expires_at=now + timedelta(seconds=OTP_TTL_SECONDS),
        attempts=0,
        resend_count=0,
        consumed=False,
    )

    db.add(challenge)
    db.commit()
    db.refresh(challenge)

    _deliver_otp_or_fail(
        db,
        challenge,
        user.email,
        otp,
    )

    return LoginOTPResponse(
        otp_required=True,
        challenge_id=challenge_id,
        email_masked=_mask_email(user.email),
        expires_in_seconds=OTP_TTL_SECONDS,
        message=(
            "A verification code has been sent "
            "to your registered email."
        ),
    )


# =========================================================
# VERIFY OTP: JWT ONLY AFTER SUCCESSFUL VERIFICATION
# =========================================================

@router.post(
    "/verify-otp",
    response_model=TokenResponse,
)
def verify_login_otp(
    data: VerifyLoginOTPRequest,
    db: Session = Depends(get_db),
):
    otp = data.otp.strip()

    if not re.fullmatch(r"\d{6}", otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter the 6-digit verification code.",
        )

    challenge = (
        db.query(LoginOTPChallenge)
        .filter(
            LoginOTPChallenge.challenge_id == data.challenge_id
        )
        .first()
    )

    now = datetime.utcnow()

    if not challenge or challenge.consumed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This verification challenge is invalid or "
                "already used. Please sign in again."
            ),
        )

    if challenge.expires_at <= now:
        challenge.consumed = True
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Your verification code has expired. "
                "Please sign in again."
            ),
        )

    if challenge.attempts >= OTP_MAX_ATTEMPTS:
        challenge.consumed = True
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect codes. Please sign in again.",
        )

    try:
        submitted_hash = hash_login_otp(
            data.challenge_id,
            otp,
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Login OTP security is not configured on the server."
            ),
        ) from exc

    if not hmac.compare_digest(
        submitted_hash,
        challenge.otp_hash,
    ):
        challenge.attempts += 1

        remaining = max(
            0,
            OTP_MAX_ATTEMPTS - challenge.attempts,
        )

        if remaining == 0:
            challenge.consumed = True

        db.commit()

        if remaining == 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Too many incorrect codes. Please sign in again."
                ),
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Incorrect verification code. "
                f"{remaining} attempts remaining."
            ),
        )

    user = (
        db.query(User)
        .filter(User.id == challenge.user_id)
        .first()
    )

    if not user:
        challenge.consumed = True
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This account is no longer available. "
                "Please sign in again."
            ),
        )

    # Consume the OTP before issuing the token.
    consumed_count = (
        db.query(LoginOTPChallenge)
        .filter(
            LoginOTPChallenge.id == challenge.id,
            LoginOTPChallenge.consumed.is_(False),
            LoginOTPChallenge.expires_at > now,
        )
        .update(
            {LoginOTPChallenge.consumed: True},
            synchronize_session=False,
        )
    )

    db.commit()

    if consumed_count != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This verification code has already been used "
                "or expired. Please sign in again."
            ),
        )

    token = create_access_token(
        {
            "sub": user.email,
            "user_id": user.id,
        }
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
    }


# =========================================================
# RESEND OTP
# =========================================================

@router.post(
    "/resend-otp",
    response_model=LoginOTPResendResponse,
)
def resend_login_otp(
    data: ResendLoginOTPRequest,
    db: Session = Depends(get_db),
):
    challenge = (
        db.query(LoginOTPChallenge)
        .filter(
            LoginOTPChallenge.challenge_id == data.challenge_id
        )
        .first()
    )

    now = datetime.utcnow()

    if not challenge or challenge.consumed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This verification challenge is invalid. "
                "Please sign in again."
            ),
        )

    if challenge.expires_at <= now:
        challenge.consumed = True
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Your verification challenge has expired. "
                "Please sign in again."
            ),
        )

    seconds_since_last_send = (
        now - challenge.last_sent_at
    ).total_seconds()

    if seconds_since_last_send < OTP_RESEND_COOLDOWN_SECONDS:
        wait = max(
            1,
            int(
                OTP_RESEND_COOLDOWN_SECONDS
                - seconds_since_last_send
            ),
        )

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Please wait {wait} seconds before "
                "requesting another code."
            ),
        )

    if challenge.resend_count >= OTP_MAX_RESENDS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "The resend limit has been reached. "
                "Please sign in again."
            ),
        )

    user = (
        db.query(User)
        .filter(User.id == challenge.user_id)
        .first()
    )

    if not user:
        challenge.consumed = True
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This account is no longer available. "
                "Please sign in again."
            ),
        )

    otp = generate_login_otp()

    try:
        challenge.otp_hash = hash_login_otp(
            challenge.challenge_id,
            otp,
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Login OTP security is not configured on the server."
            ),
        ) from exc

    challenge.last_sent_at = now
    challenge.expires_at = now + timedelta(
        seconds=OTP_TTL_SECONDS
    )
    challenge.resend_count += 1

    # Keep the incorrect-attempt count when resending.
    db.commit()

    _deliver_otp_or_fail(
        db,
        challenge,
        user.email,
        otp,
    )

    return LoginOTPResendResponse(
        message="A new verification code has been sent.",
        expires_in_seconds=OTP_TTL_SECONDS,
        resend_available_in_seconds=OTP_RESEND_COOLDOWN_SECONDS,
    )
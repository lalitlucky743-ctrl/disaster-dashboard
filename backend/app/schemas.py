from pydantic import BaseModel, EmailStr, Field


# =========================================================
# AUTH
# =========================================================

class RegisterRequest(BaseModel):

    name: str = Field(
        min_length=2,
        max_length=100
    )

    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=256
    )


class LoginRequest(BaseModel):

    email: EmailStr

    password: str = Field(
        min_length=1,
        max_length=256
    )


class UserResponse(BaseModel):

    id: int
    name: str
    email: EmailStr

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):

    access_token: str
    token_type: str
    user: UserResponse


# =========================================================
# AI
# =========================================================

# =========================================================
# AI
# =========================================================

class AIRequest(BaseModel):

    question: str = Field(
        min_length=1,
        max_length=10000
    )

    location: str | None = Field(
        default=None,
        max_length=200
    )


class AIResponse(BaseModel):

    answer: str

    status: str = "ready"


# =========================================================
# DASHBOARD
# =========================================================

class RiskData(BaseModel):

    overall: str
    weather: str
    flood: str
    landslide: str
    earthquake: str


class AlertData(BaseModel):

    id: int
    type: str
    severity: str
    location: str
    message: str
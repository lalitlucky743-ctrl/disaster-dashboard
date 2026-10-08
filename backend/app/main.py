from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import auth
from .routers import dashboard
from .routers import ai
from .routers import weather
from .routers import ml
from .routers import alerts
from app.routers import weather_proxy


# ==========================================================
# DATABASE
# ==========================================================

Base.metadata.create_all(bind=engine)


# ==========================================================
# FASTAPI APPLICATION
# ==========================================================

app = FastAPI(
    title="Disaster Intelligence Platform",
    version="1.0.0",
    description=(
        "Real-time disaster intelligence platform for "
        "weather monitoring, ML-based risk prediction, "
        "and official disaster alerts."
    ),
)


# ==========================================================
# CORS
# ==========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Local Vite development
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",

        # Localhost alternatives
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://127.0.0.1:5176",

        # Production frontend
        "https://disaster-dashboard-vert.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================================
# AUTHENTICATION
# ==========================================================

app.include_router(
    auth.router,
    prefix="/api/auth",
    tags=["Authentication"],
)


# ==========================================================
# DASHBOARD
# ==========================================================

app.include_router(
    dashboard.router,
    prefix="/api/dashboard",
    tags=["Dashboard"],
)


# ==========================================================
# GROQ AI INTELLIGENCE
# ==========================================================

app.include_router(
    ai.router,
    prefix="/api/ai",
    tags=["AI Intelligence"],
)


# ==========================================================
# LIVE WEATHER
# ==========================================================

app.include_router(
    weather.router,
    prefix="/api/weather",
    tags=["Live Weather"],
)



# ==========================================================
# WEATHER PROXY
# ==========================================================

app.include_router(
    weather_proxy.router,
    prefix="/api/weather",
    tags=["Weather Proxy"],
)


# ==========================================================
# ML DISASTER RISK PREDICTION
# ==========================================================

app.include_router(
    ml.router,
    prefix="/api/ml",
    tags=["ML Disaster Prediction"],
)


# ==========================================================
# OFFICIAL DISASTER ALERTS
#
# Sources:
# - IMD
# - SACHET / NDMA
# - Future verified official sources
#
# IMPORTANT:
# This router must NEVER generate fake/default alerts.
# ==========================================================

app.include_router(
    alerts.router,
    prefix="/api/alerts",
    tags=["Official Disaster Alerts"],
)


# ==========================================================
# ROOT
# ==========================================================

@app.get(
    "/",
    tags=["System"],
)
def root():
    return {
        "status": "operational",
        "service": "Disaster Intelligence Platform",
        "version": "1.0.0",
    }


# ==========================================================
# HEALTH CHECK
# ==========================================================

@app.get(
    "/health",
    tags=["System"],
)
def health():
    return {
        "status": "healthy",
    }


# ==========================================================
# HEAD HEALTH CHECK
# ==========================================================

@app.head("/health")
def health_head():
    return None
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import auth
from .routers import dashboard
from .routers import ai
from .routers import weather
from .routers import ml


# Create database tables
Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="Disaster Intelligence Platform",
    version="1.0.0",
)


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "https://disaster-dashboard-vert.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Authentication
# --------------------------------------------------

app.include_router(
    auth.router,
    prefix="/api/auth",
    tags=["Authentication"],
)


# --------------------------------------------------
# Dashboard
# --------------------------------------------------

app.include_router(
    dashboard.router,
    prefix="/api/dashboard",
    tags=["Dashboard"],
)


# --------------------------------------------------
# Groq AI Intelligence
# --------------------------------------------------

app.include_router(
    ai.router,
    prefix="/api/ai",
    tags=["AI Intelligence"],
)


# --------------------------------------------------
# Live Weather
# --------------------------------------------------

app.include_router(
    weather.router,
    prefix="/api/weather",
    tags=["Live Weather"],
)


# --------------------------------------------------
# ML Disaster Risk Prediction
# --------------------------------------------------

app.include_router(
    ml.router,
    prefix="/api/ml",
    tags=["ML Disaster Prediction"],
)


# --------------------------------------------------
# Root
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "status": "operational",
        "service": "Disaster Intelligence Platform",
    }


# --------------------------------------------------
# Health Check
# --------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


@app.head("/health")
def health_head():
    return None
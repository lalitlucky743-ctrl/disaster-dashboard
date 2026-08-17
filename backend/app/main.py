from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine

from .routers import auth
from .routers import dashboard
from .routers import ai


Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="Disaster Intelligence Platform",
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)


app.include_router(
    auth.router,
    prefix="/api/auth",
    tags=["Authentication"],
)

app.include_router(
    dashboard.router,
    prefix="/api/dashboard",
    tags=["Dashboard"],
)

app.include_router(
    ai.router,
    prefix="/api/ai",
    tags=["AI Intelligence"],
)


@app.get("/")
def root():

    return {
        "status": "operational",
        "service": "Disaster Intelligence Platform",
    }


@app.get("/health")
def health():

    return {
        "status": "healthy"
    }
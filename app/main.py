from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.logging import logger
from app.api.v1.auth import router as auth_router
from app.api.v1.patients import router as patients_router
from app.api.v1.consultations import router as consultations_router
from app.api.v1.voice_agent import router as voice_agent_router
from app.db.session import engine, Base
import app.models # Register all models

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Medical Transcription System API...")
    # Create tables if not created yet (for instant dev setup)
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema validated.")
    yield
    logger.info("Shutting down Medical Transcription System API...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI-Based Multilingual Medical Speech Transcription & Documentation System Backend API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list if settings.cors_origins_list else ["*"],
    allow_origin_regex=r"https://.*\.onrender\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Logging Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal clinical system error occurred. Please contact the administrator."}
    )

# Include Routers at both /api and /api/v1 for flexibility
app.include_router(auth_router, prefix="/api")
app.include_router(patients_router, prefix="/api")
app.include_router(consultations_router, prefix="/api")
app.include_router(voice_agent_router, prefix="/api")

app.include_router(auth_router, prefix="/api/v1")
app.include_router(patients_router, prefix="/api/v1")
app.include_router(consultations_router, prefix="/api/v1")
app.include_router(voice_agent_router, prefix="/api/v1")

@app.get("/", tags=["Root"])
def root():
    return {
        "status": "online",
        "message": "Medical Speech Transcription API is running.",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health", tags=["System Health"])
def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "database": "sqlite/relational-sql"
    }

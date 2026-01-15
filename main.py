# app_agregation/main.py

"""
Main FastAPI application entry point.

Initializes the FastAPI app, configures middleware, and sets up
database connections and routing.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config.settings import settings
from api.routes import router
from services.mongodb_service import MongoDBService

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format=settings.LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        *([logging.FileHandler(settings.LOG_FILE)] if settings.LOG_FILE else [])
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.
    """
    # Startup
    logger.info("Starting Video Aggregation Service...")
    
    # Connect to MongoDB
    try:
        await MongoDBService.connect()
        logger.info("MongoDB connection established")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise
    
    # Ensure storage directories exist
    settings.VIDEO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Video storage directory: {settings.VIDEO_STORAGE_DIR}")
    logger.info(f"Temporary directory: {settings.TEMP_DIR}")
    logger.info(f"Server starting on {settings.HOST}:{settings.PORT}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Video Aggregation Service...")
    await MongoDBService.disconnect()
    logger.info("MongoDB connection closed")


# Initialize FastAPI application
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=settings.API_DESCRIPTION,
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for video storage (for direct access)
app.mount(
    "/video_storage",
    StaticFiles(directory=str(settings.VIDEO_STORAGE_DIR)),
    name="video_storage"
)

# Include API routes
app.include_router(router)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint providing service information."""
    return {
        "service": settings.API_TITLE,
        "version": settings.API_VERSION,
        "description": settings.API_DESCRIPTION,
        "docs": "/docs",
        "health": "/api/health"
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=settings.WORKERS,
        log_level=settings.LOG_LEVEL.lower()
    )
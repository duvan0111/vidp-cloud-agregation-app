# app_agregation/main.py

"""
Main FastAPI application entry point.

Initializes the FastAPI app, configures middleware, and sets up
AWS services (S3 and DynamoDB) connections and routing.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from api.routes import router
from services.dynamodb_service import DynamoDBService
from services.s3_service import S3Service

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
    
    # Initialize S3
    try:
        await S3Service.initialize()
        logger.info(f"S3 connection established - Bucket: {settings.S3_BUCKET_NAME}")
    except Exception as e:
        logger.error(f"Failed to initialize S3: {e}")
        raise
    
    # Connect to DynamoDB
    try:
        await DynamoDBService.connect()
        logger.info(f"DynamoDB connection established - Table: {settings.DYNAMODB_TABLE_NAME}")
    except Exception as e:
        logger.error(f"Failed to connect to DynamoDB: {e}")
        raise
    
    # Ensure temp directory exists (for local processing)
    settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Temporary directory: {settings.TEMP_DIR}")
    logger.info(f"S3 Bucket: {settings.S3_BUCKET_NAME}")
    logger.info(f"AWS Region: {settings.AWS_REGION}")
    logger.info(f"Server starting on {settings.HOST}:{settings.PORT}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Video Aggregation Service...")
    await DynamoDBService.disconnect()
    logger.info("AWS services disconnected")


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
        "health": "/api/health",
        "storage": {
            "type": "Amazon S3",
            "bucket": settings.S3_BUCKET_NAME,
            "region": settings.AWS_REGION
        },
        "database": {
            "type": "Amazon DynamoDB",
            "table": settings.DYNAMODB_TABLE_NAME
        }
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
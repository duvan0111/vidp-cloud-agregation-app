# app_agregation/config/settings.py

"""
Configuration module for Video Aggregation Service.

Centralizes environment variables, paths, and service endpoints using
Pydantic settings management for type safety and validation.
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, model_validator


class Settings(BaseSettings):
    """
    Application settings with environment variable support.
    
    All settings can be overridden via environment variables or .env file.
    """
    
    # ========== Service Information ==========
    API_TITLE: str = "Video Aggregation Service"
    API_VERSION: str = "2.0.0"
    API_DESCRIPTION: str = (
        "Microservice orchestrating video processing: "
        "subtitle generation, burning, compression, and streaming"
    )
    
    # ========== Server Configuration ==========
    HOST: str = Field(default="127.0.0.1", description="Server host address")
    PORT: int = Field(default=8005, ge=1, le=65535, description="Server port")
    
    API_URL: Optional[str] = Field(
        default=None, 
        description="Public base URL of the service (used for links)"
    )
    
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    WORKERS: int = Field(default=1, ge=1, description="Number of worker processes")
    
    # ========== AWS Configuration ==========
    AWS_ACCESS_KEY_ID: Optional[str] = Field(
        default=None,
        description="AWS Access Key ID (optional if using IAM roles)"
    )
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(
        default=None,
        description="AWS Secret Access Key (optional if using IAM roles)"
    )
    AWS_REGION: str = Field(
        default="us-east-1",
        description="AWS Region"
    )
    
    # ========== S3 Configuration ==========
    S3_BUCKET_NAME: str = Field(
        default="vidp-video-storage",
        description="S3 bucket name for video storage"
    )
    S3_PREFIX: str = Field(
        default="videos/",
        description="S3 key prefix for video files"
    )
    S3_PRESIGNED_URL_EXPIRATION: int = Field(
        default=3600,
        ge=60,
        description="Presigned URL expiration time in seconds"
    )
    
    # ========== DynamoDB Configuration ==========
    DYNAMODB_TABLE_NAME: str = Field(
        default="vidp_videos",
        description="DynamoDB table name for video metadata"
    )
    DYNAMODB_ENDPOINT_URL: Optional[str] = Field(
        default=None,
        description="DynamoDB endpoint URL (for local development with DynamoDB Local)"
    )
    
    # ========== External Service URLs ==========
    SUBTITLE_SERVICE_URL: str = Field(
        default="http://localhost:8002/api/generate-subtitles/",
        description="Subtitle generation service endpoint"
    )
    COMPRESSION_SERVICE_URL: str = Field(
        default="http://localhost:8001/api/compress/upload",
        description="Video compression service endpoint"
    )
    
    # ========== Timeout Configuration (seconds) ==========
    HTTP_TIMEOUT: float = Field(
        default=600.0,
        ge=10.0,
        description="Global HTTP request timeout"
    )
    SUBTITLE_TIMEOUT: float = Field(
        default=600.0,
        ge=10.0,
        description="Subtitle generation timeout"
    )
    COMPRESSION_TIMEOUT: float = Field(
        default=600.0,
        ge=10.0,
        description="Video compression timeout"
    )
    
    # ========== Storage Configuration ==========
    BASE_DIR: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent,
        description="Application base directory"
    )
    TEMP_DIR: Optional[Path] = Field(
        default=None,
        description="Temporary file storage directory"
    )
    VIDEO_STORAGE_DIR: Optional[Path] = Field(
        default=None,
        description="Local video storage directory (fallback/cache)"
    )
    MAX_UPLOAD_SIZE: int = Field(
        default=500 * 1024 * 1024,  # 500MB
        ge=1024 * 1024,  # Minimum 1MB
        description="Maximum upload file size in bytes"
    )
    
    # ========== Video Streaming Configuration ==========
    CHUNK_SIZE: int = Field(
        default=1024 * 1024,  # 1MB chunks
        ge=64 * 1024,  # Minimum 64KB
        description="Chunk size for video streaming in bytes"
    )
    
    # ========== FFmpeg Configuration ==========
    FFMPEG_PRESET: str = Field(
        default="medium",
        description="FFmpeg encoding preset (ultrafast, fast, medium, slow)"
    )
    FFMPEG_CODEC: str = Field(
        default="libx264",
        description="Video codec for encoding"
    )
    FFMPEG_TIMEOUT: int = Field(
        default=600,
        ge=30,
        description="FFmpeg operation timeout in seconds"
    )
    
    # ========== Logging Configuration ==========
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    LOG_FILE: Optional[str] = Field(
        default=None,
        description="Optional log file path"
    )
    LOG_FORMAT: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log message format"
    )
    
    # ========== Security Configuration ==========
    ALLOWED_EXTENSIONS: list[str] = Field(
        default=[".mp4", ".avi", ".mov", ".mkv"],
        description="Allowed video file extensions"
    )
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore"
    }
    
    # Validators
    
    @model_validator(mode='after')
    def set_api_url_default(self):
        """
        Automatically set API_URL based on HOST and PORT if not provided.
        """
        if not self.API_URL:
            self.API_URL = f"http://{self.HOST}:{self.PORT}"
        
        if self.API_URL.endswith('/'):
            self.API_URL = self.API_URL[:-1]
            
        return self

    @field_validator("TEMP_DIR", mode="before")
    @classmethod
    def set_temp_dir(cls, v, info):
        """Set and create temporary directory if not specified."""
        if v is None:
            base_dir = info.data.get("BASE_DIR", Path(__file__).resolve().parent.parent)
            v = base_dir / "temp_aggregator"
        
        temp_path = Path(v)
        temp_path.mkdir(parents=True, exist_ok=True)
        return temp_path
    
    @field_validator("VIDEO_STORAGE_DIR", mode="before")
    @classmethod
    def set_video_storage_dir(cls, v, info):
        """Set and create video storage directory if not specified."""
        if v is None:
            base_dir = info.data.get("BASE_DIR", Path(__file__).resolve().parent.parent)
            v = base_dir / "video_storage"
        
        storage_path = Path(v)
        storage_path.mkdir(parents=True, exist_ok=True)
        return storage_path
    
    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level is a valid Python logging level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v.upper()
    
    @field_validator("FFMPEG_PRESET")
    @classmethod
    def validate_ffmpeg_preset(cls, v):
        """Validate FFmpeg preset value."""
        valid_presets = ["ultrafast", "superfast", "veryfast", "faster", "fast", 
                         "medium", "slow", "slower", "veryslow"]
        if v not in valid_presets:
            raise ValueError(f"FFMPEG_PRESET must be one of {valid_presets}")
        return v


# Singleton settings instance
settings = Settings()
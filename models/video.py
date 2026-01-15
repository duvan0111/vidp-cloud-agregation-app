# app_agregation/models/video.py

"""
MongoDB models for video metadata storage.
Updated for Pydantic v2 and Python 3.12 compatibility.
"""

from datetime import datetime
from typing import Optional, Annotated
from enum import Enum
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict
from bson import ObjectId

# --- Custom Type for Pydantic v2 ---
# This helper ensures that MongoDB ObjectIds are converted to strings 
# before Pydantic tries to validate them.
PyObjectId = Annotated[str, BeforeValidator(str)]

class VideoStatus(str, Enum):
    """Video processing status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    SAVED = "saved"
    FAILED = "failed"

class VideoMetadata(BaseModel):
    """
    Video metadata model for MongoDB storage.
    
    Attributes:
        id: Unique identifier (mapped from MongoDB '_id').
        source_video_id: ID from the main vidp-fastapi-service (for cross-database reference).
        filename: Original name of the uploaded file.
        file_path: Internal storage path.
        link: Publicly accessible URL.
        status: Current processing status.
        created_at: Timestamp of creation.
    """
    # Map MongoDB's '_id' to Python's 'id'
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    
    # Reference to the original video in vidp-fastapi-service database
    source_video_id: Optional[str] = Field(None, description="Video ID from the main service (vidp-fastapi-service)")
    
    filename: str = Field(..., description="Original filename of the video")
    file_path: str = Field(..., description="Relative path to video file")
    link: str = Field(..., description="Full URL to access/stream the video")
    status: VideoStatus = Field(default=VideoStatus.PENDING, description="Processing status")
    
    file_size: Optional[int] = Field(None, description="File size in bytes")
    duration: Optional[float] = Field(None, description="Video duration in seconds")
    resolution: Optional[str] = Field(None, description="Video resolution (e.g., 1920x1080)")
    
    # Use datetime.now() because utcnow() is deprecated in Python 3.12
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    
    error_message: Optional[str] = Field(None, description="Error message if status is FAILED")

    # Pydantic v2 Configuration
    model_config = ConfigDict(
        populate_by_name=True,       # Allows using 'id' or '_id'
        arbitrary_types_allowed=True, # Allows ObjectId to pass through if needed
        json_schema_extra={
            "example": {
                "id": "65a1234567890abcdef12345",
                "source_video_id": "550e8400-e29b-41d4-a716-446655440000",
                "filename": "sample_video.mp4",
                "file_path": "video_storage/job_abc123_final.mp4",
                "link": "http://localhost:8000/video_storage/job_abc123_final.mp4",
                "status": "saved",
                "file_size": 15728640,
                "duration": 120.5,
                "resolution": "1920x1080"
            }
        }
    )

class VideoCreateRequest(BaseModel):
    """
    Request model for creating video metadata.
    Used when the API receives a new video upload.
    """
    filename: str
    file_path: str
    link: str
    status: VideoStatus = VideoStatus.PENDING
    file_size: Optional[int] = None
    source_video_id: Optional[str] = None  # ID from vidp-fastapi-service

class VideoUpdateRequest(BaseModel):
    """
    Request model for updating video metadata.
    Fields are optional to allow partial updates.
    """
    status: Optional[VideoStatus] = None
    error_message: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[float] = None
    resolution: Optional[str] = None
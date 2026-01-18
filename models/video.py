# app_agregation/models/video.py

"""
Pydantic models for video metadata storage.
Updated for DynamoDB and Pydantic v2 compatibility.
"""

from datetime import datetime
from typing import Optional, Dict
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, field_validator


class VideoStatus(str, Enum):
    """Video processing status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    SAVED = "saved"
    FAILED = "failed"


class VideoMetadata(BaseModel):
    """
    Video metadata model for DynamoDB storage.
    
    NEW FIELDS:
    - detected_language: Language detected by language detection service
    - animals_detected: Dictionary of animals detected by YOLO service
    
    Attributes:
        videoId: Primary key in DynamoDB (UUID string).
        id: Alias for videoId for backward compatibility.
        source_video_id: ID from the main vidp-fastapi-service (for cross-database reference).
        filename: Original name of the uploaded file.
        file_path: Storage path (S3 key or local path).
        s3_key: S3 object key for the video file.
        link: Publicly accessible URL (presigned URL or direct link).
        status: Current processing status.
        detected_language: Language code detected (e.g., 'fr', 'en', 'es').
        animals_detected: Dictionary of detected animals with counts (e.g., {'dog': 5, 'cat': 2}).
        created_at: Timestamp of creation.
    """
    videoId: Optional[str] = Field(default=None, description="Unique video ID (UUID) - Primary Key")
    id: Optional[str] = Field(default=None, description="Alias for videoId")
    
    # Reference to the original video in vidp-fastapi-service database
    source_video_id: Optional[str] = Field(None, description="Video ID from the main service (vidp-fastapi-service)")
    
    filename: str = Field(..., description="Original filename of the video")
    file_path: str = Field(..., description="Storage path (S3 key or local path)")
    s3_key: Optional[str] = Field(None, description="S3 object key for the video")
    link: str = Field(..., description="Full URL to access/stream the video")
    status: VideoStatus = Field(default=VideoStatus.PENDING, description="Processing status")
    
    file_size: Optional[int] = Field(None, description="File size in bytes")
    duration: Optional[float] = Field(None, description="Video duration in seconds")
    resolution: Optional[str] = Field(None, description="Video resolution (e.g., 1920x1080)")
    
    # NEW FIELDS FOR METADATA
    detected_language: Optional[str] = Field(
        None, 
        description="Language detected by language detection service (ISO code: fr, en, es, etc.)"
    )
    animals_detected: Optional[Dict[str, int]] = Field(
        None,
        description="Animals detected by YOLO service with their counts (e.g., {'dog': 5, 'cat': 2})"
    )
    
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    
    error_message: Optional[str] = Field(None, description="Error message if status is FAILED")

    # Pydantic v2 Configuration
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "videoId": "550e8400-e29b-41d4-a716-446655440000",
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "source_video_id": "550e8400-e29b-41d4-a716-446655440001",
                "filename": "sample_video.mp4",
                "file_path": "videos/job_abc123_final.mp4",
                "s3_key": "job_abc123_final.mp4",
                "link": "https://bucket.s3.amazonaws.com/videos/job_abc123_final.mp4",
                "status": "saved",
                "file_size": 15728640,
                "duration": 120.5,
                "resolution": "1920x1080",
                "detected_language": "fr",
                "animals_detected": {
                    "dog": 5,
                    "cat": 2,
                    "bird": 1
                }
            }
        }
    )
    
    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def parse_datetime(cls, v):
        """Parse datetime from ISO format string if needed."""
        if isinstance(v, str):
            return datetime.fromisoformat(v)
        return v
    
    def model_post_init(self, __context):
        """Ensure videoId and id are synchronized."""
        if self.videoId and not self.id:
            self.id = self.videoId
        elif self.id and not self.videoId:
            self.videoId = self.id


class VideoCreateRequest(BaseModel):
    """
    Request model for creating video metadata.
    Used when the API receives a new video upload.
    """
    filename: str
    file_path: str
    link: str
    s3_key: Optional[str] = None
    status: VideoStatus = VideoStatus.PENDING
    file_size: Optional[int] = None
    source_video_id: Optional[str] = None
    detected_language: Optional[str] = None
    animals_detected: Optional[Dict[str, int]] = None


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
    link: Optional[str] = None
    s3_key: Optional[str] = None
    detected_language: Optional[str] = None
    animals_detected: Optional[Dict[str, int]] = None
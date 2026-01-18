# app_aggregation/api/routes.py
"""
API route definitions for video processing endpoints.
UPDATED: Now accepts detected_language and animals_detected from vidp-fastapi-service
"""

import logging
from pathlib import Path
from typing import Optional
import uuid
import json

from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException, status, Request
from fastapi.responses import StreamingResponse, RedirectResponse

from config.settings import settings
from services.ffmpeg_service import FFmpegService
from services.dynamodb_service import DynamoDBService
from services.s3_service import S3Service
from models.video import VideoStatus, VideoCreateRequest, VideoUpdateRequest
from utils.file_utils import cleanup_files, validate_file_size

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Video Processing"])


@router.post(
    "/process-video/",
    summary="Process video with SRT file upload and metadata",
    response_description="Returns video metadata and streaming URL",
    status_code=status.HTTP_200_OK
)
async def process_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(..., description="Video file to process (MP4 format)"),
    srt_file: UploadFile = File(..., description="SRT subtitle file to burn into the video"),
    resolution: str = Form(default="360p", description="Target video resolution"),
    crf_value: int = Form(default=23, ge=0, le=51, description="Video quality (0-51, lower is better)"),
    source_video_id: Optional[str] = Form(default=None, description="Video ID from the main service (vidp-fastapi-service)"),
    original_filename: Optional[str] = Form(default=None, description="Original filename uploaded by user"),
    detected_language: Optional[str] = Form(default=None, description="Language detected by language detection service (ISO code)"),
    animals_detected: Optional[str] = Form(default=None, description="Animals detected by YOLO service (JSON string)")
) -> dict:
    """
    Process video with provided SRT subtitles, burn them in, compress, and store to S3.
    
    NEW: Also receives and stores original_filename, detected_language and animals_detected metadata.
    
    Steps:
    1. Save uploaded video and SRT file locally (temp)
    2. Burn subtitles into video using FFmpeg
    3. Upload final video to S3
    4. Save metadata to DynamoDB (including original filename, language and animals)
    5. Return streaming URL (presigned S3 URL)
    """
    # Generate a unique Job ID
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    logger.info(f"[{job_id}] Starting video processing for: {video.filename}")
    
    # Use original_filename if provided, otherwise use uploaded filename
    final_original_filename = original_filename if original_filename else video.filename
    logger.info(f"[{job_id}] Original filename: {final_original_filename}")
    
    # Parse animals_detected if provided
    animals_dict = None
    if animals_detected:
        try:
            animals_dict = json.loads(animals_detected)
            logger.info(f"[{job_id}] Animals detected: {animals_dict}")
        except json.JSONDecodeError as e:
            logger.warning(f"[{job_id}] Failed to parse animals_detected JSON: {e}")
    
    # Log detected language
    if detected_language:
        logger.info(f"[{job_id}] Detected language: {detected_language}")
    
    # Define file paths (local temp)
    original_video_path = settings.TEMP_DIR / f"{job_id}_original.mp4"
    srt_path = settings.TEMP_DIR / f"{job_id}.srt"
    burned_video_path = settings.TEMP_DIR / f"{job_id}_burned.mp4"
    
    # Final S3 key
    final_filename = f"{job_id}_final.mp4"
    s3_key = final_filename
    
    # Track temporary files for cleanup
    temp_files = [original_video_path, srt_path, burned_video_path]
    
    # Resolution mapping
    resolution_map = {
        "1080p": "1920x1080",
        "720p": "1280x720",
        "480p": "854x480",
        "360p": "640x360"
    }
    target_resolution = resolution_map.get(resolution, "640x360")
    
    video_id = None
    
    try:
        # Step 1: Save uploaded video
        logger.info(f"[{job_id}] Saving uploaded video: {video.filename}")
        settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        
        video_content = await video.read()
        with open(original_video_path, "wb") as buffer:
            buffer.write(video_content)
        
        if hasattr(settings, 'MAX_UPLOAD_SIZE') and not validate_file_size(original_video_path, settings.MAX_UPLOAD_SIZE):
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds maximum allowed size"
            )
        
        # Step 2: Save uploaded SRT file
        logger.info(f"[{job_id}] Saving uploaded SRT file: {srt_file.filename}")
        
        srt_content = await srt_file.read()
        logger.info(f"[{job_id}] SRT content size: {len(srt_content)} bytes")
        
        has_subtitles = len(srt_content) > 0
        if not has_subtitles:
            logger.info(f"[{job_id}] SRT file is empty - will process video without subtitles")
        
        with open(srt_path, "wb") as buffer:
            buffer.write(srt_content)
        
        if has_subtitles:
            logger.info(f"[{job_id}] SRT file written, size on disk: {srt_path.stat().st_size} bytes")

        # Step 3: Create initial DynamoDB entry
        streaming_url = f"{settings.API_URL}/api/stream/{final_filename}"
        
        if source_video_id:
            logger.info(f"[{job_id}] Linking to source video ID: {source_video_id}")
        
        video_create = VideoCreateRequest(
            filename=final_original_filename,  # Use the original filename from user
            file_path=f"s3://{settings.S3_BUCKET_NAME}/{settings.S3_PREFIX}{s3_key}",
            s3_key=s3_key,
            link=streaming_url,
            status=VideoStatus.PROCESSING,
            file_size=original_video_path.stat().st_size,
            source_video_id=source_video_id
        )
        
        video_metadata = await DynamoDBService.create_video(video_create)
        video_id = str(video_metadata.id)
        
        # Step 4: Burn subtitles into video
        logger.info(f"[{job_id}] Burning subtitles into video")
        
        await FFmpegService.burn_subtitles(
            video_path=str(original_video_path),
            srt_path=str(srt_path),
            output_path=str(burned_video_path),
            resolution=target_resolution,
            crf=crf_value
        )
        
        # Step 5: Upload to S3
        logger.info(f"[{job_id}] Uploading final video to S3")
        s3_uri = await S3Service.upload_file(
            local_path=burned_video_path,
            s3_key=s3_key,
            content_type="video/mp4"
        )
        
        # Step 6: Get final video information
        video_info = FFmpegService.get_video_metadata(str(burned_video_path))
        
        # Step 7: Generate presigned URL for streaming
        presigned_url = await S3Service.get_presigned_url(s3_key)
        
        # Step 8: Update DynamoDB with success status + language + animals
        update_data_dict = {
            "status": VideoStatus.SAVED,
            "file_size": video_info.get("size"),
            "duration": video_info.get("duration"),
            "resolution": video_info.get("resolution"),
            "link": presigned_url,
            "s3_key": s3_key
        }
        
        # Add detected_language if provided
        if detected_language:
            update_data_dict["detected_language"] = detected_language
        
        # Add animals_detected if provided
        if animals_dict:
            update_data_dict["animals_detected"] = animals_dict
        
        update_data = VideoUpdateRequest(**update_data_dict)
        
        await DynamoDBService.update_video(video_id, update_data)
        
        # Schedule cleanup
        background_tasks.add_task(cleanup_files, temp_files)
        
        logger.info(f"[{job_id}] Video processing completed successfully")
        
        return {
            "status": "success",
            "job_id": job_id,
            "video_id": video_id,
            "source_video_id": source_video_id,
            "message": "Video processed and stored successfully in S3",
            "streaming_url": presigned_url,
            "s3_uri": s3_uri,
            "metadata": {
                "original_filename": final_original_filename,  # Return the original filename
                "final_filename": final_filename,
                "s3_key": s3_key,
                "resolution": video_info.get("resolution"),
                "duration": video_info.get("duration"),
                "file_size": video_info.get("size"),
                "detected_language": detected_language,
                "animals_detected": animals_dict
            }
        }
    
    except HTTPException:
        if video_id:
            await DynamoDBService.update_video(
                video_id,
                VideoUpdateRequest(status=VideoStatus.FAILED, error_message="HTTP error occurred")
            )
        cleanup_files(temp_files)
        raise
    
    except Exception as e:
        logger.error(f"[{job_id}] Processing failed: {str(e)}", exc_info=True)
        if video_id:
            await DynamoDBService.update_video(
                video_id,
                VideoUpdateRequest(status=VideoStatus.FAILED, error_message=str(e))
            )
        cleanup_files(temp_files)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.get(
    "/stream/{filename}",
    summary="Stream video from S3 with range request support",
    responses={
        200: {"description": "Video stream"},
        206: {"description": "Partial content (range request)"},
        302: {"description": "Redirect to presigned S3 URL"},
        404: {"description": "Video not found"}
    }
)
async def stream_video(filename: str, request: Request):
    """
    Stream video from S3. 
    For simple requests, redirects to presigned URL.
    For range requests, streams through the server.
    """
    s3_key = filename
    
    # Check if file exists in S3
    if not await S3Service.file_exists(s3_key):
        logger.warning(f"Stream attempt for non-existent file: {filename}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    
    range_header = request.headers.get("range")
    
    if not range_header:
        # Simple request - redirect to presigned URL
        presigned_url = await S3Service.get_presigned_url(s3_key)
        return RedirectResponse(url=presigned_url, status_code=302)
    
    # Range request - stream through server for better compatibility
    file_size = await S3Service.get_file_size(s3_key)
    
    if file_size is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    
    # Parse range header
    range_match = range_header.replace("bytes=", "").split("-")
    try:
        start = int(range_match[0]) if range_match[0] else 0
        end = int(range_match[1]) if len(range_match) > 1 and range_match[1] else file_size - 1
    except ValueError:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid range format")
    
    if start >= file_size or end >= file_size or start > end:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid range")
    
    chunk_size = end - start + 1
    
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
        "Content-Type": "video/mp4",
    }
    
    return StreamingResponse(
        S3Service.stream_file(s3_key, start_byte=start, end_byte=end),
        status_code=206,
        headers=headers,
        media_type="video/mp4"
    )


@router.get("/videos/{video_id}")
async def get_video_metadata(video_id: str) -> dict:
    """Get video metadata by ID (including detected_language and animals_detected)."""
    video = await DynamoDBService.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Generate fresh presigned URL if we have an S3 key
    if video.s3_key:
        try:
            video.link = await S3Service.get_presigned_url(video.s3_key)
        except Exception as e:
            logger.warning(f"Failed to generate presigned URL: {e}")
    
    return video.model_dump()


@router.get("/videos/by-source/{source_video_id}")
async def get_video_by_source_id(source_video_id: str) -> dict:
    """
    Retrieve aggregated video metadata by source video ID from vidp-fastapi-service.
    Includes detected_language and animals_detected if available.
    """
    video = await DynamoDBService.get_video_by_source_id(source_video_id)
    if not video:
        raise HTTPException(
            status_code=404, 
            detail=f"No aggregated video found for source_video_id: {source_video_id}"
        )
    
    # Generate fresh presigned URL
    if video.s3_key:
        try:
            video.link = await S3Service.get_presigned_url(video.s3_key)
        except Exception as e:
            logger.warning(f"Failed to generate presigned URL: {e}")
    
    return video.model_dump()


@router.get("/videos/")
async def list_videos(status: Optional[VideoStatus] = None, limit: int = 100) -> dict:
    """List all videos with optional status filter."""
    videos = await DynamoDBService.list_videos(status=status, limit=limit)
    
    # Generate fresh presigned URLs for all videos
    for video in videos:
        if video.s3_key:
            try:
                video.link = await S3Service.get_presigned_url(video.s3_key)
            except Exception as e:
                logger.warning(f"Failed to generate presigned URL for {video.id}: {e}")
    
    return {
        "total": len(videos), 
        "videos": [video.model_dump() for video in videos]
    }


@router.delete("/videos/{video_id}")
async def delete_video(video_id: str, background_tasks: BackgroundTasks) -> dict:
    """Delete a video from S3 and DynamoDB."""
    video = await DynamoDBService.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Delete from S3
    if video.s3_key:
        try:
            await S3Service.delete_file(video.s3_key)
            logger.info(f"Deleted video from S3: {video.s3_key}")
        except Exception as e:
            logger.warning(f"Failed to delete from S3: {e}")
    
    # Delete from DynamoDB
    deleted = await DynamoDBService.delete_video(video_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Video metadata not found")
    
    return {"status": "success", "message": f"Video {video_id} deleted successfully"}


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    dynamodb_status = await DynamoDBService.is_connected()
    
    # Check S3 access
    s3_status = False
    try:
        session = S3Service._get_session()
        async with session.client("s3") as s3:
            await s3.head_bucket(Bucket=settings.S3_BUCKET_NAME)
            s3_status = True
    except Exception:
        s3_status = False
    
    return {
        "status": "healthy" if (dynamodb_status and s3_status) else "degraded",
        "service": "Video Aggregation Service",
        "version": getattr(settings, "API_VERSION", "2.0.0"),
        "storage": {
            "type": "Amazon S3",
            "bucket": settings.S3_BUCKET_NAME,
            "connected": s3_status
        },
        "database": {
            "type": "Amazon DynamoDB",
            "table": settings.DYNAMODB_TABLE_NAME,
            "connected": dynamodb_status
        }
    }
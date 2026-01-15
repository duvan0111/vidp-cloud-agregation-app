# app_agregation/services/s3_service.py

"""
Amazon S3 service for video file storage.
Handles upload, download, streaming, and deletion of video files.
"""

import logging
from pathlib import Path
from typing import Optional, AsyncGenerator
import aioboto3
from botocore.exceptions import ClientError

from config.settings import settings

logger = logging.getLogger(__name__)


class S3Service:
    """
    Service class for Amazon S3 operations on video files.
    Provides asynchronous methods for file storage operations.
    """
    
    _session: Optional[aioboto3.Session] = None
    
    @classmethod
    def _get_session(cls) -> aioboto3.Session:
        """Get or create aioboto3 session."""
        if cls._session is None:
            session_kwargs = {}
            
            # Use explicit credentials if provided, otherwise use IAM roles
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                session_kwargs = {
                    "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
                    "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
                    "region_name": settings.AWS_REGION
                }
            else:
                session_kwargs = {"region_name": settings.AWS_REGION}
            
            cls._session = aioboto3.Session(**session_kwargs)
        
        return cls._session
    
    @classmethod
    async def initialize(cls):
        """
        Initialize S3 service and verify bucket access.
        Creates the bucket if it doesn't exist.
        """
        try:
            session = cls._get_session()
            async with session.client("s3") as s3:
                # Check if bucket exists
                try:
                    await s3.head_bucket(Bucket=settings.S3_BUCKET_NAME)
                    logger.info(f"S3 bucket verified: {settings.S3_BUCKET_NAME}")
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "")
                    if error_code == "404":
                        # Bucket doesn't exist, create it
                        logger.info(f"Creating S3 bucket: {settings.S3_BUCKET_NAME}")
                        create_params = {"Bucket": settings.S3_BUCKET_NAME}
                        
                        # LocationConstraint is required for non-us-east-1 regions
                        if settings.AWS_REGION != "us-east-1":
                            create_params["CreateBucketConfiguration"] = {
                                "LocationConstraint": settings.AWS_REGION
                            }
                        
                        await s3.create_bucket(**create_params)
                        logger.info(f"S3 bucket created: {settings.S3_BUCKET_NAME}")
                    else:
                        raise
                        
        except Exception as e:
            logger.error(f"Failed to initialize S3 service: {e}")
            raise
    
    @classmethod
    async def upload_file(
        cls,
        local_path: Path,
        s3_key: str,
        content_type: str = "video/mp4"
    ) -> str:
        """
        Upload a file to S3.
        
        Args:
            local_path: Path to the local file to upload.
            s3_key: S3 object key (path within the bucket).
            content_type: MIME type of the file.
            
        Returns:
            str: The S3 URI of the uploaded file.
            
        Raises:
            ClientError: If upload fails.
        """
        try:
            session = cls._get_session()
            full_key = f"{settings.S3_PREFIX}{s3_key}"
            
            async with session.client("s3") as s3:
                with open(local_path, "rb") as file_data:
                    await s3.upload_fileobj(
                        file_data,
                        settings.S3_BUCKET_NAME,
                        full_key,
                        ExtraArgs={"ContentType": content_type}
                    )
            
            s3_uri = f"s3://{settings.S3_BUCKET_NAME}/{full_key}"
            logger.info(f"File uploaded to S3: {s3_uri}")
            return s3_uri
            
        except ClientError as e:
            logger.error(f"Failed to upload file to S3: {e}")
            raise
    
    @classmethod
    async def download_file(cls, s3_key: str, local_path: Path) -> Path:
        """
        Download a file from S3.
        
        Args:
            s3_key: S3 object key (without prefix).
            local_path: Local path to save the file.
            
        Returns:
            Path: Path to the downloaded file.
            
        Raises:
            ClientError: If download fails.
        """
        try:
            session = cls._get_session()
            full_key = f"{settings.S3_PREFIX}{s3_key}"
            
            async with session.client("s3") as s3:
                with open(local_path, "wb") as file_data:
                    await s3.download_fileobj(
                        settings.S3_BUCKET_NAME,
                        full_key,
                        file_data
                    )
            
            logger.info(f"File downloaded from S3: {full_key} -> {local_path}")
            return local_path
            
        except ClientError as e:
            logger.error(f"Failed to download file from S3: {e}")
            raise
    
    @classmethod
    async def get_presigned_url(
        cls,
        s3_key: str,
        expiration: Optional[int] = None
    ) -> str:
        """
        Generate a presigned URL for accessing a file.
        
        Args:
            s3_key: S3 object key (without prefix).
            expiration: URL expiration time in seconds.
            
        Returns:
            str: Presigned URL for the file.
        """
        try:
            session = cls._get_session()
            full_key = f"{settings.S3_PREFIX}{s3_key}"
            exp_time = expiration or settings.S3_PRESIGNED_URL_EXPIRATION
            
            async with session.client("s3") as s3:
                url = await s3.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": settings.S3_BUCKET_NAME,
                        "Key": full_key
                    },
                    ExpiresIn=exp_time
                )
            
            logger.debug(f"Generated presigned URL for: {full_key}")
            return url
            
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise
    
    @classmethod
    async def delete_file(cls, s3_key: str) -> bool:
        """
        Delete a file from S3.
        
        Args:
            s3_key: S3 object key (without prefix).
            
        Returns:
            bool: True if deleted successfully.
        """
        try:
            session = cls._get_session()
            full_key = f"{settings.S3_PREFIX}{s3_key}"
            
            async with session.client("s3") as s3:
                await s3.delete_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=full_key
                )
            
            logger.info(f"File deleted from S3: {full_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to delete file from S3: {e}")
            raise
    
    @classmethod
    async def file_exists(cls, s3_key: str) -> bool:
        """
        Check if a file exists in S3.
        
        Args:
            s3_key: S3 object key (without prefix).
            
        Returns:
            bool: True if file exists.
        """
        try:
            session = cls._get_session()
            full_key = f"{settings.S3_PREFIX}{s3_key}"
            
            async with session.client("s3") as s3:
                await s3.head_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=full_key
                )
            return True
            
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "404":
                return False
            raise
    
    @classmethod
    async def get_file_size(cls, s3_key: str) -> Optional[int]:
        """
        Get the size of a file in S3.
        
        Args:
            s3_key: S3 object key (without prefix).
            
        Returns:
            Optional[int]: File size in bytes, or None if not found.
        """
        try:
            session = cls._get_session()
            full_key = f"{settings.S3_PREFIX}{s3_key}"
            
            async with session.client("s3") as s3:
                response = await s3.head_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=full_key
                )
                return response.get("ContentLength")
            
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "404":
                return None
            raise
    
    @classmethod
    async def stream_file(
        cls,
        s3_key: str,
        start_byte: int = 0,
        end_byte: Optional[int] = None
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream a file from S3 with optional byte range support.
        
        Args:
            s3_key: S3 object key (without prefix).
            start_byte: Starting byte position.
            end_byte: Ending byte position (inclusive).
            
        Yields:
            bytes: Chunks of file data.
        """
        try:
            session = cls._get_session()
            full_key = f"{settings.S3_PREFIX}{s3_key}"
            
            # Build range header
            range_header = f"bytes={start_byte}-"
            if end_byte is not None:
                range_header = f"bytes={start_byte}-{end_byte}"
            
            async with session.client("s3") as s3:
                response = await s3.get_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=full_key,
                    Range=range_header
                )
                
                async with response["Body"] as stream:
                    while True:
                        chunk = await stream.read(settings.CHUNK_SIZE)
                        if not chunk:
                            break
                        yield chunk
                        
        except ClientError as e:
            logger.error(f"Failed to stream file from S3: {e}")
            raise

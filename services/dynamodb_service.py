# app_agregation/services/dynamodb_service.py

"""
Amazon DynamoDB service for video metadata management.
Handles connection, CRUD operations, and error logging.
"""

import logging
import uuid
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

import aioboto3
from botocore.exceptions import ClientError

from config.settings import settings
from models.video import VideoMetadata, VideoStatus, VideoCreateRequest, VideoUpdateRequest

logger = logging.getLogger(__name__)


class DynamoDBService:
    """
    Service class for DynamoDB operations on video metadata.
    Provides asynchronous methods to interact with the database.
    """
    
    _session: Optional[aioboto3.Session] = None
    
    @classmethod
    def _get_session(cls) -> aioboto3.Session:
        """Get or create aioboto3 session."""
        if cls._session is None:
            session_kwargs = {}
            
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
    def _get_client_kwargs(cls) -> dict:
        """Get client kwargs including endpoint URL for local development."""
        kwargs = {}
        if settings.DYNAMODB_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.DYNAMODB_ENDPOINT_URL
        return kwargs
    
    @classmethod
    async def connect(cls):
        """
        Initialize DynamoDB connection and create table if needed.
        """
        try:
            session = cls._get_session()
            client_kwargs = cls._get_client_kwargs()
            
            async with session.client("dynamodb", **client_kwargs) as dynamodb:
                # Check if table exists
                try:
                    await dynamodb.describe_table(TableName=settings.DYNAMODB_TABLE_NAME)
                    logger.info(f"DynamoDB table verified: {settings.DYNAMODB_TABLE_NAME}")
                except ClientError as e:
                    if e.response["Error"]["Code"] == "ResourceNotFoundException":
                        # Create table
                        await cls._create_table(dynamodb)
                    else:
                        raise
                        
        except Exception as e:
            logger.error(f"Failed to connect to DynamoDB: {e}")
            raise
    
    @classmethod
    async def _create_table(cls, dynamodb):
        """
        Create the DynamoDB table with necessary indexes.
        """
        logger.info(f"Creating DynamoDB table: {settings.DYNAMODB_TABLE_NAME}")
        
        await dynamodb.create_table(
            TableName=settings.DYNAMODB_TABLE_NAME,
            KeySchema=[
                {"AttributeName": "id", "KeyType": "HASH"}
            ],
            AttributeDefinitions=[
                {"AttributeName": "id", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "source_video_id", "AttributeType": "S"},
                {"AttributeName": "filename", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"}
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "status-created_at-index",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"}
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {
                        "ReadCapacityUnits": 5,
                        "WriteCapacityUnits": 5
                    }
                },
                {
                    "IndexName": "source_video_id-index",
                    "KeySchema": [
                        {"AttributeName": "source_video_id", "KeyType": "HASH"}
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {
                        "ReadCapacityUnits": 5,
                        "WriteCapacityUnits": 5
                    }
                },
                {
                    "IndexName": "filename-index",
                    "KeySchema": [
                        {"AttributeName": "filename", "KeyType": "HASH"}
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {
                        "ReadCapacityUnits": 5,
                        "WriteCapacityUnits": 5
                    }
                }
            ],
            ProvisionedThroughput={
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5
            }
        )
        
        # Wait for table to be created
        waiter = dynamodb.get_waiter("table_exists")
        await waiter.wait(TableName=settings.DYNAMODB_TABLE_NAME)
        
        logger.info(f"DynamoDB table created: {settings.DYNAMODB_TABLE_NAME}")
    
    @classmethod
    async def disconnect(cls):
        """
        Cleanup resources (no persistent connection in DynamoDB).
        """
        logger.info("DynamoDB service disconnected")
    
    @classmethod
    def _serialize_item(cls, data: dict) -> dict:
        """
        Serialize Python dict to DynamoDB item format.
        Converts floats to Decimal and handles None values.
        """
        serialized = {}
        for key, value in data.items():
            if value is None:
                continue
            elif isinstance(value, float):
                serialized[key] = Decimal(str(value))
            elif isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif isinstance(value, VideoStatus):
                serialized[key] = value.value
            else:
                serialized[key] = value
        return serialized
    
    @classmethod
    def _deserialize_item(cls, item: dict) -> dict:
        """
        Deserialize DynamoDB item to Python dict.
        Converts Decimal back to float/int.
        """
        deserialized = {}
        for key, value in item.items():
            if isinstance(value, Decimal):
                # Convert to int if it's a whole number, otherwise float
                if value % 1 == 0:
                    deserialized[key] = int(value)
                else:
                    deserialized[key] = float(value)
            else:
                deserialized[key] = value
        return deserialized
    
    @classmethod
    async def create_video(cls, video_data: VideoCreateRequest) -> VideoMetadata:
        """
        Create a new video metadata entry.
        
        Args:
            video_data: Video creation request data.
            
        Returns:
            VideoMetadata: The created video object with its generated ID.
        """
        try:
            session = cls._get_session()
            client_kwargs = cls._get_client_kwargs()
            
            # Generate unique ID
            video_id = str(uuid.uuid4())
            now = datetime.now()
            
            # Build item
            item = video_data.model_dump()
            item["id"] = video_id
            item["created_at"] = now.isoformat()
            item["updated_at"] = now.isoformat()
            
            # Ensure source_video_id has a value for GSI (use "NONE" as placeholder if null)
            if not item.get("source_video_id"):
                item["source_video_id"] = "NONE"
            
            # Serialize for DynamoDB
            serialized_item = cls._serialize_item(item)
            
            async with session.resource("dynamodb", **client_kwargs) as dynamodb:
                table = await dynamodb.Table(settings.DYNAMODB_TABLE_NAME)
                await table.put_item(Item=serialized_item)
            
            logger.info(f"Video metadata created: {video_data.filename} (ID: {video_id})")
            
            # Return the created item as VideoMetadata
            return VideoMetadata(
                id=video_id,
                filename=video_data.filename,
                file_path=video_data.file_path,
                link=video_data.link,
                status=video_data.status,
                file_size=video_data.file_size,
                source_video_id=video_data.source_video_id,
                created_at=now,
                updated_at=now
            )
            
        except ClientError as e:
            logger.error(f"Failed to create video metadata: {e}")
            raise
    
    @classmethod
    async def update_video(cls, video_id: str, update_data: VideoUpdateRequest) -> Optional[VideoMetadata]:
        """
        Update video metadata by ID.
        
        Args:
            video_id: The video ID.
            update_data: Object containing fields to update.
            
        Returns:
            Optional[VideoMetadata]: The updated object, or None if not found.
        """
        try:
            session = cls._get_session()
            client_kwargs = cls._get_client_kwargs()
            
            # Filter out None values
            update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
            
            if not update_dict:
                return await cls.get_video(video_id)
            
            update_dict["updated_at"] = datetime.now().isoformat()
            
            # Build update expression
            update_expression_parts = []
            expression_attribute_names = {}
            expression_attribute_values = {}
            
            for i, (key, value) in enumerate(update_dict.items()):
                attr_name = f"#attr{i}"
                attr_value = f":val{i}"
                update_expression_parts.append(f"{attr_name} = {attr_value}")
                expression_attribute_names[attr_name] = key
                
                # Serialize value
                if isinstance(value, float):
                    expression_attribute_values[attr_value] = Decimal(str(value))
                elif isinstance(value, VideoStatus):
                    expression_attribute_values[attr_value] = value.value
                else:
                    expression_attribute_values[attr_value] = value
            
            update_expression = "SET " + ", ".join(update_expression_parts)
            
            async with session.resource("dynamodb", **client_kwargs) as dynamodb:
                table = await dynamodb.Table(settings.DYNAMODB_TABLE_NAME)
                
                response = await table.update_item(
                    Key={"id": video_id},
                    UpdateExpression=update_expression,
                    ExpressionAttributeNames=expression_attribute_names,
                    ExpressionAttributeValues=expression_attribute_values,
                    ReturnValues="ALL_NEW"
                )
            
            if response.get("Attributes"):
                logger.info(f"Video metadata updated: ID {video_id}")
                item = cls._deserialize_item(response["Attributes"])
                return VideoMetadata(**item)
            
            return None
            
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning(f"Video not found for update: ID {video_id}")
                return None
            logger.error(f"Failed to update video metadata: {e}")
            raise
    
    @classmethod
    async def get_video(cls, video_id: str) -> Optional[VideoMetadata]:
        """
        Retrieve video metadata by ID.
        
        Args:
            video_id: The video ID.
            
        Returns:
            Optional[VideoMetadata]: The video object, or None if not found.
        """
        try:
            session = cls._get_session()
            client_kwargs = cls._get_client_kwargs()
            
            async with session.resource("dynamodb", **client_kwargs) as dynamodb:
                table = await dynamodb.Table(settings.DYNAMODB_TABLE_NAME)
                response = await table.get_item(Key={"id": video_id})
            
            if "Item" in response:
                item = cls._deserialize_item(response["Item"])
                return VideoMetadata(**item)
            
            return None
            
        except ClientError as e:
            logger.error(f"Failed to retrieve video metadata: {e}")
            raise
    
    @classmethod
    async def get_video_by_filename(cls, filename: str) -> Optional[VideoMetadata]:
        """
        Retrieve video metadata by filename using GSI.
        
        Args:
            filename: The exact filename to search for.
            
        Returns:
            Optional[VideoMetadata]: The video object, or None if not found.
        """
        try:
            session = cls._get_session()
            client_kwargs = cls._get_client_kwargs()
            
            async with session.resource("dynamodb", **client_kwargs) as dynamodb:
                table = await dynamodb.Table(settings.DYNAMODB_TABLE_NAME)
                
                response = await table.query(
                    IndexName="filename-index",
                    KeyConditionExpression="filename = :filename",
                    ExpressionAttributeValues={":filename": filename},
                    Limit=1
                )
            
            items = response.get("Items", [])
            if items:
                item = cls._deserialize_item(items[0])
                return VideoMetadata(**item)
            
            return None
            
        except ClientError as e:
            logger.error(f"Failed to retrieve video by filename: {e}")
            raise
    
    @classmethod
    async def get_video_by_source_id(cls, source_video_id: str) -> Optional[VideoMetadata]:
        """
        Retrieve video metadata by source video ID using GSI.
        
        Args:
            source_video_id: The video ID from vidp-fastapi-service.
            
        Returns:
            Optional[VideoMetadata]: The video object, or None if not found.
        """
        try:
            session = cls._get_session()
            client_kwargs = cls._get_client_kwargs()
            
            async with session.resource("dynamodb", **client_kwargs) as dynamodb:
                table = await dynamodb.Table(settings.DYNAMODB_TABLE_NAME)
                
                response = await table.query(
                    IndexName="source_video_id-index",
                    KeyConditionExpression="source_video_id = :source_id",
                    ExpressionAttributeValues={":source_id": source_video_id},
                    Limit=1
                )
            
            items = response.get("Items", [])
            if items:
                logger.info(f"Found video with source_video_id: {source_video_id}")
                item = cls._deserialize_item(items[0])
                return VideoMetadata(**item)
            
            return None
            
        except ClientError as e:
            logger.error(f"Failed to retrieve video by source_video_id: {e}")
            raise
    
    @classmethod
    async def list_videos(
        cls,
        status: Optional[VideoStatus] = None,
        limit: int = 100
    ) -> List[VideoMetadata]:
        """
        List videos with optional status filter.
        
        Args:
            status: Filter by processing status.
            limit: Maximum number of records to return.
            
        Returns:
            List[VideoMetadata]: A list of video objects.
        """
        try:
            session = cls._get_session()
            client_kwargs = cls._get_client_kwargs()
            
            async with session.resource("dynamodb", **client_kwargs) as dynamodb:
                table = await dynamodb.Table(settings.DYNAMODB_TABLE_NAME)
                
                if status:
                    # Use GSI for status filtering
                    response = await table.query(
                        IndexName="status-created_at-index",
                        KeyConditionExpression="status = :status",
                        ExpressionAttributeValues={":status": status.value},
                        ScanIndexForward=False,  # Sort descending by created_at
                        Limit=limit
                    )
                else:
                    # Scan all items (less efficient but necessary without status filter)
                    response = await table.scan(Limit=limit)
            
            items = response.get("Items", [])
            videos = [VideoMetadata(**cls._deserialize_item(item)) for item in items]
            
            # Sort by created_at if we did a scan
            if not status:
                videos.sort(key=lambda v: v.created_at, reverse=True)
            
            return videos
            
        except ClientError as e:
            logger.error(f"Failed to list videos: {e}")
            raise
    
    @classmethod
    async def delete_video(cls, video_id: str) -> bool:
        """
        Delete video metadata by ID.
        
        Args:
            video_id: The video ID.
            
        Returns:
            bool: True if the document was deleted.
        """
        try:
            session = cls._get_session()
            client_kwargs = cls._get_client_kwargs()
            
            async with session.resource("dynamodb", **client_kwargs) as dynamodb:
                table = await dynamodb.Table(settings.DYNAMODB_TABLE_NAME)
                
                # Check if item exists first
                response = await table.delete_item(
                    Key={"id": video_id},
                    ReturnValues="ALL_OLD"
                )
            
            if response.get("Attributes"):
                logger.info(f"Video metadata deleted: ID {video_id}")
                return True
            else:
                logger.warning(f"Video not found for deletion: ID {video_id}")
                return False
            
        except ClientError as e:
            logger.error(f"Failed to delete video metadata: {e}")
            raise
    
    @classmethod
    async def is_connected(cls) -> bool:
        """
        Check if DynamoDB is accessible.
        
        Returns:
            bool: True if connected and table exists.
        """
        try:
            session = cls._get_session()
            client_kwargs = cls._get_client_kwargs()
            
            async with session.client("dynamodb", **client_kwargs) as dynamodb:
                await dynamodb.describe_table(TableName=settings.DYNAMODB_TABLE_NAME)
            return True
        except Exception:
            return False

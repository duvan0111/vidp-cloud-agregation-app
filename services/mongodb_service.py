# app_agregation/services/mongodb_service.py

"""
MongoDB service for video metadata management.
Handles connection, CRUD operations, and error logging.
"""

import asyncio
import logging
import ssl
from typing import Optional, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
from bson import ObjectId

from config.settings import settings
from models.video import VideoMetadata, VideoStatus, VideoCreateRequest, VideoUpdateRequest

logger = logging.getLogger(__name__)

class MongoDBService:
    """
    Service class for MongoDB operations on video metadata.
    Provides asynchronous methods to interact with the database.
    """
    
    _client: Optional[AsyncIOMotorClient] = None
    _database: Optional[AsyncIOMotorDatabase] = None
    
    @classmethod
    async def connect(cls):
        """
        Establish connection to MongoDB.
        
        Configures the client with appropriate timeouts and SSL settings 
        (if connecting to Atlas). Creates indexes upon successful connection.
        
        Raises:
            Exception: If connection fails or service is unreachable.
        """
        try:
            # Base connection options
            connection_options = {
                "serverSelectionTimeoutMS": 5000,
                "connectTimeoutMS": 10000,
                "socketTimeoutMS": 10000,
            }
            
            # Add SSL/TLS options ONLY if connecting to Atlas (Remote)
            if "mongodb+srv://" in settings.MONGODB_URL or "mongodb.net" in settings.MONGODB_URL:
                import certifi
                
                ssl_context = ssl.create_default_context(cafile=certifi.where())
                ssl_context.check_hostname = True
                ssl_context.verify_mode = ssl.CERT_REQUIRED
                
                connection_options.update({
                    "tls": True,
                    "tlsCAFile": certifi.where(),
                })
            
            cls._client = AsyncIOMotorClient(settings.MONGODB_URL, **connection_options)
            cls._database = cls._client[settings.MONGODB_DATABASE]
            
            # Simple ping to verify connection
            await cls._client.admin.command('ping')
            
            logger.info(f"Connected to MongoDB: {settings.MONGODB_DATABASE}")
            
            # Create indexes
            await cls._create_indexes()
            
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB. Ensure the service is running. Error: {e}")
            raise
    
    @classmethod
    async def disconnect(cls):
        """
        Close MongoDB connection.
        Should be called during application shutdown.
        """
        if cls._client:
            cls._client.close()
            logger.info("Disconnected from MongoDB")
    
    @classmethod
    async def _create_indexes(cls):
        """
        Create necessary indexes for the collection.
        Optimizes queries by filename, status, creation date, and source_video_id.
        """
        if cls._database is None:
            return

        collection = cls._database[settings.MONGODB_COLLECTION]
        
        await collection.create_index("filename")
        await collection.create_index("status")
        await collection.create_index("created_at")
        await collection.create_index("source_video_id")  # Index for cross-database lookup
        
        logger.info("Database indexes created successfully")
    
    @classmethod
    async def create_video(cls, video_data: VideoCreateRequest) -> VideoMetadata:
        """
        Create a new video metadata entry.
        
        Args:
            video_data: Video creation request data containing filename and path.
            
        Returns:
            VideoMetadata: The created video object with its generated ID.
            
        Raises:
            PyMongoError: If insertion fails.
        """
        try:
            collection = cls._database[settings.MONGODB_COLLECTION]
            
            video_dict = video_data.model_dump()
            
            # Set timestamps
            now = datetime.now()
            video_dict["created_at"] = now
            video_dict["updated_at"] = now
            
            result = await collection.insert_one(video_dict)
            
            # Fetch the created document to return it complete
            created_video = await collection.find_one({"_id": result.inserted_id})
            
            logger.info(f"Video metadata created: {video_data.filename} (ID: {result.inserted_id})")
            
            return VideoMetadata(**created_video)
            
        except PyMongoError as e:
            logger.error(f"Failed to create video metadata: {e}")
            raise
    
    @classmethod
    async def update_video(cls, video_id: str, update_data: VideoUpdateRequest) -> Optional[VideoMetadata]:
        """
        Update video metadata by ID.
        
        Args:
            video_id: The MongoDB ObjectId as a string.
            update_data: Object containing fields to update.
            
        Returns:
            Optional[VideoMetadata]: The updated object, or None if not found.
        """
        try:
            collection = cls._database[settings.MONGODB_COLLECTION]
            
            # Filter out None values to only update provided fields
            update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
            
            if not update_dict:
                return await cls.get_video(video_id)

            update_dict["updated_at"] = datetime.now()
            
            result = await collection.find_one_and_update(
                {"_id": ObjectId(video_id)},
                {"$set": update_dict},
                return_document=True
            )
            
            if result:
                logger.info(f"Video metadata updated: ID {video_id}")
                return VideoMetadata(**result)
            else:
                logger.warning(f"Video not found for update: ID {video_id}")
                return None
                
        except PyMongoError as e:
            logger.error(f"Failed to update video metadata: {e}")
            raise
    
    @classmethod
    async def get_video(cls, video_id: str) -> Optional[VideoMetadata]:
        """
        Retrieve video metadata by ID.
        
        Args:
            video_id: The MongoDB ObjectId as a string.
            
        Returns:
            Optional[VideoMetadata]: The video object, or None if not found.
        """
        try:
            collection = cls._database[settings.MONGODB_COLLECTION]
            
            try:
                oid = ObjectId(video_id)
            except Exception:
                # Invalid ID format returns None immediately
                return None

            video = await collection.find_one({"_id": oid})
            
            if video:
                return VideoMetadata(**video)
            return None
            
        except PyMongoError as e:
            logger.error(f"Failed to retrieve video metadata: {e}")
            raise
    
    @classmethod
    async def get_video_by_filename(cls, filename: str) -> Optional[VideoMetadata]:
        """
        Retrieve video metadata by filename.
        
        Args:
            filename: The exact filename to search for.
            
        Returns:
            Optional[VideoMetadata]: The video object, or None if not found.
        """
        try:
            collection = cls._database[settings.MONGODB_COLLECTION]
            
            video = await collection.find_one({"filename": filename})
            
            if video:
                return VideoMetadata(**video)
            return None
            
        except PyMongoError as e:
            logger.error(f"Failed to retrieve video by filename: {e}")
            raise
    
    @classmethod
    async def get_video_by_source_id(cls, source_video_id: str) -> Optional[VideoMetadata]:
        """
        Retrieve video metadata by source video ID from the main service.
        
        Args:
            source_video_id: The video ID from vidp-fastapi-service.
            
        Returns:
            Optional[VideoMetadata]: The video object, or None if not found.
        """
        try:
            collection = cls._database[settings.MONGODB_COLLECTION]
            
            video = await collection.find_one({"source_video_id": source_video_id})
            
            if video:
                logger.info(f"Found video with source_video_id: {source_video_id}")
                return VideoMetadata(**video)
            return None
            
        except PyMongoError as e:
            logger.error(f"Failed to retrieve video by source_video_id: {e}")
            raise
            raise
    
    @classmethod
    async def list_videos(cls, status: Optional[VideoStatus] = None, limit: int = 100) -> List[VideoMetadata]:
        """
        List videos with optional status filter.
        
        Args:
            status: Filter by processing status (e.g., 'saved', 'pending').
            limit: Maximum number of records to return (default 100).
            
        Returns:
            List[VideoMetadata]: A list of video objects sorted by creation date (newest first).
        """
        try:
            collection = cls._database[settings.MONGODB_COLLECTION]
            
            query = {}
            if status:
                query["status"] = status
            
            cursor = collection.find(query).sort("created_at", -1).limit(limit)
            videos = await cursor.to_list(length=limit)
            
            return [VideoMetadata(**video) for video in videos]
            
        except PyMongoError as e:
            logger.error(f"Failed to list videos: {e}")
            raise
    
    @classmethod
    async def delete_video(cls, video_id: str) -> bool:
        """
        Delete video metadata by ID.
        
        Args:
            video_id: The MongoDB ObjectId as a string.
            
        Returns:
            bool: True if the document was deleted, False if not found.
        """
        try:
            collection = cls._database[settings.MONGODB_COLLECTION]
            
            try:
                oid = ObjectId(video_id)
            except Exception:
                return False

            result = await collection.delete_one({"_id": oid})
            
            if result.deleted_count > 0:
                logger.info(f"Video metadata deleted: ID {video_id}")
                return True
            else:
                logger.warning(f"Video not found for deletion: ID {video_id}")
                return False
                
        except PyMongoError as e:
            logger.error(f"Failed to delete video metadata: {e}")
            raise
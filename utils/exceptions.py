# app_agregation/utils/exceptions.py
"""Custom exception classes for better error handling."""

from fastapi import HTTPException


class ServiceError(Exception):
    """Base exception for service-related errors."""
    pass


class SubtitleServiceError(ServiceError):
    """Raised when subtitle service fails."""
    pass


class CompressionServiceError(ServiceError):
    """Raised when compression service fails."""
    pass


class FFmpegError(ServiceError):
    """Raised when FFmpeg processing fails."""
    pass


class FileProcessingError(ServiceError):
    """Raised when file operations fail."""
    pass


def handle_service_error(error: Exception, service_name: str) -> HTTPException:
    """
    Convert service errors to appropriate HTTP exceptions.
    
    Args:
        error: The original exception
        service_name: Name of the service that failed
        
    Returns:
        HTTPException with appropriate status code and detail
    """
    if isinstance(error, HTTPException):
        return error
    
    error_mapping = {
        SubtitleServiceError: (502, f"{service_name} subtitle generation failed"),
        CompressionServiceError: (502, f"{service_name} compression failed"),
        FFmpegError: (500, f"{service_name} video processing failed"),
        FileProcessingError: (500, f"{service_name} file operation failed"),
    }
    
    for exc_type, (status_code, message) in error_mapping.items():
        if isinstance(error, exc_type):
            return HTTPException(
                status_code=status_code,
                detail=f"{message}: {str(error)}"
            )
    
    # Generic error
    return HTTPException(
        status_code=500,
        detail=f"{service_name} encountered an unexpected error: {str(error)}"
    )
# app_agregation/utils/file_utils.py

"""
Utility functions for file operations and video processing.
"""

import os
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


def cleanup_files(file_paths: List[Path]) -> None:
    """
    Delete temporary files safely.
    
    Args:
        file_paths: List of file paths to delete
    """
    for file_path in file_paths:
        try:
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
                logger.info(f"Cleaned up file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to delete file {file_path}: {e}")


def validate_file_size(file_path: Path, max_size: int) -> bool:
    """
    Validate that a file does not exceed maximum size.
    
    Args:
        file_path: Path to file
        max_size: Maximum allowed size in bytes
        
    Returns:
        True if file is within size limit, False otherwise
    """
    if not file_path.exists():
        return False
    
    file_size = file_path.stat().st_size
    return file_size <= max_size


def get_video_info(video_path: Path) -> Dict[str, Optional[str]]:
    """
    Extract video information using ffprobe.
    
    Args:
        video_path: Path to video file
        
    Returns:
        Dictionary with duration and resolution
    """
    info = {
        "duration": None,
        "resolution": None
    }
    
    try:
        # Get duration
        duration_cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        
        duration_result = subprocess.run(
            duration_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if duration_result.returncode == 0 and duration_result.stdout.strip():
            info["duration"] = float(duration_result.stdout.strip())
        
        # Get resolution
        resolution_cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(video_path)
        ]
        
        resolution_result = subprocess.run(
            resolution_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if resolution_result.returncode == 0 and resolution_result.stdout.strip():
            info["resolution"] = resolution_result.stdout.strip()
        
        logger.info(f"Extracted video info: {info}")
        
    except subprocess.TimeoutExpired:
        logger.error("ffprobe command timed out")
    except Exception as e:
        logger.error(f"Failed to extract video info: {e}")
    
    return info


def validate_video_extension(filename: str, allowed_extensions: List[str]) -> bool:
    """
    Validate that a filename has an allowed extension.
    
    Args:
        filename: Name of file to validate
        allowed_extensions: List of allowed extensions (e.g., ['.mp4', '.avi'])
        
    Returns:
        True if extension is allowed, False otherwise
    """
    file_ext = Path(filename).suffix.lower()
    return file_ext in allowed_extensions
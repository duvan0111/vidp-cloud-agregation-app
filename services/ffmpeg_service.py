# app_agregation/services/ffmpeg_service.py

"""
FFmpeg service for local video processing.
Handles video manipulation tasks including subtitle burning and metadata extraction.
"""

import asyncio
import logging
import json
import subprocess
import os
import shutil
import tempfile
import ctypes
from pathlib import Path
from typing import Optional, Dict, Any

from config.settings import settings
from utils.exceptions import FFmpegError

logger = logging.getLogger(__name__)

class FFmpegService:
    """
    Handles FFmpeg operations for video processing.
    """

    @staticmethod
    def _validate_srt_content(srt_path: str) -> bool:
        """
        Check if the SRT file contains valid subtitle data.
        
        Returns:
            bool: True if the SRT has content, False if empty/invalid (will skip subtitle burning)
        """
        try:
            with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(1024).strip()
            
            if not content:
                logger.info(f"SRT file is empty: {srt_path} - will process video without subtitles")
                return False

            if content.startswith('{') and '"status":' in content:
                logger.warning("SRT file contains JSON data, not subtitle text - will process video without subtitles")
                return False
            
            return True

        except FileNotFoundError:
            logger.warning(f"SRT file missing during validation: {srt_path} - will process video without subtitles")
            return False
        except Exception as e:
            logger.warning(f"Skipping strict SRT validation due to read error: {e} - will process video without subtitles")
            return False

    @staticmethod
    def _get_windows_short_path(long_path: str) -> str:
        """
        Converts a Windows path with spaces to a DOS 8.3 short path.
        Example: "D:/My Folder/File.txt" -> "D:/MYFOLD~1/File.txt"
        This eliminates spaces, making the path safe for FFmpeg filters.
        """
        if os.name != 'nt':
            return long_path

        try:
            # Prepare buffer for the short path
            output_buf_size = ctypes.windll.kernel32.GetShortPathNameW(long_path, None, 0)
            if output_buf_size == 0:
                # If conversion fails, return original (might be already short or invalid)
                return long_path
                
            output_buf = ctypes.create_unicode_buffer(output_buf_size)
            ctypes.windll.kernel32.GetShortPathNameW(long_path, output_buf, output_buf_size)
            return output_buf.value
        except Exception as e:
            logger.warning(f"Failed to convert to short path: {e}")
            return long_path

    @staticmethod
    def _get_ffmpeg_safe_path(path: str) -> str:
        """
        Standardizes path for FFmpeg filters.
        """
        # 1. Get the 8.3 Short Path (Removes spaces/special chars)
        safe_path = FFmpegService._get_windows_short_path(path)
        
        # 2. Normalize slashes (FFmpeg prefers forward slashes)
        safe_path = safe_path.replace('\\', '/')
        
        # 3. Escape the drive letter colon (C: -> C\:)
        # This is CRITICAL for the 'subtitles' filter
        safe_path = safe_path.replace(':', '\\:')
        
        # 4. Escape single quotes just in case
        safe_path = safe_path.replace("'", "'\\''")
        
        return safe_path

    @staticmethod
    def get_video_metadata(file_path: str) -> Dict[str, Any]:
        """
        Extracts metadata using ffprobe.
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            
            format_info = data.get('format', {})
            video_stream = next((s for s in data.get('streams', []) if s['codec_type'] == 'video'), {})
            
            return {
                'duration': float(format_info.get('duration', 0)),
                'size': int(format_info.get('size', 0)),
                'resolution': f"{video_stream.get('width')}x{video_stream.get('height')}",
                'codec': video_stream.get('codec_name')
            }
        except Exception as e:
            logger.error(f"Metadata extraction failed: {str(e)}")
            return {
                "resolution": "unknown",
                "duration": 0.0,
                "size": 0,
                "codec": "unknown"
            }

    @staticmethod
    async def burn_subtitles(
        video_path: str,
        srt_path: str,
        output_path: str,
        resolution: str = "1280x720",
        crf: int = 23,
        preset: Optional[str] = None
    ) -> None:
        """
        Burn subtitles into video using FFmpeg.
        
        If the SRT file is empty or invalid, the video will be processed without subtitles.
        
        Strategy: Use Windows Short Paths (8.3) to bypass space/character issues
        and strictly escape the drive letter colon.
        """
        # 1. Resolve Absolute Paths
        abs_video_path = str(Path(video_path).resolve())
        abs_srt_path = str(Path(srt_path).resolve())
        abs_output_path = str(Path(output_path).resolve())
        
        if not os.path.exists(abs_video_path):
            raise FFmpegError(f"Video file not found: {abs_video_path}")
        
        # Check if SRT has valid content
        has_subtitles = FFmpegService._validate_srt_content(abs_srt_path)

        preset = preset or settings.FFMPEG_PRESET
        codec = settings.FFMPEG_CODEC

        if has_subtitles:
            # Process with subtitles
            # 2. Create a Temp SRT (Just to be safe and clean)
            temp_srt_fd, temp_srt_path = tempfile.mkstemp(suffix='.srt', text=True)
            os.close(temp_srt_fd)
            
            try:
                # Copy content to temp file
                shutil.copy2(abs_srt_path, temp_srt_path)
                
                # 3. Get the "Safe" path (Short path + Escaped Colon)
                # This turns "D:\M2 DS\temp.srt" into "D\:/M2DS~1/temp.srt"
                filter_srt_path = FFmpegService._get_ffmpeg_safe_path(temp_srt_path)

                vf_filter = (
                    f"subtitles='{filter_srt_path}':force_style='Fontsize=24,PrimaryColour=&H00FFFFFF,BackColour=&H80000000,BorderStyle=3',"
                    f"scale={resolution}"
                )

                cmd = [
                    'ffmpeg',
                    '-y',
                    '-i', abs_video_path,
                    '-vf', vf_filter,
                    '-c:v', codec,
                    '-crf', str(crf),
                    '-preset', preset,
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    abs_output_path
                ]

                logger.info(f"Starting FFmpeg burn with subtitles: {os.path.basename(abs_video_path)}")
                logger.debug(f"Subtitle Filter Path: {filter_srt_path}")

                # 4. Execute
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    logger.error(f"FFmpeg Exit Code: {process.returncode}")
                    error_log = stderr.decode('utf-8', errors='replace')
                    tail_log = '\n'.join(error_log.splitlines()[-20:])
                    logger.error(f"FFmpeg Log Tail:\n{tail_log}")
                    raise FFmpegError(f"FFmpeg processing failed: {tail_log}")
                    
                if not os.path.exists(abs_output_path):
                    raise FFmpegError("Output file missing after FFmpeg run")
                    
                logger.info(f"Successfully burned subtitles: {os.path.basename(abs_output_path)}")

            except Exception as e:
                if isinstance(e, FFmpegError):
                    raise
                logger.error(f"FFmpeg execution failed: {str(e)}")
                raise FFmpegError(f"FFmpeg execution failed: {str(e)}")
            
            finally:
                # 5. Clean up temp SRT
                if os.path.exists(temp_srt_path):
                    try:
                        os.remove(temp_srt_path)
                    except OSError:
                        pass
        else:
            # Process WITHOUT subtitles (video has no audio / empty SRT)
            logger.info(f"Processing video WITHOUT subtitles: {os.path.basename(abs_video_path)}")
            
            vf_filter = f"scale={resolution}"

            cmd = [
                'ffmpeg',
                '-y',
                '-i', abs_video_path,
                '-vf', vf_filter,
                '-c:v', codec,
                '-crf', str(crf),
                '-preset', preset,
                '-c:a', 'aac',
                '-b:a', '128k',
                abs_output_path
            ]

            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    logger.error(f"FFmpeg Exit Code: {process.returncode}")
                    error_log = stderr.decode('utf-8', errors='replace')
                    tail_log = '\n'.join(error_log.splitlines()[-20:])
                    logger.error(f"FFmpeg Log Tail:\n{tail_log}")
                    raise FFmpegError(f"FFmpeg processing failed: {tail_log}")
                    
                if not os.path.exists(abs_output_path):
                    raise FFmpegError("Output file missing after FFmpeg run")
                    
                logger.info(f"Successfully processed video (no subtitles): {os.path.basename(abs_output_path)}")

            except Exception as e:
                if isinstance(e, FFmpegError):
                    raise
                logger.error(f"FFmpeg execution failed: {str(e)}")
                raise FFmpegError(f"FFmpeg execution failed: {str(e)}")

    # Alias for compatibility
    embed_subtitles = burn_subtitles
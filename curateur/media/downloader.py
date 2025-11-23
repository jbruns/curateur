"""
Image downloader with validation.

Downloads images from URLs with retry logic and validates them using Pillow.
"""

import asyncio
import os
from pathlib import Path
from typing import Optional, Tuple
import httpx
from PIL import Image
from io import BytesIO


class DownloadError(Exception):
    """Base exception for download errors."""
    pass


class ValidationError(Exception):
    """Exception raised when image validation fails."""
    pass


class ImageDownloader:
    """
    Downloads and validates image files.
    
    Features:
    - HTTP download with configurable timeout
    - Retry logic with exponential backoff
    - Image validation with Pillow
    - Minimum dimension checking
    """
    
    def __init__(
        self,
        client: httpx.AsyncClient,
        timeout: int = 30,
        max_retries: int = 3,
        min_width: int = 50,
        min_height: int = 50,
        validation_mode: str = 'disabled'
    ):
        """
        Initialize image downloader.
        
        Args:
            client: httpx.AsyncClient for HTTP requests
            timeout: HTTP request timeout in seconds
            max_retries: Maximum number of retry attempts
            min_width: Minimum acceptable image width in pixels
            min_height: Minimum acceptable image height in pixels
            validation_mode: Validation mode (disabled, normal, strict)
        """
        self.client = client
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_width = min_width
        self.min_height = min_height
        self.validation_mode = validation_mode
    
    async def download(
        self,
        url: str,
        output_path: Path,
        validate: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Download an image from URL to output path.
        
        Args:
            url: Image URL to download
            output_path: Path where image should be saved
            validate: Whether to validate image after download
            
        Returns:
            Tuple of (success: bool, error_message: str or None)
            
        Example:
            success, error = await downloader.download(
                'https://example.com/image.jpg',
                Path('covers/game.jpg')
            )
            if not success:
                print(f"Download failed: {error}")
        """
        # Create parent directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Attempt download with retries
        for attempt in range(self.max_retries):
            try:
                # Download image data
                image_data = await self._download_with_retry(url, attempt)
                
                # Validate if requested and validation mode is not disabled
                if validate and self.validation_mode != 'disabled':
                    is_valid, validation_error = self._validate_image_data(image_data)
                    if not is_valid:
                        if attempt < self.max_retries - 1:
                            # Retry on validation failure
                            continue
                        return False, f"Validation failed: {validation_error}"
                
                # Write to temporary file first
                temp_path = output_path.with_suffix(output_path.suffix + '.tmp')
                try:
                    with open(temp_path, 'wb') as f:
                        f.write(image_data)
                    # Move to final location only on success
                    temp_path.rename(output_path)
                except Exception as e:
                    # Clean up temp file on error
                    if temp_path.exists():
                        temp_path.unlink()
                    raise
                
                return True, None
                
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                if attempt == self.max_retries - 1:
                    return False, f"Download failed after {self.max_retries} attempts: {e}"
                
                # Wait before retry with async sleep
                delay = 2 ** attempt
                await asyncio.sleep(delay)
            
            except Exception as e:
                return False, f"Unexpected error: {e}"
        
        return False, "Download failed (max retries exceeded)"
    
    async def _download_with_retry(self, url: str, attempt: int) -> bytes:
        """
        Download image data from URL.
        
        Args:
            url: Image URL
            attempt: Current attempt number (for logging)
            
        Returns:
            Image data as bytes
            
        Raises:
            httpx.HTTPError: If download fails
        """
        response = await self.client.get(
            url, 
            timeout=self.timeout,
            headers={'User-Agent': 'curateur/1.0.0'}
        )
        response.raise_for_status()
        
        # Check content type only if validation is enabled
        if self.validation_mode != 'disabled':
            content_type = response.headers.get('Content-Type', '')
            allowed_types = ['image/', 'application/pdf', 'video/', 'application/force-download', 'application/octet-stream']
            if not any(content_type.startswith(t) for t in allowed_types):
                raise DownloadError(f"Invalid content type: {content_type}")
        
        return response.content
    
    def _validate_image_data(self, image_data: bytes) -> Tuple[bool, Optional[str]]:
        """
        Validate image data using Pillow.
        
        Checks:
        - Valid image format
        - Minimum dimensions
        
        Args:
            image_data: Raw image bytes
            
        Returns:
            Tuple of (is_valid: bool, error_message: str or None)
        """
        try:
            # Try to open image
            img = Image.open(BytesIO(image_data))
            
            # Verify image can be loaded
            img.verify()
            
            # Reopen to get dimensions (verify() invalidates the image)
            img = Image.open(BytesIO(image_data))
            width, height = img.size
            
            # Check minimum dimensions
            if width < self.min_width or height < self.min_height:
                return False, (
                    f"Image too small: {width}x{height} "
                    f"(minimum: {self.min_width}x{self.min_height})"
                )
            
            return True, None
            
        except Exception as e:
            return False, f"Invalid image: {e}"
    
    def validate_existing_file(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Validate an existing image file.
        
        Args:
            file_path: Path to image file
            
        Returns:
            Tuple of (is_valid: bool, error_message: str or None)
        """
        if not file_path.exists():
            return False, "File does not exist"
        
        try:
            with open(file_path, 'rb') as f:
                image_data = f.read()
            
            return self._validate_image_data(image_data)
            
        except Exception as e:
            return False, f"Could not read file: {e}"
    
    def get_image_dimensions(self, file_path: Path) -> Optional[Tuple[int, int]]:
        """
        Get dimensions of an image file.
        
        Args:
            file_path: Path to image file
            
        Returns:
            Tuple of (width, height) or None if file cannot be read
        """
        try:
            with Image.open(file_path) as img:
                return img.size
        except Exception:
            return None

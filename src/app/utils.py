"""
Utility functions for the application.
"""
import os
import hashlib
import uuid
import json
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
import random
import string
import subprocess
import tempfile

from core.exceptions import ValidationError

def generate_id(prefix: str = '') -> str:
    """
    Generate a unique ID with optional prefix.
    
    Args:
        prefix: Prefix for the ID
        
    Returns:
        Unique ID string
    """
    uid = str(uuid.uuid4()).replace('-', '')
    return f"{prefix}{uid}" if prefix else uid

def hash_string(data: str) -> str:
    """
    Create SHA-256 hash of a string.
    
    Args:
        data: String to hash
        
    Returns:
        SHA-256 hash
    """
    return hashlib.sha256(data.encode()).hexdigest()

def format_file_size(bytes_size: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        bytes_size: Size in bytes
        
    Returns:
        Human-readable size string
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"

def format_duration(seconds: float) -> str:
    """
    Format duration in human-readable format.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Human-readable duration string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to remove unsafe characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove directory traversal attempts
    filename = os.path.basename(filename)
    
    # Remove null bytes
    filename = filename.replace('\x00', '')
    
    # Remove potentially dangerous characters
    dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '\\', '/']
    for char in dangerous_chars:
        filename = filename.replace(char, '_')
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext
    
    return filename

def get_file_extension(filename: str) -> str:
    """
    Get file extension from filename.
    
    Args:
        filename: Filename
        
    Returns:
        File extension (with dot)
    """
    return os.path.splitext(filename)[1].lower()

def get_mime_type(filename: str) -> str:
    """
    Get MIME type for a file.
    
    Args:
        filename: Filename
        
    Returns:
        MIME type string
    """
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'

def create_temp_file(extension: str = '.tmp', content: bytes = None) -> str:
    """
    Create a temporary file.
    
    Args:
        extension: File extension
        content: Optional content to write
        
    Returns:
        Path to temporary file
    """
    fd, temp_path = tempfile.mkstemp(suffix=extension)
    os.close(fd)
    
    if content:
        with open(temp_path, 'wb') as f:
            f.write(content)
    
    return temp_path

def read_json_file(file_path: str) -> Dict[str, Any]:
    """
    Read JSON file.
    
    Args:
        file_path: Path to JSON file
        
    Returns:
        Parsed JSON data
    """
    with open(file_path, 'r') as f:
        return json.load(f)

def write_json_file(file_path: str, data: Dict[str, Any]) -> None:
    """
    Write JSON file.
    
    Args:
        file_path: Path to JSON file
        data: Data to write
    """
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

def parse_duration_string(duration_str: str) -> float:
    """
    Parse duration string to seconds.
    
    Args:
        duration_str: Duration string (e.g., "1h30m", "90s")
        
    Returns:
        Duration in seconds
    """
    import re
    
    total_seconds = 0.0
    pattern = r'(\d+(?:\.\d+)?)([hms])'
    
    matches = re.findall(pattern, duration_str)
    for value, unit in matches:
        value = float(value)
        if unit == 'h':
            total_seconds += value * 3600
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 's':
            total_seconds += value
    
    return total_seconds

def format_datetime(dt: datetime, format_str: str = None) -> str:
    """
    Format datetime to string.
    
    Args:
        dt: Datetime object
        format_str: Format string (default: ISO format)
        
    Returns:
        Formatted datetime string
    """
    if format_str:
        return dt.strftime(format_str)
    return dt.isoformat()

def parse_datetime(dt_str: str) -> datetime:
    """
    Parse datetime from string.
    
    Args:
        dt_str: Datetime string
        
    Returns:
        Datetime object
    """
    # Try ISO format first
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except ValueError:
        pass
    
    # Try common formats
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y/%m/%d %H:%M:%S',
        '%d/%m/%Y %H:%M:%S'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    
    raise ValidationError(f"Unable to parse datetime: {dt_str}")

def calculate_cost(video_length: float, tier: str, is_silent: bool = False) -> float:
    """
    Calculate estimated processing cost.
    
    Args:
        video_length: Video length in seconds
        tier: User tier
        is_silent: Whether video is silent
        
    Returns:
        Estimated cost in USD
    """
    # Base costs per minute
    speech_cost_per_minute = 0.006  # $0.006 per minute for transcription
    silent_cost_per_minute = 0.002  # $0.002 per minute for silent processing
    
    # Tier multipliers
    tier_multipliers = {
        'free': 1.0,
        'starter': 1.0,
        'pro': 1.2,  # Higher quality processing
        'plus': 1.5,  # Premium features
        'enterprise': 2.0  # Highest quality
    }
    
    # Calculate base cost
    minutes = video_length / 60
    if is_silent:
        base_cost = minutes * silent_cost_per_minute
    else:
        base_cost = minutes * speech_cost_per_minute
    
    # Apply tier multiplier
    multiplier = tier_multipliers.get(tier, 1.0)
    estimated_cost = base_cost * multiplier
    
    # Add minimum cost
    estimated_cost = max(estimated_cost, 0.001)  # Minimum $0.001
    
    return round(estimated_cost, 4)

def generate_password(length: int = 12) -> str:
    """
    Generate a secure random password.
    
    Args:
        length: Password length
        
    Returns:
        Secure password
    """
    # Character sets
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    symbols = '!@#$%^&*()_+-=[]{}|;:,.<>?'
    
    # Ensure at least one character from each set
    password = [
        random.choice(lowercase),
        random.choice(uppercase),
        random.choice(digits),
        random.choice(symbols)
    ]
    
    # Fill the rest with random characters
    all_chars = lowercase + uppercase + digits + symbols
    password += [random.choice(all_chars) for _ in range(length - 4)]
    
    # Shuffle the password
    random.shuffle(password)
    
    return ''.join(password)

def validate_email(email: str) -> bool:
    """
    Validate email address format.
    
    Args:
        email: Email address
        
    Returns:
        True if email is valid
    """
    import re
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def truncate_text(text: str, max_length: int, suffix: str = '...') -> str:
    """
    Truncate text to maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix

def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """
    Split list into chunks.
    
    Args:
        lst: List to chunk
        chunk_size: Size of each chunk
        
    Returns:
        List of chunks
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def merge_dicts(dict1: Dict, dict2: Dict) -> Dict:
    """
    Merge two dictionaries recursively.
    
    Args:
        dict1: First dictionary
        dict2: Second dictionary
        
    Returns:
        Merged dictionary
    """
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    
    return result

def get_system_info() -> Dict[str, Any]:
    """
    Get system information.
    
    Returns:
        System information dictionary
    """
    import platform
    import psutil
    
    return {
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'cpu_count': psutil.cpu_count(),
        'total_memory': psutil.virtual_memory().total,
        'available_memory': psutil.virtual_memory().available,
        'disk_usage': psutil.disk_usage('/').percent,
        'boot_time': psutil.boot_time(),
        'process_id': os.getpid()
    }

def execute_command(cmd: List[str], timeout: int = 30) -> Dict[str, Any]:
    """
    Execute shell command with timeout.
    
    Args:
        cmd: Command to execute
        timeout: Timeout in seconds
        
    Returns:
        Command execution result
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True
        )
        
        return {
            'success': True,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'return_code': result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': 'Command timed out',
            'stdout': '',
            'stderr': '',
            'return_code': -1
        }
    except subprocess.CalledProcessError as e:
        return {
            'success': False,
            'error': str(e),
            'stdout': e.stdout,
            'stderr': e.stderr,
            'return_code': e.returncode
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'stdout': '',
            'stderr': '',
            'return_code': -1
        }

def retry_with_backoff(func, max_retries: int = 3, base_delay: float = 1.0):
    """
    Retry function with exponential backoff.
    
    Args:
        func: Function to retry
        max_retries: Maximum number of retries
        base_delay: Base delay in seconds
        
    Returns:
        Function result
    """
    import time
    
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
    
    raise Exception("Max retries exceeded")

class Timer:
    """Simple timer context manager."""
    
    def __enter__(self):
        self.start = datetime.utcnow()
        return self
    
    def __exit__(self, *args):
        self.end = datetime.utcnow()
        self.elapsed = self.end - self.start
    
    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds."""
        return self.elapsed.total_seconds()
    
    @property
    def elapsed_milliseconds(self) -> float:
        """Get elapsed time in milliseconds."""
        return self.elapsed.total_seconds() * 1000
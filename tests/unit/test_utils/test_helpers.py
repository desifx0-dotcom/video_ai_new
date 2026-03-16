"""
Unit tests for helper functions.
"""
import pytest
from datetime import datetime
import tempfile
import os

from app.utils import (
    generate_id, hash_string, format_file_size,
    format_duration, sanitize_filename, get_file_extension,
    get_mime_type, create_temp_file, read_json_file,
    write_json_file, parse_duration_string, format_datetime,
    parse_datetime, calculate_cost, generate_password,
    validate_email, truncate_text, chunk_list, merge_dicts,
    get_system_info, execute_command, Timer
)

class TestHelpers:
    """Test helper functions."""
    
    def test_generate_id(self):
        """Test ID generation."""
        id1 = generate_id()
        id2 = generate_id()
        id3 = generate_id("user_")
        
        assert isinstance(id1, str)
        assert len(id1) == 32  # UUID without dashes
        assert id1 != id2
        assert id3.startswith("user_")
    
    def test_hash_string(self):
        """Test string hashing."""
        hash1 = hash_string("test")
        hash2 = hash_string("test")
        hash3 = hash_string("different")
        
        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA-256 hex length
        assert hash1 == hash2
        assert hash1 != hash3
    
    def test_format_file_size(self):
        """Test file size formatting."""
        assert format_file_size(500) == "500.00 B"
        assert format_file_size(1500) == "1.46 KB"
        assert format_file_size(1500000) == "1.43 MB"
        assert format_file_size(1500000000) == "1.40 GB"
        assert format_file_size(1500000000000) == "1.36 TB"
    
    def test_format_duration(self):
        """Test duration formatting."""
        assert format_duration(45.5) == "45.5s"
        assert format_duration(90) == "1.5m"
        assert format_duration(7200) == "2.0h"
    
    def test_sanitize_filename(self):
        """Test filename sanitization."""
        # Remove directory traversal
        assert sanitize_filename("../../../etc/passwd") == "etc_passwd"
        
        # Remove dangerous characters
        assert sanitize_filename("file<name>.txt") == "file_name_.txt"
        assert sanitize_filename("file:name.txt") == "file_name.txt"
        assert sanitize_filename('file"name".txt') == "file_name_.txt"
        
        # Preserve safe characters
        assert sanitize_filename("file-name.txt") == "file-name.txt"
        assert sanitize_filename("file_name.txt") == "file_name.txt"
        
        # Limit length
        long_name = "a" * 300 + ".txt"
        sanitized = sanitize_filename(long_name)
        assert len(sanitized) <= 255
        assert sanitized.endswith(".txt")
    
    def test_get_file_extension(self):
        """Test file extension extraction."""
        assert get_file_extension("video.mp4") == ".mp4"
        assert get_file_extension("document.pdf") == ".pdf"
        assert get_file_extension("no_extension") == ""
        assert get_file_extension(".hidden") == ""
        assert get_file_extension("archive.tar.gz") == ".gz"
    
    def test_get_mime_type(self):
        """Test MIME type detection."""
        assert get_mime_type("video.mp4") == "video/mp4"
        assert get_mime_type("image.jpg") == "image/jpeg"
        assert get_mime_type("unknown.xyz") == "application/octet-stream"
    
    def test_create_temp_file(self):
        """Test temporary file creation."""
        temp_file = create_temp_file(".txt", b"test content")
        
        try:
            assert os.path.exists(temp_file)
            assert temp_file.endswith(".txt")
            
            with open(temp_file, 'r') as f:
                content = f.read()
                assert content == "test content"
        finally:
            os.unlink(temp_file)
    
    def test_json_file_operations(self):
        """Test JSON file read/write."""
        test_data = {"name": "test", "value": 123}
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
            temp_file = f.name
        
        try:
            # Write JSON
            write_json_file(temp_file, test_data)
            
            # Read JSON
            read_data = read_json_file(temp_file)
            
            assert read_data == test_data
        finally:
            os.unlink(temp_file)
    
    def test_parse_duration_string(self):
        """Test duration string parsing."""
        assert parse_duration_string("1h30m") == 5400.0
        assert parse_duration_string("90s") == 90.0
        assert parse_duration_string("2h") == 7200.0
        assert parse_duration_string("1.5h") == 5400.0
        assert parse_duration_string("") == 0.0
    
    def test_datetime_functions(self):
        """Test datetime functions."""
        # Format datetime
        dt = datetime(2024, 1, 1, 12, 30, 45)
        formatted = format_datetime(dt)
        assert "2024-01-01T12:30:45" in formatted
        
        # Custom format
        custom = format_datetime(dt, "%Y/%m/%d")
        assert custom == "2024/01/01"
        
        # Parse datetime
        parsed = parse_datetime("2024-01-01T12:30:45")
        assert parsed == dt
        
        # Alternative formats
        parsed2 = parse_datetime("2024-01-01 12:30:45")
        assert parsed2 == dt
        
        # Invalid format
        with pytest.raises(Exception):
            parse_datetime("invalid")
    
    def test_calculate_cost(self):
        """Test cost calculation."""
        # Speech videos
        assert calculate_cost(300, "free", False) > 0  # 5 minutes
        assert calculate_cost(300, "starter", False) > 0
        assert calculate_cost(300, "pro", False) > 0
        assert calculate_cost(300, "plus", False) > 0
        
        # Silent videos (should be cheaper)
        speech_cost = calculate_cost(300, "free", False)
        silent_cost = calculate_cost(300, "free", True)
        assert silent_cost < speech_cost
        
        # Tier differences
        free_cost = calculate_cost(300, "free", False)
        pro_cost = calculate_cost(300, "pro", False)
        assert pro_cost > free_cost  # Pro should be more expensive
    
    def test_generate_password(self):
        """Test password generation."""
        password = generate_password(12)
        
        assert isinstance(password, str)
        assert len(password) == 12
        
        # Should contain at least one of each character type
        import string
        assert any(c in string.ascii_lowercase for c in password)
        assert any(c in string.ascii_uppercase for c in password)
        assert any(c in string.digits for c in password)
        assert any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password)
    
    def test_validate_email(self):
        """Test email validation."""
        assert validate_email("test@example.com") == True
        assert validate_email("user.name@domain.co.uk") == True
        assert validate_email("test+tag@example.com") == True
        assert validate_email("") == False
        assert validate_email("invalid") == False
        assert validate_email("@example.com") == False
    
    def test_truncate_text(self):
        """Test text truncation."""
        text = "This is a long text that needs to be truncated"
        
        # No truncation needed
        assert truncate_text(text, 100) == text
        
        # Truncation needed
        truncated = truncate_text(text, 20)
        assert len(truncated) <= 23  # 20 + "..."
        assert truncated.endswith("...")
        
        # Custom suffix
        truncated = truncate_text(text, 20, " [more]")
        assert truncated.endswith(" [more]")
    
    def test_chunk_list(self):
        """Test list chunking."""
        lst = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        
        # Chunk size 3
        chunks = chunk_list(lst, 3)
        assert len(chunks) == 3
        assert chunks[0] == [1, 2, 3]
        assert chunks[1] == [4, 5, 6]
        assert chunks[2] == [7, 8, 9]
        
        # Chunk size 4
        chunks = chunk_list(lst, 4)
        assert len(chunks) == 3
        assert chunks[0] == [1, 2, 3, 4]
        assert chunks[1] == [5, 6, 7, 8]
        assert chunks[2] == [9]
        
        # Empty list
        assert chunk_list([], 3) == []
    
    def test_merge_dicts(self):
        """Test dictionary merging."""
        dict1 = {"a": 1, "b": {"x": 10}}
        dict2 = {"b": {"y": 20}, "c": 3}
        
        merged = merge_dicts(dict1, dict2)
        assert merged == {"a": 1, "b": {"x": 10, "y": 20}, "c": 3}
        
        # Overwrite non-dict values
        dict3 = {"a": 100}
        merged = merge_dicts(dict1, dict3)
        assert merged == {"a": 100, "b": {"x": 10}}
    
    def test_get_system_info(self):
        """Test system info retrieval."""
        info = get_system_info()
        
        assert isinstance(info, dict)
        assert "platform" in info
        assert "python_version" in info
        assert "cpu_count" in info
        assert "total_memory" in info
        assert "available_memory" in info
        assert "disk_usage" in info
        assert "boot_time" in info
        assert "process_id" in info
    
    def test_execute_command(self):
        """Test command execution."""
        # Successful command
        result = execute_command(["echo", "test"])
        assert result["success"] == True
        assert "test" in result["stdout"]
        
        # Failed command
        result = execute_command(["false"])
        assert result["success"] == False
        assert result["return_code"] != 0
        
        # Timeout
        result = execute_command(["sleep", "10"], timeout=1)
        assert result["success"] == False
        assert "timed out" in result["error"]
    
    def test_timer(self):
        """Test timer context manager."""
        with Timer() as timer:
            import time
            time.sleep(0.1)
        
        assert timer.elapsed_seconds > 0.1
        assert timer.elapsed_milliseconds > 100
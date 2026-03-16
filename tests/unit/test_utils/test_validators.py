"""
Unit tests for validators.
"""
import pytest
import tempfile
import os
from unittest.mock import Mock, patch

from core.validators import Validators, ValidationErrorBuilder

class TestValidators:
    """Test validators."""
    
    def test_validate_email_valid(self):
        """Test valid email addresses."""
        assert Validators.validate_email("test@example.com")[0] == True
        assert Validators.validate_email("user.name@domain.co.uk")[0] == True
        assert Validators.validate_email("test+tag@example.com")[0] == True
    
    def test_validate_email_invalid(self):
        """Test invalid email addresses."""
        assert Validators.validate_email("")[0] == False
        assert Validators.validate_email("invalid")[0] == False
        assert Validators.validate_email("@example.com")[0] == False
        assert Validators.validate_email("test@")[0] == False
    
    def test_validate_password_valid(self):
        """Test valid passwords."""
        assert Validators.validate_password("Password123!")[0] == True
        assert Validators.validate_password("StrongPass!2024")[0] == True
    
    def test_validate_password_invalid(self):
        """Test invalid passwords."""
        # Too short
        assert Validators.validate_password("Short1!")[0] == False
        # No uppercase
        assert Validators.validate_password("password123!")[0] == False
        # No lowercase
        assert Validators.validate_password("PASSWORD123!")[0] == False
        # No digit
        assert Validators.validate_password("Password!")[0] == False
        # No special character
        assert Validators.validate_password("Password123")[0] == False
    
    def test_validate_video_file(self):
        """Test video file validation."""
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            f.write(b'test')
            temp_file = f.name
        
        try:
            # Mock file size
            with patch('os.path.getsize', return_value=1000000):
                # Mock MIME type
                with patch('magic.Magic') as mock_magic:
                    mock_instance = Mock()
                    mock_instance.from_file.return_value = 'video/mp4'
                    mock_magic.return_value = mock_instance
                    
                    result = Validators.validate_video_file(
                        temp_file,
                        max_size_mb=10,
                        allowed_extensions=['mp4', 'avi'],
                        check_mime_type=True
                    )
                    
                    assert result[0] == True
        finally:
            os.unlink(temp_file)
    
    def test_validate_tier(self):
        """Test tier validation."""
        assert Validators.validate_tier("free")[0] == True
        assert Validators.validate_tier("starter")[0] == True
        assert Validators.validate_tier("pro")[0] == True
        assert Validators.validate_tier("plus")[0] == True
        assert Validators.validate_tier("enterprise")[0] == True
        assert Validators.validate_tier("invalid")[0] == False
    
    def test_validate_language_code(self):
        """Test language code validation."""
        assert Validators.validate_language_code("en")[0] == True
        assert Validators.validate_language_code("es")[0] == True
        assert Validators.validate_language_code("zh-CN")[0] == True
        assert Validators.validate_language_code("")[0] == False
        assert Validators.validate_language_code("english")[0] == False
    
    def test_validate_integer(self):
        """Test integer validation."""
        assert Validators.validate_integer("123")[0] == True
        assert Validators.validate_integer(456)[0] == True
        assert Validators.validate_integer(100, min_value=0, max_value=200)[0] == True
        assert Validators.validate_integer("abc")[0] == False
        assert Validators.validate_integer(50, min_value=100)[0] == False
    
    def test_validate_float(self):
        """Test float validation."""
        assert Validators.validate_float("123.45")[0] == True
        assert Validators.validate_float(456.78)[0] == True
        assert Validators.validate_float(100.5, min_value=0.0, max_value=200.0)[0] == True
        assert Validators.validate_float("abc")[0] == False
    
    def test_validate_string(self):
        """Test string validation."""
        assert Validators.validate_string("test", min_length=1, max_length=10)[0] == True
        assert Validators.validate_string("abc123", allowed_chars="abcdefghijklmnopqrstuvwxyz0123456789")[0] == True
        assert Validators.validate_string("", min_length=1)[0] == False
        assert Validators.validate_string("toolong" * 10, max_length=10)[0] == False
    
    def test_validate_list(self):
        """Test list validation."""
        assert Validators.validate_list([1, 2, 3], min_items=1, max_items=5)[0] == True
        assert Validators.validate_list([], min_items=1)[0] == False
        assert Validators.validate_list([1] * 10, max_items=5)[0] == False
        
        # With item validator
        def is_positive(x):
            return x > 0, ""
        
        assert Validators.validate_list([1, 2, 3], item_validator=is_positive)[0] == True
        assert Validators.validate_list([1, -2, 3], item_validator=is_positive)[0] == False
    
    def test_validate_dict(self):
        """Test dictionary validation."""
        data = {"name": "test", "age": 25}
        required_keys = ["name", "age"]
        
        assert Validators.validate_dict(data, required_keys=required_keys)[0] == True
        
        # Missing required key
        assert Validators.validate_dict({"name": "test"}, required_keys=required_keys)[0] == False
        
        # With key validators
        def validate_name(x):
            return isinstance(x, str) and len(x) > 0, "Name must be non-empty string"
        
        def validate_age(x):
            return isinstance(x, int) and x >= 0, "Age must be non-negative integer"
        
        key_validators = {"name": validate_name, "age": validate_age}
        assert Validators.validate_dict(data, key_validators=key_validators)[0] == True
        
        # Invalid data
        invalid_data = {"name": "", "age": -5}
        assert Validators.validate_dict(invalid_data, key_validators=key_validators)[0] == False
    
    def test_validate_url(self):
        """Test URL validation."""
        assert Validators.validate_url("https://example.com")[0] == True
        assert Validators.validate_url("http://example.com")[0] == True
        assert Validators.validate_url("")[0] == False
        assert Validators.validate_url("invalid")[0] == False
        
        # With allowed domains
        allowed_domains = ["example.com", "google.com"]
        assert Validators.validate_url("https://example.com", allowed_domains)[0] == True
        assert Validators.validate_url("https://facebook.com", allowed_domains)[0] == False
    
    def test_validate_hex_color(self):
        """Test hex color validation."""
        assert Validators.validate_hex_color("#ffffff")[0] == True
        assert Validators.validate_hex_color("#fff")[0] == True
        assert Validators.validate_hex_color("#ffffffff")[0] == True  # with alpha
        assert Validators.validate_hex_color("")[0] == False
        assert Validators.validate_hex_color("#ggg")[0] == False
        assert Validators.validate_hex_color("ffffff")[0] == False  # missing #
    
    def test_validate_date_string(self):
        """Test date string validation."""
        assert Validators.validate_date_string("2024-01-01")[0] == True
        assert Validators.validate_date_string("2024/01/01", "%Y/%m/%d")[0] == True
        assert Validators.validate_date_string("")[0] == False
        assert Validators.validate_date_string("invalid")[0] == False


class TestValidationErrorBuilder:
    """Test validation error builder."""
    
    def test_add_error(self):
        """Test adding errors."""
        builder = ValidationErrorBuilder()
        builder.add_error("email", "Email is required")
        builder.add_error("email", "Email must be valid")
        builder.add_error("password", "Password is required")
        
        assert builder.has_errors() == True
        assert builder.errors == {
            "email": ["Email is required", "Email must be valid"],
            "password": ["Password is required"]
        }
    
    def test_raise_if_errors(self):
        """Test raising errors."""
        builder = ValidationErrorBuilder()
        builder.add_error("email", "Email is required")
        
        with pytest.raises(Exception) as exc_info:
            builder.raise_if_errors()
        
        assert "Email is required" in str(exc_info.value)
    
    def test_to_dict(self):
        """Test converting to dictionary."""
        builder = ValidationErrorBuilder()
        builder.add_error("email", "Email is required")
        builder.add_error("password", "Password is required")
        
        errors_dict = builder.to_dict()
        assert errors_dict == {
            "email": ["Email is required"],
            "password": ["Password is required"]
        }
    
    def test_no_errors(self):
        """Test no errors case."""
        builder = ValidationErrorBuilder()
        assert builder.has_errors() == False
        
        # Should not raise
        builder.raise_if_errors()
        
        assert builder.to_dict() == {}
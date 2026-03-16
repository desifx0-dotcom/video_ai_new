"""
Pytest configuration and fixtures.
"""
import os
import sys
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.main import create_app
from src.app.config import TestingConfig
from src.core.domain.entities.user import User, Tier
from src.core.domain.entities.video import Video, VideoStatus, VideoType

@pytest.fixture
def app():
    """Create a Flask app for testing."""
    app, _ = create_app(TestingConfig)
    app.config.update({
        "TESTING": True,
        "DATABASE_PROVIDER": "memory",
        "EMAIL_PROVIDER": "mock",
        "ENABLE_SILENT_DETECTION": False,
        "ENABLE_TRANSLATION": False,
        "ENABLE_VIDEO_STYLES": False,
    })
    
    yield app

@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()

@pytest.fixture
def runner(app):
    """Create a CLI runner."""
    return app.test_cli_runner()

@pytest.fixture
def auth_header():
    """Create an authorization header for testing."""
    return {"Authorization": "Bearer test-token"}

@pytest.fixture
def test_user():
    """Create a test user."""
    return User(
        id="test-user-123",
        email="test@example.com",
        hashed_password="hashed_password",
        tier=Tier.FREE,
        credits_remaining=10,
        videos_processed_this_month=0,
        monthly_video_limit=3
    )

@pytest.fixture
def test_video():
    """Create a test video."""
    return Video(
        id="test-video-123",
        user_id="test-user-123",
        original_filename="test.mp4",
        file_size=1024 * 1024,  # 1MB
        duration=60.0,  # 1 minute
        mime_type="video/mp4",
        status=VideoStatus.UPLOADED,
        video_type=VideoType.SPEECH
    )

@pytest.fixture
def test_video_silent():
    """Create a test silent video."""
    return Video(
        id="test-video-456",
        user_id="test-user-123",
        original_filename="silent.mp4",
        file_size=512 * 1024,  # 512KB
        duration=30.0,  # 30 seconds
        mime_type="video/mp4",
        status=VideoStatus.UPLOADED,
        video_type=VideoType.SILENT
    )

@pytest.fixture
def temp_video_file():
    """Create a temporary video file for testing."""
    temp_dir = tempfile.mkdtemp()
    video_path = Path(temp_dir) / "test_video.mp4"
    
    # Create a minimal valid MP4 file (just header)
    with open(video_path, 'wb') as f:
        # MP4 header
        f.write(b'\x00\x00\x00\x1cftypmp42\x00\x00\x00\x00mp42mp42\x00\x00\x00\x08free')
    
    yield str(video_path)
    
    # Cleanup
    if video_path.exists():
        video_path.unlink()
    if Path(temp_dir).exists():
        Path(temp_dir).rmdir()

@pytest.fixture
def mock_openai():
    """Mock OpenAI API."""
    with patch('src.providers.openai_provider.openai') as mock:
        mock.Completion.create.return_value = {
            "choices": [{"text": "Generated title"}]
        }
        mock.Audio.transcribe.create.return_value = {
            "text": "Test transcription",
            "language": "en"
        }
        yield mock

@pytest.fixture
def mock_google():
    """Mock Google AI API."""
    with patch('src.providers.google_provider.genai') as mock:
        mock_model = Mock()
        mock_model.generate_content.return_value.text = "Generated content"
        mock.GenerativeModel.return_value = mock_model
        yield mock

@pytest.fixture
def mock_stability():
    """Mock Stability AI API."""
    with patch('src.providers.stability_provider.stability_sdk') as mock:
        mock_response = Mock()
        mock_response.artifacts = [Mock(binary=b"fake_image_data")]
        mock.StabilityInference.generate.return_value = [mock_response]
        yield mock

@pytest.fixture
def mock_stripe():
    """Mock Stripe API."""
    with patch('src.providers.stripe_provider.stripe') as mock:
        mock.Customer.create.return_value = {"id": "cust_123"}
        mock.Subscription.create.return_value = {"id": "sub_123"}
        mock.Invoice.create.return_value = {"id": "inv_123"}
        yield mock

@pytest.fixture
def mock_firebase():
    """Mock Firebase."""
    with patch('src.providers.firebase_provider.firebase_admin') as mock:
        mock_db = Mock()
        mock_db.collection.return_value.document.return_value.set.return_value = None
        mock_db.collection.return_value.document.return_value.get.return_value.to_dict.return_value = {}
        mock_db.collection.return_value.where.return_value.stream.return_value = []
        mock.firestore.client.return_value = mock_db
        yield mock

@pytest.fixture
def mock_redis():
    """Mock Redis."""
    with patch('src.providers.redis_provider.redis') as mock:
        mock_client = Mock()
        mock_client.get.return_value = None
        mock_client.set.return_value = True
        mock_client.delete.return_value = 1
        mock.from_url.return_value = mock_client
        yield mock

@pytest.fixture
def mock_ffmpeg():
    """Mock FFmpeg."""
    with patch('src.providers.ffmpeg_provider.ffmpeg') as mock:
        mock.input.return_value.output.return_value.run.return_value = None
        mock.probe.return_value = {
            "format": {"duration": "60.0"},
            "streams": [{"codec_type": "video"}]
        }
        yield mock

@pytest.fixture
def mock_sendgrid():
    """Mock SendGrid."""
    with patch('src.providers.email_provider.sendgrid') as mock:
        mock_client = Mock()
        mock_client.send.return_value = Mock(status_code=202)
        mock.SendGridAPIClient.return_value = mock_client
        yield mock

@pytest.fixture
def mock_resend():
    """Mock Resend."""
    with patch('src.providers.email_provider.Resend') as mock:
        mock_client = Mock()
        mock_client.Emails.send.return_value = {"id": "email_123"}
        mock.Resend.return_value = mock_client
        yield mock

@pytest.fixture
def test_config():
    """Load test configuration."""
    config_dir = Path(__file__).parent.parent / 'config'
    
    configs = {}
    # Load tier config
    tier_config_path = config_dir / 'tier_config.yaml'
    if tier_config_path.exists():
        import yaml
        with open(tier_config_path, 'r') as f:
            configs['tiers'] = yaml.safe_load(f)
    
    return configs

@pytest.fixture
def mock_jwt():
    """Mock JWT decoding."""
    with patch('src.app.middleware.auth.decode_token') as mock:
        mock.return_value = {
            "sub": "test-user-123",
            "email": "test@example.com",
            "tier": "free"
        }
        yield mock

@pytest.fixture
def celery_app(app):
    """Create a Celery app for testing."""
    from src.tasks.celery_app import celery
    celery.conf.update({"task_always_eager": True})
    return celery

@pytest.fixture(autouse=True)
def cleanup_temp_files():
    """Clean up temporary files after each test."""
    yield
    import tempfile
    import shutil
    temp_dir = Path(tempfile.gettempdir()) / "video_ai"
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
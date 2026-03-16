# test_openai.py
import os
os.environ['OPENAI_API_KEY'] = 'mock-key'

from src.providers.openai_provider import OpenAIProvider

provider = OpenAIProvider()
print(f"✅ OpenAIProvider initialized: {provider.check_availability()}")

# Test mock transcription
result = provider.transcribe_audio("test.mp4")
print(f"✅ Mock transcription: {result[:50]}...")

# Test mock text generation
result = provider.generate_text("Hello AI")
print(f"✅ Mock generation: {result}")

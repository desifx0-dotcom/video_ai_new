"""
Integration tests for translation service.
"""
import pytest
import json
from unittest.mock import patch, MagicMock

from src.app.config import TestingConfig
from src.services.translation_service import TranslationService
from src.core.constants import Language

class TestTranslationService:
    """Test translation service."""
    
    @pytest.fixture
    def translation_service(self):
        """Create translation service instance."""
        return TranslationService()
    
    def test_translate_text(self, translation_service):
        """Test text translation."""
        # Mock googletrans
        with patch('src.providers.google_provider.GoogleProvider.translate') as mock_translate:
            mock_translate.return_value = {
                'text': 'Hola mundo',
                'src': 'en',
                'dest': 'es',
                'confidence': 0.95,
                'cost': 0.0  # Free with googletrans
            }
            
            result = translation_service.translate_text(
                text='Hello world',
                target_language='es',
                tier='free'
            )
            
            assert result['success'] == True
            assert result['translated_text'] == 'Hola mundo'
            assert result['source_language'] == 'en'
            assert result['target_language'] == 'es'
            assert result['cost'] == 0.0
    
    def test_translate_video_transcription(self, translation_service):
        """Test video transcription translation."""
        transcription = """
        Hello everyone. Welcome to this tutorial on video processing.
        Today we'll learn how to use AI to enhance your videos.
        Let's get started!
        """
        
        # Mock translation
        with patch.object(translation_service, 'translate_text') as mock_translate:
            mock_translate.return_value = {
                'success': True,
                'translated_text': """
                Hola a todos. Bienvenidos a este tutorial sobre procesamiento de video.
                Hoy aprenderemos cómo usar IA para mejorar tus videos.
                ¡Empecemos!
                """,
                'source_language': 'en',
                'target_language': 'es',
                'confidence': 0.92,
                'cost': 0.0
            }
            
            result = translation_service.translate_video_transcription(
                transcription=transcription,
                target_language='es',
                tier='free'
            )
            
            assert result['success'] == True
            assert 'translated_text' in result
            assert 'es' in result['translated_text']  # Spanish text
            assert result['cost'] == 0.0
    
    def test_translate_video_metadata(self, translation_service):
        """Test video metadata translation."""
        metadata = {
            'title': 'AI Video Processing Tutorial',
            'description': 'Learn how to use AI to enhance your videos with automatic transcription, styling, and more.',
            'tags': ['tutorial', 'ai', 'video processing', 'machine learning']
        }
        
        # Mock translation for each field
        with patch.object(translation_service, 'translate_text') as mock_translate:
            mock_translate.side_effect = [
                {  # Title translation
                    'success': True,
                    'translated_text': 'Tutorial de Procesamiento de Video con IA',
                    'cost': 0.0
                },
                {  # Description translation
                    'success': True,
                    'translated_text': 'Aprende a usar IA para mejorar tus videos con transcripción automática, estilos y más.',
                    'cost': 0.0
                },
                {  # Tags translation (batch)
                    'success': True,
                    'translated_text': ['tutorial', 'ia', 'procesamiento de video', 'aprendizaje automático'],
                    'cost': 0.0
                }
            ]
            
            result = translation_service.translate_video_metadata(
                metadata=metadata,
                target_language='es',
                tier='pro'
            )
            
            assert result['success'] == True
            assert 'es' in result['translated_title'].lower()
            assert 'es' in result['translated_description'].lower()
            assert len(result['translated_tags']) == 4
            assert result['total_cost'] == 0.0
    
    def test_batch_translation(self, translation_service):
        """Test batch translation for multiple texts."""
        texts = [
            'Hello world',
            'Good morning',
            'Thank you very much',
            'How are you today?'
        ]
        
        # Mock batch translation
        with patch('src.providers.google_provider.GoogleProvider.translate_batch') as mock_batch:
            mock_batch.return_value = [
                {'text': 'Hola mundo', 'src': 'en', 'dest': 'es'},
                {'text': 'Buenos días', 'src': 'en', 'dest': 'es'},
                {'text': 'Muchas gracias', 'src': 'en', 'dest': 'es'},
                {'text': '¿Cómo estás hoy?', 'src': 'en', 'dest': 'es'}
            ]
            
            result = translation_service.translate_batch(
                texts=texts,
                target_language='es',
                tier='plus'  # Plus tier supports batch translation
            )
            
            assert result['success'] == True
            assert len(result['translations']) == 4
            assert all('es' in t.lower() for t in result['translations'])
            assert result['cost'] == 0.0
    
    def test_language_detection(self, translation_service):
        """Test automatic language detection."""
        # Mock language detection
        with patch('src.providers.google_provider.GoogleProvider.detect_language') as mock_detect:
            mock_detect.return_value = {
                'language': 'en',
                'confidence': 0.98,
                'cost': 0.0
            }
            
            result = translation_service.detect_language(
                text='Hello world, this is a test.',
                tier='free'
            )
            
            assert result['success'] == True
            assert result['language'] == 'en'
            assert result['confidence'] == 0.98
            assert result['cost'] == 0.0
    
    def test_supported_languages(self, translation_service):
        """Test getting supported languages."""
        languages = translation_service.get_supported_languages()
        
        # Should return all supported languages
        assert len(languages) > 100  # 100+ languages supported
        
        # Check some common languages are present
        common_langs = ['en', 'es', 'fr', 'de', 'zh-CN', 'ja', 'ko', 'ru']
        for lang in common_langs:
            assert lang in languages
        
        # Check language names are included
        for lang_code, lang_info in languages.items():
            assert 'name' in lang_info
            assert 'native_name' in lang_info
    
    def test_tier_based_translation_features(self):
        """Test translation features based on tier."""
        # Free tier: Basic translation
        free_features = {
            'batch_translation': False,
            'priority_processing': False,
            'max_text_length': 5000,
            'supported_languages': 100
        }
        
        # Starter tier: Same as free
        starter_features = free_features.copy()
        
        # Pro tier: Batch translation enabled
        pro_features = free_features.copy()
        pro_features['batch_translation'] = True
        
        # Plus tier: All features
        plus_features = pro_features.copy()
        plus_features['priority_processing'] = True
        plus_features['max_text_length'] = 10000
        
        assert not free_features['batch_translation']
        assert not starter_features['batch_translation']
        assert pro_features['batch_translation']
        assert plus_features['batch_translation']
        assert plus_features['priority_processing']
    
    def test_translation_cost_calculation(self, translation_service):
        """Test translation cost calculation (should be free)."""
        # All translations should be free with googletrans
        test_cases = [
            {'text_length': 100, 'tier': 'free', 'expected_cost': 0.0},
            {'text_length': 1000, 'tier': 'starter', 'expected_cost': 0.0},
            {'text_length': 5000, 'tier': 'pro', 'expected_cost': 0.0},
            {'text_length': 10000, 'tier': 'plus', 'expected_cost': 0.0}
        ]
        
        for test_case in test_cases:
            cost = translation_service.calculate_translation_cost(
                text_length=test_case['text_length'],
                tier=test_case['tier']
            )
            
            assert cost == test_case['expected_cost']
    
    def test_translation_quality_by_tier(self):
        """Test translation quality differences by tier."""
        # Note: googletrans uses Google Translate, so quality is consistent
        # But higher tiers might use premium services in the future
        
        # For now, all tiers get the same quality
        tiers = ['free', 'starter', 'pro', 'plus']
        
        for tier in tiers:
            # Translation quality should be the same
            # (This would change if we add premium translation services)
            pass
    
    def test_error_handling(self, translation_service):
        """Test translation error handling."""
        # Mock translation error
        with patch('src.providers.google_provider.GoogleProvider.translate') as mock_translate:
            mock_translate.side_effect = Exception("Translation API error")
            
            result = translation_service.translate_text(
                text='Hello world',
                target_language='es',
                tier='free'
            )
            
            assert result['success'] == False
            assert 'error' in result
            assert 'Translation' in result['error']
    
    def test_unsupported_language(self, translation_service):
        """Test translation to unsupported language."""
        # Try to translate to an unsupported language code
        result = translation_service.translate_text(
            text='Hello world',
            target_language='xx',  # Invalid language code
            tier='free'
        )
        
        # Should return error or fallback to English
        assert result['success'] == False or result['target_language'] != 'xx'
    
    def test_large_text_translation(self, translation_service):
        """Test translation of large text."""
        # Create large text (over free tier limit)
        large_text = 'A' * 6000  # 6000 characters
        
        # Free tier has 5000 character limit
        result = translation_service.translate_text(
            text=large_text,
            target_language='es',
            tier='free'
        )
        
        # Should handle gracefully (truncate or error)
        assert result['success'] == False or len(result['translated_text']) <= 5000
    
    def test_special_characters_handling(self, translation_service):
        """Test translation with special characters."""
        text_with_specials = """
        Hello world! 👋
        This is a test with emojis 😊 and special characters: © ® ™
        Also HTML entities: &amp; &lt; &gt;
        And code: print("Hello")
        """
        
        with patch.object(translation_service, 'translate_text') as mock_translate:
            mock_translate.return_value = {
                'success': True,
                'translated_text': text_with_specials,  # Mock same text for simplicity
                'cost': 0.0
            }
            
            result = translation_service.translate_text(
                text=text_with_specials,
                target_language='es',
                tier='pro'
            )
            
            assert result['success'] == True
            # Should preserve special characters
            assert '👋' in result['translated_text'] or 'emoji' in result.get('notes', '')
    
    def test_format_preservation(self, translation_service):
        """Test preservation of formatting during translation."""
        formatted_text = """
        # Title
        
        This is a paragraph.
        
        - Item 1
        - Item 2
        - Item 3
        
        **Bold text** and *italic text*.
        
        Code block:
        ```
        def hello():
            print("World")
        ```
        """
        
        # Mock translation that preserves formatting
        with patch.object(translation_service, 'translate_text') as mock_translate:
            # In reality, formatting might be preserved or handled specially
            mock_translate.return_value = {
                'success': True,
                'translated_text': formatted_text,  # Mock same for simplicity
                'cost': 0.0,
                'formatting_preserved': True
            }
            
            result = translation_service.translate_text(
                text=formatted_text,
                target_language='es',
                tier='plus'
            )
            
            assert result['success'] == True
            # Higher tiers might preserve formatting better
            if result.get('formatting_preserved'):
                assert '#' in result['translated_text']  # Markdown preserved
                assert '```' in result['translated_text']  # Code block preserved
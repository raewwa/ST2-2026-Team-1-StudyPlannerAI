from app.services.ai_gateway import create_advice_provider, OllamaStudyAdviceProvider

def test_ollama_factory_english():
    provider = create_advice_provider({'AI_PROVIDER':'ollama', 'OLLAMA_MODEL':'llama3.2'})
    assert isinstance(provider, OllamaStudyAdviceProvider)
    assert provider.language == 'en'

def test_gemini_provider_not_supported():
    import pytest
    with pytest.raises(ValueError):
        create_advice_provider({'AI_PROVIDER':'gemini'})

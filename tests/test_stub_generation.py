import pytest

from src.editorial.services.generation.providers import StubGenerationProvider


@pytest.mark.asyncio
async def test_stub_provider_returns_requested_variants() -> None:
    provider = StubGenerationProvider()
    prompt = "Источники:\n- История про сессию и экзамены\n- История про общежитие"
    variants = await provider.generate_variants(prompt, 3)

    assert len(variants) == 3
    assert all(isinstance(item, str) and item for item in variants)


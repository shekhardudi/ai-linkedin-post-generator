"""Settings is the single source of truth for models + tunables.

These tests verify (a) every key is exposed, (b) env vars actually override,
and (c) the helpers (`crew_models`, `model_card`) reflect overrides.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def fresh_settings(monkeypatch):
    """Yield a builder that returns a fresh Settings, applying env overrides first."""
    def _build(**env_overrides):
        for k, v in env_overrides.items():
            monkeypatch.setenv(k, v)
        # Bypass lru_cache by importing the module and instantiating directly
        import backend.core.settings as s_mod
        importlib.reload(s_mod)
        s_mod.get_settings.cache_clear()
        return s_mod.Settings()
    yield _build


def test_default_model_strings(fresh_settings):
    s = fresh_settings()
    assert s.crew_researcher_model == "openai/gpt-5"
    assert s.crew_writer_model == "anthropic/claude-opus-4-7"
    assert s.crew_critic_model == "anthropic/claude-sonnet-4-6"
    assert s.visual_director_model == "anthropic/claude-sonnet-4-6"
    assert s.image_model == "gpt-image-1"
    assert s.image_default_size == "1024x1024"
    assert s.image_default_quality == "medium"


def test_env_overrides_each_model(fresh_settings):
    s = fresh_settings(
        CREW_RESEARCHER_MODEL="openai/gpt-5-mini",
        CREW_WRITER_MODEL="anthropic/claude-sonnet-4-6",
        CREW_CRITIC_MODEL="anthropic/claude-haiku-4-5-20251001",
        VISUAL_DIRECTOR_MODEL="anthropic/claude-haiku-4-5-20251001",
        IMAGE_MODEL="dall-e-3",
        IMAGE_DEFAULT_QUALITY="low",
    )
    assert s.crew_researcher_model == "openai/gpt-5-mini"
    assert s.crew_writer_model == "anthropic/claude-sonnet-4-6"
    assert s.crew_critic_model == "anthropic/claude-haiku-4-5-20251001"
    assert s.visual_director_model == "anthropic/claude-haiku-4-5-20251001"
    assert s.image_model == "dall-e-3"
    assert s.image_default_quality == "low"


def test_crew_models_helper(fresh_settings):
    s = fresh_settings(
        CREW_RESEARCHER_MODEL="A", CREW_WRITER_MODEL="B", CREW_CRITIC_MODEL="C"
    )
    assert s.crew_models() == ["A", "B", "C"]


def test_model_card_reflects_overrides(fresh_settings):
    s = fresh_settings(
        CREW_RESEARCHER_MODEL="r", CREW_WRITER_MODEL="w",
        CREW_CRITIC_MODEL="c", VISUAL_DIRECTOR_MODEL="v", IMAGE_MODEL="i",
    )
    card = s.model_card()
    assert card == {"researcher": "r", "writer": "w", "critic": "c",
                    "visual_director": "v", "image": "i"}


def test_llm_tunables(fresh_settings):
    s = fresh_settings(
        VISUAL_DIRECTOR_TEMPERATURE="0.3",
        VISUAL_DIRECTOR_MAX_TOKENS="1500",
        SCOUT_SYNTHESIS_TEMPERATURE="0.5",
        OLLAMA_NUM_CTX="16384",
    )
    assert s.visual_director_temperature == 0.3
    assert s.visual_director_max_tokens == 1500
    assert s.scout_synthesis_temperature == 0.5
    assert s.ollama_num_ctx == 16384


def test_rate_limit_strings(fresh_settings):
    s = fresh_settings(RATE_LIMIT_POSTS="100/hour", RATE_LIMIT_IMAGES="20/minute")
    assert s.rate_limit_posts == "100/hour"
    assert s.rate_limit_images == "20/minute"

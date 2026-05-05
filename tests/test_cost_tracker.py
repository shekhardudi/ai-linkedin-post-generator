from types import SimpleNamespace

from backend.utils.cost_tracker import compute_post_cost


def _crew_output_with(prompt: int, completion: int):
    return SimpleNamespace(
        token_usage=SimpleNamespace(
            prompt_tokens=prompt,
            completion_tokens=completion,
            cached_prompt_tokens=0,
        )
    )


def test_compute_post_cost_with_full_data():
    crew = _crew_output_with(prompt=30_000, completion=6_000)
    cost = compute_post_cost(
        crew_output=crew,
        crew_models=[
            "openai/gpt-5",
            "anthropic/claude-opus-4-7",
            "anthropic/claude-sonnet-4-6",
        ],
        visual_director_usage={"input_tokens": 1_500, "output_tokens": 400},
        image_call_count=2,
    )
    d = cost.to_dict()
    assert d["crew"]["prompt_tokens"] == 30_000
    assert d["crew"]["completion_tokens"] == 6_000
    assert d["crew"]["cost_usd"] > 0
    assert d["visual_director"]["prompt_tokens"] == 1_500
    assert d["visual_director"]["cost_usd"] > 0
    assert d["image"]["calls"] == 2
    assert d["image"]["cost_usd"] > 0
    assert d["total_cost_usd"] == round(
        d["crew"]["cost_usd"] + d["visual_director"]["cost_usd"] + d["image"]["cost_usd"],
        6,
    )


def test_compute_post_cost_handles_missing_token_usage():
    crew = SimpleNamespace(token_usage=None)
    cost = compute_post_cost(
        crew_output=crew,
        crew_models=["openai/gpt-5"],
        visual_director_usage=None,
        image_call_count=0,
    )
    assert cost.to_dict()["total_cost_usd"] == 0.0


def test_compute_post_cost_handles_dict_token_usage():
    crew = SimpleNamespace(token_usage={"prompt_tokens": 10_000, "completion_tokens": 1_000})
    cost = compute_post_cost(
        crew_output=crew,
        crew_models=["openai/gpt-5", "anthropic/claude-opus-4-7"],
    )
    d = cost.to_dict()
    assert d["crew"]["prompt_tokens"] == 10_000
    assert d["crew"]["completion_tokens"] == 1_000
    assert d["crew"]["cost_usd"] > 0


def test_compute_post_cost_unknown_model_falls_to_zero():
    crew = _crew_output_with(prompt=1_000, completion=500)
    cost = compute_post_cost(
        crew_output=crew,
        crew_models=["openai/totally-fake-model"],
    )
    assert cost.to_dict()["crew"]["cost_usd"] == 0.0


def test_image_only_cost_increments():
    crew = SimpleNamespace(token_usage=None)
    one = compute_post_cost(crew_output=crew, crew_models=[], image_call_count=1)
    two = compute_post_cost(crew_output=crew, crew_models=[], image_call_count=2)
    assert two.image_cost_usd == round(2 * one.image_cost_usd, 6)

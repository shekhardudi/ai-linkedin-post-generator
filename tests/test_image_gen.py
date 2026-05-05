"""Light-touch tests for image_gen — we mock the OpenAI client to avoid real API calls."""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.tools import image_gen


class _FakeImagesAPI:
    def __init__(self, b64: str) -> None:
        self._b64 = b64

    def generate(self, **kwargs):
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self._b64, url=None)])


class _FakeClient:
    def __init__(self, b64: str) -> None:
        self.images = _FakeImagesAPI(b64)


def test_generate_image_writes_png(tmp_path, monkeypatch):
    # 1x1 transparent PNG
    raw_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c63000100000005000100200d0a2d000000000049454e44ae426082"
    )
    fake_b64 = base64.b64encode(raw_bytes).decode("ascii")

    monkeypatch.setattr(image_gen, "OpenAI", lambda api_key=None: _FakeClient(fake_b64))

    path = image_gen.generate_image(prompt="A documentary still.", run_id="20260101_120000")
    assert path.exists()
    assert path.suffix == ".png"
    assert path.read_bytes() == raw_bytes
    assert path.parent.name == "20260101_120000"
    assert path.stem == "20260101_120000_01"


def test_generate_image_increments_seq(tmp_path, monkeypatch):
    raw_bytes = bytes.fromhex("89504e470d0a1a0a")
    fake_b64 = base64.b64encode(raw_bytes).decode("ascii")
    monkeypatch.setattr(image_gen, "OpenAI", lambda api_key=None: _FakeClient(fake_b64))

    p1 = image_gen.generate_image(prompt="x", run_id="run_a")
    p2 = image_gen.generate_image(prompt="x", run_id="run_a")
    assert p1.stem.endswith("_01")
    assert p2.stem.endswith("_02")

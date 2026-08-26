"""Encoder backend tests: error paths run everywhere, torch paths skip without the extra."""

import importlib.util
from pathlib import Path

from typing import Any

import numpy as np
import pytest

from library_of_mess.encoders import EmbeddingBackendError, build_encoders
from library_of_mess.encoders import weights_cached
from library_of_mess.encoders.preprocess import IMAGE_SIZE, load_image_blob

TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None
PIL_AVAILABLE = importlib.util.find_spec("PIL") is not None


def test_build_encoders_raises_when_stack_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Probe reports a missing stack regardless of what this env has installed."""
    import library_of_mess.encoders as enc

    monkeypatch.setattr(enc, "missing_modules", lambda: ["torch", "transformers", "PIL"])
    with pytest.raises(EmbeddingBackendError, match="--extra embeddings"):
        build_encoders()


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not installed")
def test_weights_cached_tracks_hf_snapshot_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from library_of_mess import config
    from library_of_mess.encoders.torch_clip import MODEL_REGISTRY, configured_model_id

    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path / "models"))
    config.model_cache_dir.cache_clear() if hasattr(config.model_cache_dir, "cache_clear") else None
    repo = configured_model_id()
    revision = MODEL_REGISTRY[repo]["revision"]
    snapshots = tmp_path / "models" / f"models--{repo.replace('/', '--')}" / "snapshots"

    assert not weights_cached()

    (snapshots / revision).mkdir(parents=True)
    assert weights_cached()


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not installed")
def test_backend_dispatch_and_shapes(tmp_path: Path) -> None:
    import torch

    from library_of_mess.encoders.torch_clip import TorchClipBackend

    calls: list[str] = []

    class FakeModel:
        def get_image_features(self, pixel_values):  # type: ignore[no-untyped-def]
            calls.append("image")
            return torch.ones(len(pixel_values), 8)

        def get_text_features(self, input_ids):  # type: ignore[no-untyped-def]
            calls.append("text")
            return torch.full((len(input_ids), 8), 2.0)

    class FakeTok:
        def __call__(self, texts, return_tensors, padding, max_length, truncation):  # type: ignore[no-untyped-def]
            assert return_tensors == "pt"
            assert padding == "max_length" and max_length == 64 and truncation
            return {"input_ids": torch.ones(len(texts), 64, dtype=torch.int64)}

    class StubBackend(TorchClipBackend):
        def __init__(self) -> None:
            super().__init__()
            self.fake_model = FakeModel()
            self.fake_tok = FakeTok()

        def _model(self) -> Any:
            return self.fake_model

        def _tokenizer(self) -> Any:
            return self.fake_tok

    backend = StubBackend()
    emb_i = backend.encode_images([_write_test_jpg(tmp_path)])
    emb_t = backend.encode_texts(["something"])

    assert calls == ["image", "text"]
    assert emb_i.shape == (1, 8) and float(emb_i[0, 0]) == 1.0
    assert emb_t.shape == (1, 8) and float(emb_t[0, 0]) == 2.0


def _write_test_jpg(tmp_path: Path) -> Path:
    from PIL import Image

    path = tmp_path / "thumb.jpg"
    Image.new("RGB", (48, 32), (255, 255, 255)).save(path)
    return path


@pytest.mark.skipif(not PIL_AVAILABLE, reason="pillow not installed")
def test_load_image_blob_normalizes(tmp_path: Path) -> None:
    blob = load_image_blob(_write_test_jpg(tmp_path))

    assert blob.shape == (3, IMAGE_SIZE, IMAGE_SIZE)
    assert blob.dtype == np.float32
    assert float(blob.min()) >= -1.0 - 1e-6
    assert float(blob.max()) <= 1.0 + 1e-6
    assert float(blob[0, 0, 0]) == pytest.approx(1.0)


@pytest.mark.skipif(not PIL_AVAILABLE, reason="pillow not installed")
def test_load_image_blob_rejects_garbage(tmp_path: Path) -> None:
    bad = tmp_path / "broken.jpg"
    bad.write_bytes(b"not an image")

    with pytest.raises(EmbeddingBackendError, match="unreadable thumbnail"):
        load_image_blob(bad)

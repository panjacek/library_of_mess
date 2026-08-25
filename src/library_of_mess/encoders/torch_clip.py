"""SigLIP2 embeddings via PyTorch (optional backend).

Loads the official google/siglip2-base-patch32-256 checkpoint (Apache-2.0)
straight from the source repo — no converted artifacts, no intermediate
formats. Each encode call runs only the tower it needs. Device comes from
EMBEDDINGS_DEVICE (default cpu); GPU later is a wheel swap plus that env var.
"""

import os
from pathlib import Path
from typing import Any

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

from library_of_mess.config import model_cache_dir
from library_of_mess.encoders import EmbeddingBackendError
from library_of_mess.encoders.preprocess import load_image_blob

DEFAULT_MODEL_ID = "google/siglip2-base-patch16-224"

# first-party Google checkpoints, revision-pinned (sha verified via HF API);
# image_size must match each checkpoint's training resolution
MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "google/siglip2-base-patch16-224": {"revision": "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2", "image_size": 224},
    "google/siglip2-base-patch32-256": {"revision": "94dffa8cb1179de3e03f091dbc3917e5d5a9ae84", "image_size": 256},
    "google/siglip2-base-patch16-256": {"revision": "3f9f96cb90da5dbc758b01813f2f6f1aee24c1ab", "image_size": 256},
    "google/siglip2-so400m-patch16-256": {"revision": "e8708ab72d125807e45b36fb7d4e0aacbb59f379", "image_size": 256},
}
MAX_TEXT_TOKENS = 64


def configured_model_id() -> str:
    """Repo id selected via EMBEDDINGS_MODEL (default = fastest B/32)."""
    return os.environ.get("EMBEDDINGS_MODEL", DEFAULT_MODEL_ID)


class TorchClipBackend:
    """Image+text encoders backed by transformers on any torch device."""

    def __init__(self) -> None:
        self.repo_id = configured_model_id()
        if self.repo_id not in MODEL_REGISTRY:
            raise EmbeddingBackendError(
                f"EMBEDDINGS_MODEL='{self.repo_id}' is not pinned; known: {', '.join(MODEL_REGISTRY)}"
            )
        self.revision = MODEL_REGISTRY[self.repo_id]["revision"]
        self.image_size = MODEL_REGISTRY[self.repo_id]["image_size"]
        self._net: Any = None
        self._tok: Any = None
        device = os.environ.get("EMBEDDINGS_DEVICE", "cpu").strip().lower()
        if device.split(":", 1)[0] not in ("cpu", "cuda", "mps", "xpu"):
            raise EmbeddingBackendError(
                f"EMBEDDINGS_DEVICE='{device}' is not a known torch device; use cpu, cuda, cuda:0, mps or xpu"
            )
        self._device = device

    def encode_images(self, thumb_paths: list[Path]) -> np.ndarray:
        """Encode a batch of thumbnails to (n, dim) float32 embeddings."""
        pixels = np.stack([load_image_blob(path, self.image_size) for path in thumb_paths])
        feed = {"pixel_values": torch.from_numpy(pixels).to(self._device)}
        return self._run("image", feed, len(thumb_paths))

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        """Encode a batch of queries to (n, dim) float32 embeddings."""
        tok = self._tokenizer()
        # official config declares input_ids only — the tower trains on full
        # padded sequences without an attention mask
        enc = tok(
            list(texts),
            return_tensors="pt",
            padding="max_length",
            max_length=MAX_TEXT_TOKENS,
            truncation=True,
        )
        return self._run("text", {"input_ids": enc["input_ids"].to(self._device)}, len(texts))

    def _run(self, tower: str, feed: dict[str, Any], batch: int) -> np.ndarray:
        model = self._model()
        method = model.get_image_features if tower == "image" else model.get_text_features
        with torch.inference_mode():
            out = method(**feed)
        return out.detach().cpu().numpy().astype(np.float32).reshape(batch, -1)

    def _model(self) -> Any:
        if self._net is None:
            self._load_tokenizer()
            self._net = (
                AutoModel.from_pretrained(self.repo_id, revision=self.revision, cache_dir=str(model_cache_dir()))
                .to(self._device)
                .eval()
            )
        return self._net

    def _tokenizer(self) -> Any:
        self._model()
        return self._tok

    def _load_tokenizer(self) -> None:
        self._tok = AutoTokenizer.from_pretrained(
            self.repo_id, revision=self.revision, cache_dir=str(model_cache_dir())
        )

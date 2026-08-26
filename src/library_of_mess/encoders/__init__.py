"""Pluggable encoder backends for the semantic-search stack.

The heavy parts (torch, model weights) ship as the opt-in `embeddings`
extra — importing this package without it never fails, and
`build_encoders()` raises an actionable error instead of an ImportError.
See docs/research/embedding-models.md for the research behind the choices.
"""

import importlib.util

from library_of_mess.embeddings import ImageEncoder, TextEncoder

__all__ = [
    "EmbeddingBackendError",
    "ImageEncoder",
    "TextEncoder",
    "build_encoders",
    "configured_model_id",
    "weights_cached",
]

REQUIRED_MODULES = ("torch", "transformers", "PIL")


def missing_modules() -> list[str]:
    """Names from REQUIRED_MODULES that cannot be imported in this env."""
    return [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]


def configured_model_id() -> str:
    """Repo id of the embedding model selected via EMBEDDINGS_MODEL (may be unset pre-import)."""
    # lazy by design: importing this package must never require the ML stack
    if "torch" in missing_modules():
        return ""
    from library_of_mess.encoders.torch_clip import configured_model_id as _cid

    return _cid()


def weights_cached() -> bool:
    """True when the configured model's HF snapshot already sits in the local cache.

    Lets UIs say "first run downloads weights" only when that is actually true —
    the cache lives outside the venv (~/.cache/library_of_mess) and survives
    environment rebuilds.
    """
    if "torch" in missing_modules():
        return False
    from library_of_mess.config import model_cache_dir
    from library_of_mess.encoders.torch_clip import MODEL_REGISTRY
    from library_of_mess.encoders.torch_clip import configured_model_id as _cid

    repo = _cid()
    revision = MODEL_REGISTRY.get(repo, {}).get("revision")
    if not repo or not revision:
        return False
    snapshots = model_cache_dir() / f"models--{repo.replace('/', '--')}" / "snapshots"
    return (snapshots / revision).is_dir()


class EmbeddingBackendError(RuntimeError):
    """Raised when the optional embedding stack is missing or unusable."""


def build_encoders() -> tuple[ImageEncoder, TextEncoder]:
    """Return (image, text) encoder callables backed by the optional extra."""
    missing = missing_modules()
    if missing:
        raise EmbeddingBackendError(
            f"semantic search requires the optional 'embeddings' extra "
            f"(missing: {', '.join(missing)}): uv sync --extra embeddings"
        )
    # lazy by design: base installs have no torch, so the backend module can
    # only be imported after the probe above passed
    from library_of_mess.encoders.torch_clip import TorchClipBackend

    backend = TorchClipBackend()
    return backend.encode_images, backend.encode_texts

# ADR 0001: Semantic search stack

Status: accepted (POC shipped) · Date: 2026-08-25 · Research: `docs/research/embedding-models.md`

## Context

The library should be findable by content, not only hand tags: "rainy descent",
"group ride", "forest singletrack". Constraints that shaped the choice:

- CPU-only laptop inference; no GPU today, but GPU must be reachable later
- install-size discipline: base project ~464MB; opt-in extra required
- ~10³ videos → ~10⁴ sampled frames; brute-force search is fine at this scale
- weights from reputable sources only (first-party model orgs)
- offline first: no APIs, no telemetry-style callbacks

## Decision

Run **Google's SigLIP2-B/32** (`google/siglip2-base-patch32-256`, Apache-2.0,
revision-pinned `94dffa8c`) via **transformers + PyTorch CPU wheels**, shipped as
the optional `embeddings` extra:

```toml
embeddings = ["torch>=2.9", "transformers>=4.49,<5", "pillow>=11"]
```

- Weights download once (~1.1GB fp32) into `MODEL_CACHE_DIR` (default
  `~/.cache/library_of_mess/models`), never into the repo or venv.
- Whole-video coverage: ffmpeg samples one frame every `SEARCH_FRAME_INTERVAL`
  seconds (default 10s) into `_search/{stem}.fNNNN.jpg`; every frame is embedded
  separately by the unchanged filename-keyed npz store (`embeddings.py`);
  per-frame hits are grouped back to their best moment per video with a
  timestamp, and playback seeks there (`st.video(start_time=...)`).
- Encoders are injected callables (`encoders/torch_clip.py` behind a probe-guarded
  factory); UI and store know nothing about torch.

Measured on the dev machine (8 logical cores): **6.1 img/s indexing, ~210ms text
query**, incremental re-syncs ~free (npz cache). End-to-end validated through the
packaged stack on real photographs (3/3 correct top-1) — synthetic noise images
are out-of-distribution for any CLIP-class model and rank near-randomly.

## Alternatives considered (rejected, with numbers)

| option | why rejected |
|---|---|
| open-clip-torch, default PyPI wheels | ~2.5GB CUDA payload into a 464MB project |
| onnxruntime + onnx-community int8 export | worked (3.1 img/s / 357ms) but provenance rejected: converted third-party upload; combined-graph also wasted a dummy vision pass per query |
| OpenCV 5 DNN engine | beats ORT on CPU transformers, but cannot parse available quantized artifacts: `DynamicQuantizeLinear`/`MatMulNBits` unsupported; fp16 tower exports lack projection heads |
| imgbeddings | unmaintained since 2022, incompatible with modern huggingface_hub |
| sqlite-vec store | pre-v1 with declared breaking changes; ANN alpha-only; numpy matmul wins outright at ~10⁴ vectors |
| Gemini Embedding 2 | natively multimodal incl. video — but closed weights, API-only; revisit if video-native embeddings ever become self-hostable |

## Consequences

- Base install and CI stay light: default env never imports torch; tests use
  fake encoders plus skipif guards.
- `transformers>=4.49,<5` pin is load-bearing: v5 refactored SigLIP2
  (projections moved into towers, `attention_mask` dropped from tokenizer
  config) and broke cross-modal alignment under it.
- GPU later = swap uv index to CUDA wheels + `EMBEDDINGS_DEVICE=cuda`. No code
  or artifact changes.
- Default model revised after first real-library pass (weak retrieval):
  **B/16-224** for recall; B/32-256 remains available as the ~3× faster speed
  option via `EMBEDDINGS_MODEL`.
- Video resolution is decoupled from search cost — embedding consumes 400px
  thumbnails / 256² frames, so 4K sources cost the same as 720p.

## Pending / follow-ups

- Real-library quality eval: first pass (2026-08-25) judged results
  unsatisfying ("AI slop") even after the B/16 flip — eval harness
  (fixed query set + CSV dumps) is the required next step before any further
  model/density tuning; hypotheses ranked in the session handoff plan.
- Auto-tagging research track: zero-shot classification over already-sampled
  frames to suggest tags in the existing tagging grid (see gitignored
  `docs/plans/2026-08-25_plan_autotag_research.md`); also the fallback
  direction if joint-embedding search under-serves this footage class.

## Follow-up 2026-08-26: eval executed, decision holds

The eval harness ran against the real library (`scripts/eval_search.py`,
`scripts/sanity_check.py`; findings in gitignored
`docs/plans/2026-08-26_handoff_semantic_search.md`):

- **Ranking verified correct**: a known mountains-panorama clip ranks #1 for
  mountain queries; off-corpus control queries are rejected. The 08-25 "AI
  slop" judgment was a methodology error — SigLIP2's embedding space is
  anisotropic (image-image cosine ≈ 0.79 mean), so absolute scores compress
  into ~0–0.15 and must never be read as confidence. Rank order is the only
  signal.
- **`siglip2-so400m-patch16-256` tested and rejected**: identical rankings,
  same anisotropy, ~4× index cost. B/16-224 stays the default.
- **OpenCV 5 DNN re-checked** (June 2026 release, 80% ONNX coverage): it is
  an inference engine, not a different model — same weights yield the same
  embeddings and scores. Swapping runtimes cannot change retrieval quality,
  so the rejection above stands on quality grounds; only install-size
  (~230MB → ~54MB) would motivate revisiting it.
- Small-object queries ("red gloves") fail on wide-angle frames at any model
  size in this family — inherent to global 224px encoding, not fixable by
  tuning here.

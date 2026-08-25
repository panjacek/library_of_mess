# Embedding model & runtime research — semantic search backend

Status: findings from pre-implementation research (2026-08-25). No decision taken yet;
spikes and the eventual choice are tracked in the ADR (`docs/adr/0001-semantic-search-stack.md`,
to be written). Implementation plans live in gitignored `docs/plans/`.

## Problem framing

Goal: "find clips that look like X" over a personal video library via CLIP-style joint
image+text embeddings of thumbnails.

Constraints that shape every option:

- CPU-only inference on a laptop; no GPU anywhere in the loop.
- Install-size discipline: project is ~464MB with deps (`streamlit`, `pandas`, `pyarrow`);
  default Linux torch pulls ~2.5GB+ (CUDA wheels) — unacceptable.
- Scale is tiny: ~10³ thumbnails. Brute-force cosine over an npz store is already merged
  (`embeddings.py`) and is the right search layer at this size.
- Queries are short English phrases ("rainy descent", "group ride") — no need for
  multilingual towers or long-context text encoders.
- Weights must come from reputable sources (model author orgs or canonical ports), not
  random community re-uploads.

Key distinction discovered early: **runtime size** (pip wheels) and **weight size**
(cached model files) are separate budgets. Runtimes range 20–230MB installed; weights for
any reputable joint model are 215–600MB regardless of runtime. Weights cache outside the
repo/venv (`~/.cache/huggingface` or configured dir), so clone/Docker-image size only
depends on the runtime.

## Model landscape (2026, single-vector image↔text)

| Model | Source org / year | Params (vis + txt) | License | Signal |
|---|---|---|---|---|
| SigLIP2 B/32, B/16 | Google, Feb 2025 | 86M vis + large text tower | Apache-2.0 | De-facto strongest open family; ~990k HF dl/mo (B/16); standard VLM vision encoder |
| ViT-B-32 LAION-2B | LAION e.V. | 151M total | MIT | Most-used CLIP ckpt on HF (~3.3M dl/mo); ecosystem default baseline |
| MobileCLIP2 S0/S2/B | Apple, Aug 2025 | S0: 11.4M + 42.4M · S2: 35.7M + 63.4M | apple-amlr (restrictive-ish) | TMLR Featured Certification; S0 ≈ OpenAI ViT-B/16 class at fraction of size |
| MetaCLIP2 | Meta FAIR, 2025 | L-class | open | NeurIPS 2025 Spotlight; multilingual curation angle — irrelevant here |
| jina-clip-v2 | Jina AI | 0.9B | CC BY-NC (non-commercial) | Real text tower / RAG story — wrong axis for this project |
| imgbeddings | minimaxir, 2022 | — | MIT | Dead: last release 2022, broken vs modern `huggingface_hub` (issue #7 unfixed) |

Notes:

- All of SigLIP2 / MobileCLIP2 / MetaCLIP2 / vanilla CLIP load through **one dependency**
  (`open_clip`'s `create_model_and_transforms`) — model choice is an eval question, not a
  dependency question, if torch-cpu is the runtime.
- Quality floor: MobileCLIP2-S0 scores 71.5% ImageNet zero-shot vs laion ViT-B-32's 66.6%
  — even the smallest credible candidate clears "must not embarrass itself".
- Interview-relevant talking points surfaced by this research: sigmoid-per-pair loss vs
  global softmax (SigLIP), distillation via active data curation (SigLIP2),
  multi-modal reinforced training + reparameterization before export (MobileCLIP2),
  dynamic-int8 surviving where static PTQ destroys CLIP retrieval (~95% retention after
  Conv+BN fusion per published CPU-focused study).

## Verified weights sizes (the real disk cost)

From actual HF repos (checked 2026-08-25):

| Artifact | Size | Note |
|---|---|---|
| laion ViT-B-32 fp32 safetensors | ~600MB | fp16-style checkpoints exist via open_clip |
| SigLIP2-base fp32 combined ONNX | **1.5GB** | 256k-vocab Gemma tokenizer inflates text tower to 1.13GB alone |
| SigLIP2-base fp16 combined ONNX | 751MB | `onnx-community/siglip2-base-patch16-256-ONNX` |
| SigLIP2-base **int8** combined ONNX | **378MB** | same repo; vision int8 94.7MB + text int8 283MB |
| MobileCLIP2-S0 fp32 checkpoint | ~215MB | smallest reputable joint-model option found |

Reputable source map:

- `google/siglip2-*` — official Google, Apache-2.0.
- `laion/CLIP-ViT-B-32-laion2B-s34B-b79K` — LAION e.V., MIT.
- `apple/MobileCLIP2-*` — official Apple; `timm/MobileCLIP2-*-OpenCLIP` = canonical
  OpenCLIP-format port by timm's maintainer (14.6k dl/mo). License `apple-amlr` — fine
  for personal/portfolio use, one ADR sentence required.
- `onnx-community/*-ONNX` — HF-staff-run org (Xenova / transformers.js maintainer),
  verified uploads, full quantization ladder (fp32/fp16/int8/q4f16).
- Avoided: `plhery/mobileclip2-onnx`, `memojo/*` etc. — personal accounts,
  vision-tower-only exports anyway (built for transformers.js).

## Runtime comparison

| Runtime | Wheel download | Installed est. | Notes |
|---|---|---|---|
| torch-cpu (dedicated index) | ~192MB (torch) + torchvision/open_clip | ~230MB | uv pins via documented `[[tool.uv.index]]` explicit + `[tool.uv.sources]`; zero preprocessing risk; loads all candidate models incl. MobileCLIP2/SigLIP2 natively |
| onnxruntime | **~20MB** | ~40MB | cp314 wheels confirmed; mature transformer tuning; needs own preprocessing + tokenizer glue |
| **OpenCV 5 DNN** | 54MB headless wheel | ~120–150MB | see below |

### OpenCV 5 specifics (released June 2026)

From the release page (opencv.org/opencv-5):

- New graph-based DNN engine: ONNX operator coverage 22% → 80%+, dynamic shapes,
  QDQ quantized graphs, attention/MatMul fusion with FlashAttention-style kernels.
- Head-to-head vs ONNX Runtime on CPU (i9-14900KS): **beats ORT on transformer-class
  models** — DINOv2-small +24.4%, OWLv2 +36.6%, BiRefNet +32.4%, YOLOv8n +11.5%.
  CLIP ViT towers are exactly the fused-attention pattern.
- CLIP is on their validated out-of-the-box model list.
- Native tokenizer + KV-cache ship in-library (built for GPT-2/Gemma/Qwen families).
  CLIP's text tower uses GPT-2-style BPE (49408 vocab) — plausibly covered, but no
  documented CLIP-text path → spike item.
- Three engines behind one API (`ENGINE_AUTO` default); new engine is CPU-only at launch —
  irrelevant here, CPU-only is the requirement.
- Preprocessing (`imread`/`resize`/`blobFromImages`) covers thumbnail→tensor without Pillow.

## Host feasibility (verified against dev machine)

Machine: Debian 13 (trixie), glibc 2.41, x86_64, Python pinned 3.14.3 via `.python-version`.

- OpenCV 5.0.0.93 pip wheels uploaded 2026-07-02; tagged `cp37-abi3` (stable ABI since
  4.5.x) → **no cp313/cp314 wheel needed**, installs on the 3.14 pin directly.
- `manylinux_2_17` / `manylinux_2_28` tags satisfied by host glibc — plain native install.
- **headless variant needs zero extra system packages** (no libGL/libGTK); full variant
  drags GUI libs — skip it.
- No GPU/CUDA involvement → nothing forces Docker. Docker stays optional as today;
  image grows by only ~150MB if ever built with extras.

Total added footprint for the leading stack (OpenCV runtime + int8 weights cached in
`~/.cache`): **~54MB pip delta + 215–378MB first-run weight download**, repo untouched.

## Dead ends (documented so future-me doesn't re-walk them)

- **open-clip-torch with default PyPI wheels**: the original 2.5GB scare. Cause is CUDA
  bundled into Linux PyPI torch (~888MB wheel + ~3GB nvidia deps), not CLIP itself.
  Fix exists either way: cpu-only index pinning (uv-documented) — or skip torch entirely.
- **imgbeddings**: unmaintained since 2022, incompatible with modern huggingface_hub.
- **sqlite-vec**: revived March 2026 (Mozilla-sponsored) but pre-v1 with declared breaking
  changes; ANN/DiskANN alpha-only. Sweet spot is ~100k+ vectors; at ~10³ vectors numpy
  matmul wins outright. Rejected-with-numbers paragraph belongs in the ADR.
- **Gemini Embedding 2** (GA Apr 2026): first natively multimodal API embedding
  (text/image/video/audio/PDF) — but closed weights, API-only. Violates offline/local
  constraint. Worth one ADR sentence as the future upgrade path if video-native
  embeddings ever matter here.
- **Community ONNX mirrors of MobileCLIP** (plhery, memojo): vision-tower-only exports,
  non-canonical sources. Superseded by timm's canonical port.

## Open questions → spikes

1. Does cv2's native tokenizer handle CLIP BPE end-to-end? (only real functional risk of
   the OpenCV path)
2. imgs/sec cold/warm, RSS, query latency per runtime on real thumbnails.
3. Retrieval sanity: ~10 hand-written queries ("rainy descent", "forest singletrack", …)
   judged recall@k on my library — ViT-B-32 vs SigLIP2-b32-int8 vs MobileCLIP2-S0.
4. Weight sourcing for OpenCV/ORT path: onnx-community int8 exports vs one-time
   self-export of laion B-32 (reproducibility vs convenience).

Decision goes to `docs/adr/0001-semantic-search-stack.md` once spikes run.

## Spike results (2026-08-25, spike F executed)

Environment: Debian 13 host, Python 3.14.3, cv2 5.0.0 pip wheel (abi3 — installs and
imports fine on the pinned interpreter), ORT 1.29.0, weights =
`onnx-community/siglip2-base-patch16-256-ONNX` @ `d1114256`.

**OpenCV 5 DNN path: rejected, with numbers.**

| artifact | result |
|---|---|
| int8 towers/combined (`DynamicQuantizeLinear` ops) | new parser refuses, classic parser errors — unsupported op |
| q4f16 (`MatMulNBits`) | unsupported op |
| fp16 separate towers | load and run (~1.05s vision fwd), but outputs are raw token states — **projection head missing** from tower-only exports |
| fp16 combined | loads; default output is pairwise logits `(1,1)`, no cached-image-embedding workflow |

The release page's "QDQ support" covers *static* quantization only; every quantized
artifact in the onnx-community ladder uses *dynamic* quantization. Revisit if/when
cv.dnn gains DynamicQuantizeLinear/MatMulNBits.

**onnxruntime path: works today, chosen as the shipping runtime.**

- int8 combined model (378MB) runs clean; requesting `image_embeds` / `text_embeds`
  yields proper L2-normalized 768-d embeddings (ORT requires the unused modality as a
  dummy feed — measured overhead included below).
- Throughput: ~1.8–2 img/s batch indexing; text query median ~1.0s per call.
- For a ~10³-thumb library that is a one-time ~10min index and acceptable interactive
  query latency; the npz cache makes repeat syncs free (measured: 5ms).
- End-to-end pipeline validated through the packaged code path
  (`build_encoders` → `update_embeddings` → `search`): correct top-1 ranking on
  synthetic color queries, norms ≈ 1.0.

**Remaining before ADR:** quality eval (question 3) against the real library with the
10-query set; torch-cpu baseline comparison is optional now that ORT satisfies size,
correctness, and maintenance criteria.

### Session tuning (2026-08-25, follow-up)

ORT `SessionOptions` on the 8-logical-core host: `intra_op_num_threads=4`
(physical-core heuristic) + `ORT_ENABLE_ALL` graph optimizations measured
**3.1 vs 2.0 img/s** indexing and **357 vs 875ms** query latency. Wired into
`ort_clip.py`; override threads via `EMBEDDINGS_THREADS`.

Model size note: SigLIP2-B/32-256 is the fastest variant in Google's lineup
(64 vision tokens/img; b16-224 = 196 tokens ≈ 2–3× slower for ~4pt quality).
Video resolution is decoupled from embedding cost — search operates on 400px
ffmpeg thumbnails, so a 4K library costs the same as a 720p one.

## Final decision (2026-08-25): torch-cpu, official weights

The onnx-community int8 artifact was dropped on provenance grounds (converted
third-party upload). Re-benchmarked with the **official**
`google/siglip2-base-patch32-256` checkpoint via transformers + torch-cpu:

| metric | ORT int8 combined | torch-cpu fp32 official |
|---|---|---|
| pip delta in extra | ~30MB | ~230MB (opt-in extra only) |
| weight download | 378MB int8 | ~1.1GB fp32, cached outside repo |
| indexing | 3.1 img/s | **6.1 img/s** |
| query latency | 357ms (incl. wasted dummy vision pass) | **~210ms single / 0.58s for 3 queries** |
| provenance | converted third-party | **first-party Google repo, revision-pinned** |
| GPU later | re-export needed (int8 is CPU-only trick) | wheel swap + `EMBEDDINGS_DEVICE=cuda` |

Chosen: torch. Simpler provenance, faster on both axes that matter, native GPU
path; cost is a bigger opt-in install.

Implementation findings worth remembering:

- **Pin `transformers>=4.49,<5`** — v5 refactored SigLIP2 (`get_*_features`
  returns raw `BaseModelOutputWithPooling`, projections moved into towers,
  tokenizer drops `attention_mask`) and cross-modal alignment broke under it.
- The official tokenizer config declares `model_input_names: ["input_ids"]` —
  the text tower trains on full padded sequences, no attention mask. Passing an
  explicit mask is harmless but pointless.
- Validation lesson: flat-noise synthetic images are out-of-distribution and
  rank near-randomly (similarities ~0.05–0.10 = noise floor) for ANY CLIP-class
  model. Alignment checks must use real photographs (bear/teddy/beignets probe:
  3/3 correct top-1).
- Measured e2e through the packaged stack (`update_embeddings` → `search`):
  correct top-1 on all real-photo queries, incremental re-sync 5ms.

OpenCV 5 DNN remains documented above as rejected-with-numbers; its benchmark
story stands, its quantized-artifact compatibility does not.

## POC shipped (2026-08-25)

Decision recorded in `docs/adr/0001-semantic-search-stack.md`. What exists now:

- **Whole-video moment search**: `thumbnails.generate_search_frames()` samples a
  frame every `SEARCH_FRAME_INTERVAL` seconds (default 10) into
  `_search/{stem}.fNNNN.jpg`; the unchanged filename-keyed npz store embeds each
  frame; per-frame hits are grouped to the best moment per video and playback
  seeks there (`st.video(start_time=...)`). UI: `ui/pages/005_search.py`.
- **Cost model** (at 6 img/s CPU): 1h footage @10s interval = 360 frames ≈ 1min
  one-time indexing; knob trades density for cost.
- **Deliberate v1 limits**: uniform sampling only (no scene-cut detection), no
  near-duplicate frame dedup, gallery page still uses first-frame thumbnails.
- **Pending**: real-library eval (10 cycling queries, recall@k) — blocked on
  library access; demo-library smoke covers the render path via AppTest.
- **Next research track**: auto-tagging — zero-shot classification over the
  already-sampled frames to suggest tags in the tagging grid; sketched in
  gitignored `docs/plans/2026-08-25_plan_autotag_research.md`.

## Vector storage analysis (2026-08-25)

The POC's npz + frame-directory approach works but is not queryable and hides
facts in filenames. Evaluated the 2026 embedded vector-store field (sqlite3
BLOB, LanceDB, sqlite-vec, DuckDB VSS, Chroma) against this project's scale
(~10⁴–10⁵ frames): retrieval quality is identical across engines, SQLite-family
is fastest at small corpus, and only LanceDB survives past ~300k frames.

**Verdict: plain stdlib SQLite file** — full analysis, schema, and migration
trigger recorded in `docs/adr/0002-vector-storage.md`. Implementation deferred;
the npz store remains operational until the swap lands.

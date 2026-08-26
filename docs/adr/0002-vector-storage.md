# ADR 0002: Vector storage — plain SQLite file

Status: decision accepted, implementation pending · Date: 2026-08-25
Research: `docs/research/embedding-models.md` · Related: ADR 0001 (model choice)

## Context

The semantic-search POC stores per-frame embeddings in a loose npz file plus a
directory of sampled frame JPEGs (`_search/*.jpg`). That works but is
architecturally smelly next to the tidy `library.parquet`: no queryable facts
(video/frame/timestamp live in filename strings), no incremental deletes, no
visibility into size. Goal: one proper database file for vectors, KISS, fast,
reliable — without committing to infrastructure a personal tool will never need.

Scale reality: frames = hours_of_footage × 360 at the default 10s interval.
A 50h library ≈ 18k frames (~55MB of float32); even a 300h library stays under
110k rows where brute-force numpy search is milliseconds.

## Analysis (2026-06/07 sources: vecdb-bench, dreaming.press embedded-store guides)

| engine | index | deps cost | single file | maturity | notes |
|---|---|---|---|---|---|
| **sqlite3 stdlib + BLOB** | brute-force numpy | zero (stdlib) | ✅ one `.db` | forever-stable | fastest measured stack at small scale (0.3–1ms queries in 2026 benchmarks); matrix cached in RAM after first load |
| LanceDB | IVF-PQ / HNSW ANN, disk-backed, larger-than-RAM | ~50MB + dep tree | ❌ directory of lance fragments | pre-1.0 (0.3x) | purpose-built; MVCC/versioning; the only engine comfortable past ~300k frames |
| sqlite-vec | brute-force only (ANN unshipped — issue #25 open since 2024) | loadable extension | ✅ | pre-1.0 | strictly dominated by stdlib sqlite3 here: same brute-force, extra dependency |
| DuckDB VSS | HNSW with **experimental persistence** | ~40MB | ✅ | experimental | WAL recovery unimplemented → unclean shutdown can corrupt index; slowest queries; OOM reports at scale |
| Chroma | in-memory ANN (~1M RAM ceiling) | heavy (drags ONNX runtime et al.) | ❌ | ok | anti-KISS for this project |

Benchmark consensus across independent 2026 comparisons: retrieval quality is
identical across engines (rerankers equalize), SQLite-family is fastest at
small corpus, and the only axis that ever forces a move is corpus size.

## Decision

**Single SQLite file via the standard library.** No new dependencies.

```sql
CREATE TABLE frames (
  key        TEXT PRIMARY KEY,   -- "{video_stem}.f{idx:04d}"
  video      TEXT NOT NULL,
  frame_idx  INTEGER NOT NULL,
  seconds    REAL NOT NULL,
  model_id   TEXT NOT NULL,      -- ADR 0001 model guard, now column-level
  dim        INTEGER NOT NULL,
  vector     BLOB NOT NULL       -- float32[768] ≈ 3KB/frame
);
CREATE INDEX idx_frames_video ON frames(video);
```

- Search path: one `SELECT … WHERE model_id = ?` → numpy matrix (cached per
  session) → existing cosine top-k in `embeddings.py` (unchanged math).
- Incremental indexing = UPSERT per video; resampling = `DELETE WHERE video = ?`
  then re-insert. Filename string-parsing hacks (`rpartition(".f")`) die.
- Location: `EMBEDDINGS_DB` env, default `.cache/embeddings.sqlite3` alongside
  the other caches.

Confirmed sub-decisions:

- **Fresh start** — no npz migration; re-embedding is the cheap part anyway.
- **Sampled JPEG cache stays** on disk (`.cache/thumbnails/_search/`, 512px) as
  a decode cache; deleting it costs ffmpeg passes, never data.

## Migration trigger (when to revisit)

If projected frames cross ~300k (≈800h of footage at 10s interval), move to
**LanceDB**: vectors already live in clean columns, so the export is a SELECT.
Until then any ANN engine is complexity purchased for nothing.

## Consequences

- The current npz remains the operational store until this is implemented;
  swap lands as `vector_store.py` + page rewiring in one small change.
- Backup story improves to "copy two files" (parquet + embeddings db).
- Size becomes SQL-visible (`SELECT SUM(LENGTH(vector)) FROM frames`).

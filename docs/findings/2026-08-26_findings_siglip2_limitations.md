# SigLIP2 Limitations on Narrow-Domain Video

## Date: 2026-08-26

## Problem

User's library is 308 cycling videos (helmet-cam, similar terrain). Text→video
search returns random-looking results for most queries.

## Root cause

SigLIP2-B/16-224 embedding space is highly isotropic on this corpus:

- **Cross-similarity**: 0.89 mean (search frames), 0.79 mean (poster thumbs)
- **Score range**: 0.04–0.12 out of [-1, 1]
- **Effect**: all frames point in nearly the same direction; text queries can
  barely distinguish them

This is a property of the model + data combination, not a bug. SigLIP2 was
trained on diverse web photos. Cycling helmet-cam footage is a narrow slice
the model sees as visually homogeneous.

## What works

- **Scene-level ranking**: "mountains" returns mountain frames first (rank
  correct, absolute signal weak at 12%)
- **Scene-level ranking**: "forest path" returns forest frames first
- **Rejection**: "kitchen" correctly fails (highest score 0.07)

## What doesn't work

- **Item-level search**: "pink dress", "red gloves" return random cycling
  frames (noise floor 0.05–0.10)
- **Absolute scores**: meaningless due to anisotropy; only rank order has
  signal, and even that is weak
- **Model size**: so400m gave identical rankings at 4× cost
- **Prompt engineering**: bare nouns ≈ caption phrasing, no gain

## Implications

1. The system is useful for **coarse filtering** (mountain vs city vs forest)
   but not for **fine retrieval** (find this specific object/person)

2. The UI should probably **hide low-confidence results** (threshold ~0.10)
   rather than showing random cycling frames as "matches"

3. For item-level search, a different approach may be needed:
   - Image→image search (user uploads reference frame)
   - Finetuned model on cycling-specific vocabulary
   - Object detection + metadata (but user rejected boxes)

## Verified on

- SigLIP2-B/16-224 (primary, current)
- SigLIP2-So400m (tested, rejected — identical rankings, 4× cost)
- 308 videos / 804 indexed frames (67 videos sampled so far)

## Test data

- 168 poster thumbnails (sanity check set)
- 804 search frames (12 per video × 67 videos)
- eval_labels.json with 4 queries (cycling path, red gloves, singletrack, mountains)

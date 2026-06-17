# HF Space Deployment Handoff

**Date:** 2026-06-15  
**Repo:** `/Users/pranay/Projects/shopstack`  
**Space:** `pranaysuyash/shopstack`

## What We Verified

- The current working app is already reflected in the Hugging Face Space after upload.
- Space runtime is `READY` on `cpu-basic`.
- Space sha matches the uploaded commit: `22ef457b14c28bda87550f7b9cc7a3e405dff847`.
- The Space card is live at `https://pranaysuyash-shopstack.hf.space`.
- The app-specific Space secret `SHOPSTACK_HF_API_KEY` is present.
- No Space-level variables are currently set.

## Upload Path Used

The Space was updated from a clean export of the committed tree, not from the dirty working directory:

```bash
git archive --format=tar HEAD --output=/private/tmp/shopstack-head.tar
tar -xf /private/tmp/shopstack-head.tar -C /private/tmp/shopstack-space-deploy
hf upload pranaysuyash/shopstack /private/tmp/shopstack-space-deploy \
  --repo-type space \
  --commit-message "Sync ShopStack HEAD 6f8adfc" \
  --commit-description "Uploaded clean HEAD snapshot from /Users/pranay/Projects/shopstack to keep the HF Space aligned with the current working app."
```

The upload produced commit:

- `https://huggingface.co/spaces/pranaysuyash/shopstack/commit/22ef457b14c28bda87550f7b9cc7a3e405dff847`

## Current Space Settings

From `hf spaces info`:

- SDK: `gradio`
- Hardware: `cpu-basic`
- Sleep time: `172800`
- Dev mode: `false`
- Space stage: `RUNNING`

From `hf spaces secrets list`:

- `SHOPSTACK_HF_API_KEY`

From `hf spaces variables list`:

- none

## Model Support Matrix

### Works on the Space as-is

- Mock / off-grid app path.
- Hugging Face Inference API planner path when `SHOPSTACK_OFF_THE_GRID=false`, `SHOPSTACK_PLANNER_BACKEND=huggingface`, and `SHOPSTACK_HF_API_KEY` is present.
- Providers that only need remote inference or lightweight runtime support.

### Space-safe but config-dependent

- `huggingface` planner backend.
- `whisper` backend if the OpenAI key is configured.
- `openai` provider paths if the OpenAI key is configured.
- `glm_ocr`, `birefnet`, `nomic`, and other transformer-backed providers only if their dependencies are actually installed in the Space image and the runtime can load them.

### Local-only or not Space-safe by default

- MLX-backed local inference.
- `llama_cpp` / local GGUF inference.
- Apple Silicon-specific flows.
- Any provider that depends on native modules or large model loads not included in the Space image.

## Practical Conclusion

The current Space deployment is aligned with the current repo snapshot, but not every model path is guaranteed to work on Spaces.

The safest assumption is:

- the app boots and the mock/off-grid experience works,
- the HF planner path works when its secret/env configuration is present,
- local Apple Silicon model paths stay local-only unless the Space image explicitly supports them.

## Follow-Up Checks

1. Re-run `hf spaces info pranaysuyash/shopstack` after future uploads to confirm the Space sha matches the intended commit.
2. Re-check `hf spaces secrets list` if model-backed features stop working.
3. Keep the committed tree clean before future uploads so the Space only receives intentional changes.

## Follow-Up Fix

The live Space surfaced a PWA regression where `/sw.js` returned HTML
instead of JavaScript. The fix was to wrap `gr.Blocks.launch()` so the
PWA and health routes are re-mounted after Gradio recreates the FastAPI
app. That change is in `app.py` and is covered by
`tests/test_app.py::test_launch_reinstalls_pwa_and_health_routes` plus
`tests/test_pwa_runtime.py`.

## Live Retest Note

The household-selection error reported during browser use has not been
reproduced locally. The household state machine is covered by
`tests/test_household_state.py`, and the live Space should be retested
against the `22ef457...` build now that the PWA route issue is resolved.

## 2026-06-17 Runtime Addendum

The runtime architecture has since shifted to a FastAPI host in
`shopstack/server.py`, with the Gradio UI mounted under that host as a
migration bridge. The next Space deployment should validate the FastAPI
entrypoint explicitly and not assume the old Gradio-root launch path is
still the primary runtime contract.

## 2026-06-17 Command Surface Addendum

The shared command surface now has a versioned HTTP preview path at
`POST /api/v1/command/preview` and a household-scoped execution path at
`POST /api/v1/command/execute`. Both use the same deterministic intent
rules as the Today-tab input; preview is safe to call without auth,
and execute dispatches through the shared command handlers so mobile
and web clients can use the canonical behavior without reimplementing
the parser or mutation logic.

The same trace layer now powers `GET /api/v1/command/recent`, which
returns the recent executed command history for a household without
adding a second log store.

## 2026-06-17 Frontend Shell Addendum

The root route is now an API-first FastAPI shell instead of the Gradio
workspace. The shell renders household state, command preview/execute,
auth, and recent command history from the v1 API, while Gradio remains
available under `/gradio` as the compatibility surface for legacy
screens and tests.

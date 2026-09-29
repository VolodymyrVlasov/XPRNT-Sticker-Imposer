You are working in the project root.
Do NOT modify existing working code beyond what is listed below.
Base branch: `main`. Commit and push directly to `main` (single-maintainer repo).

## GOAL

Fix a `NameError` that currently breaks importing `server/core/shape_inspect.py`
entirely (and therefore the whole server, since `server/routes/analyze_shape.py`
imports from it) — introduced by the previous commit (`cf9b1f2`, the
OCG layer-detection feature).

## WHY

`detect_layers()` is defined with a return-type annotation:

```python
def detect_layers(path: str) -> LayerDetectionResult:
```

but the `LayerDetectionResult` dataclass is defined **later in the same file**
(after `ContourSegment`/`ContourSubpath`, just before `ShapeArtworkInfo`).
This file has no `from __future__ import annotations` at the top, so Python
evaluates function annotations **eagerly, at `def`-time** — meaning
`LayerDetectionResult` must already exist as a name in the module when this
`def` statement runs. It doesn't yet (it's defined ~75 lines further down),
so importing this module currently raises:

```
NameError: name 'LayerDetectionResult' is not defined
```

**Please confirm this yourself first** by starting the server
(`python run_server.py`) and checking whether it fails to start / the
`/api/analyze-shape` route fails to load — this should reproduce immediately.
If for some reason it does NOT reproduce (e.g. the file on disk differs from
what's described here), stop and report that discrepancy rather than
applying the fix blindly.

## STEP 1 — server/core/shape_inspect.py — fix the forward reference

Add this as the **first line of the file, before the module docstring**
(this is the standard placement — a `from __future__` import must precede
even the docstring is fine either way, but conventionally goes first; if
your Python tooling insists the docstring must stay literally first, put it
immediately after the docstring instead — either is valid, just make sure
it's before any other code):

```python
from __future__ import annotations
```

This defers all annotation evaluation in this file to string form (PEP 563),
so `detect_layers`'s `-> LayerDetectionResult` no longer needs
`LayerDetectionResult` to exist yet at `def`-time. This is a standard,
low-risk fix — nothing in this file calls `typing.get_type_hints()` or
otherwise needs annotations resolved to real objects at runtime, so behavior
is otherwise unchanged.

Do not reorder any functions or classes, do not change any logic — this
should be a true one-line diff.

## STEP 2 — VERIFY

1. Start the server (`python run_server.py`) and confirm it starts cleanly
   with no import errors.
2. Hit `/api/analyze-shape` with a real (or synthetic) shape-mode test PDF
   and confirm it returns 200 with a `layer_info` field in the response —
   both for a plain file (no OCG layers → `classification: "none"`) and, if
   you still have them, one of the synthetic multi-layer test files from the
   previous session's smoke test.
3. Confirm `/api/generate-shape` and `/api/generate-batch-shape` still work
   (these routes also transitively import `shape_inspect.py`).

## STEP 3 — COMMIT + PUSH

```
git add server/core/shape_inspect.py
git commit -m "fix: NameError on import in shape_inspect.py (forward reference to LayerDetectionResult)"
git push origin main
```

## STEP 4 — SUMMARY

### ✅ Completed
### 🧪 Verify results (STEP 2, all 3 points — please paste actual command/response output, not just "confirmed")

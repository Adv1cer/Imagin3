# Imagin — POC Product Priority (governing)

> **Status:** POC / generation-quality feasibility. Corrected 2026-07-23.
>
> This document records the **governing priority** for the POC. Where the
> older week-by-week timeline in `OKF-Imagin_5.md §9` implies an
> infrastructure-first ordering (Compute Gateway/queue in Week 2, API/SSE in
> Week 6), **this document takes precedence** for sequencing decisions.

## POC goal

Prove that the local/DGX generation system can **consistently produce
high-quality outputs** across the required use cases. The next milestone is
NOT "the API works." It is:

> Across a defined poster benchmark, the local DGX pipeline produces
> technically valid candidates whose semantic and visual quality can be
> measured and accepted by a human reviewer.

`overall_status=pass` from automated QA means **technical correctness only**
(geometry, exact Thai OCR, no unexpected generated text, QR decode, logo
provenance, overflow, text-free background). It is **not** proof of visual
or semantic quality, and must never be counted as human approval.

## Priority order (do these in this sequence)

1. **Generation-quality proof** — the pipeline reliably produces technically
   valid candidates.
2. **Poster quality benchmark** — measure quality across many
   prompts/orgs/templates/aspect-ratios/audiences with human review
   (`imagin.benchmark`, `benchmarks/poster_cases.yaml`).
3. **Central Brain / prompt-derived copy** — replace the hardcoded Week-1
   copy with structured, prompt-derived headline/body/CTA (this is the real
   blocker to "generate perfect" for arbitrary prompts).
4. **General-image quality proof** — photoreal / illustration / anime /
   product / environment / people / objects.
5. **Infographic proof** — research, fact selection/verification, structured
   hierarchy, charts, exact Thai text/numbers, deterministic composition.
6. **Image-edit proof** — reference input, inpaint/outpaint, edit only the
   requested region, preserve everything else + verified logos + text.
7. **Human quality evaluation** — repeatable benchmark + reviewer decisions
   to find failure patterns and tune prompts/templates/workflows/models.
8. **Thin demo UI** — only after the major quality hypotheses are tested.

## Compute Gateway scope during POC

Compute Gateway work during the POC is limited to **sequential execution
(concurrency 1)** plus **memory and latency measurement** to prove local DGX
feasibility. Nothing more.

## Explicitly deferred (NOT POC priorities)

Production-grade multi-user API, Redis/Celery queue architecture, RBAC, full
authentication, multi-tenant permissions, 20k-user scaling, Kubernetes,
autoscaling, advanced monitoring, enterprise backup, full production
rollout. A minimal sequential runner is sufficient for the POC.

## Hard constraints (unchanged, never weaken)

- On-premise / DGX-first. No external AI API. If an outside service seems
  unavoidable, stop, explain why, and calculate cost before using it.
- Do not train a new foundation image model.
- Do not weaken OCR exact-match, unexpected-text, QR, logo-provenance,
  layout-contract, or overflow QA gates.
- The image model never draws the headline/body/CTA, the official logo, or
  the QR — those are composited deterministically.
- Do not hardcode benchmark success; do not treat technical QA pass as human
  visual approval.

## Section references used by the codebase

Code comments cite `PROD.md §…` for provenance/QA rules established during
Week 1 (§6.3 deterministic composition, §7.1a logo scoring/thresholds, §7.3
logo evidence scoring, §7.4 fresh QR validation, §7.6 respectful crawling +
SSRF, §8.1 UUID/timestamptz + no-overwrite versioning, §8.5 Alembic-only,
§15.1 Week-1 exit evidence). Those rules remain in force; this document does
not restate them line-by-line, and adds the corrected POC priority above.

"""Poster Quality Benchmark Harness.

Governing POC priority (2026-07-23): prove generation *quality* across many
prompts/orgs/templates/aspect-ratios before building any production API,
queue, or auth. This package expands a versioned dataset into individual
candidates, runs them sequentially (concurrency 1) through the EXISTING
real pipeline, preserves every technical QA gate, and captures both machine
metrics and human-review fields so semantic/visual quality can be measured
and accepted by a reviewer.

Design boundary: the harness never re-implements generation and never
weakens QA. dataset/manifest/harness/review carry NO native or pipeline
imports, so they run in any environment; only benchmark.cli reaches the
real DGX pipeline (lazily). A pluggable generate-fn is the seam between the
two, which also makes the whole harness testable offline with a fake
generator (no DGX, no Postgres, no PyGObject).
"""

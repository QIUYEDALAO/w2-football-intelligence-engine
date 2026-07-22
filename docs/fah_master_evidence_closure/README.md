# FAH Master Evidence Closure

This directory intentionally does not contain tracked approval artifacts.

Run `scripts/run_fah_master_pipeline.py --artifact-root <path>` to create a fresh
offline evidence package from the configured private data root. When private data
is unavailable, the runner emits a fail-closed `DATA_REQUIRED` package that ends
at `MANUAL_APPROVAL_REQUIRED`.

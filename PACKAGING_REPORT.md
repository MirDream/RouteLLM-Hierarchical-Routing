# Packaging and Reproduction Report

| Check | Result |
|---|---|
| GitHub Account | `MirDream` |
| GitHub Repository | <https://github.com/MirDream/RouteLLM-Hierarchical-Routing> |
| Visibility | Private |
| Branch | `main` |
| Validated Release Content Commit | `dcbe7f7b01fd663a81130b3ad3fe1d0a71124e63` |
| Short Commit | `dcbe7f7` |
| Original Source | Isolated stable project snapshot; not included as a parent workspace |
| Release Directory | Repository root |
| GitHub Push | PASS |
| Clean Git Clone | PASS |
| Fresh `.venv` | PASS |
| Clean Install | PASS |
| Unit Tests | 19 / 19 passed; 0 failures; 0 errors |
| Visual Demo | PASS; Streamlit HTTP 200 |
| Official Mode | PASS; real `Controller.route -> RandomRouter.route` path |
| Hierarchical Mode | PASS; real controller, router, quality, scheduler, and utility path |
| Low Load | PASS; `model-a@cloud` |
| Cloud Congestion | PASS; `model-b@edge-1` |
| Edge Congestion | PASS; `model-a@cloud` |
| `run_demo.ps1` | PASS |
| `run_simulation.ps1` | PASS |
| `run_experiments.ps1` | PASS; 60 runs completed |
| Absolute Path Scan | PASS; 0 tracked matches |
| Secret Scan | PASS; 0 likely secret values |
| License / Attribution | PASS; upstream Apache-2.0 license preserved and attribution documented |
| PPT Included | Yes; `docs/RouteLLM_Hierarchical_Routing_Final.pptx` |

## Clean Reproduction Procedure Used

1. Cloned the Private GitHub repository into a new directory.
2. Ran `setup_windows.ps1` with Python 3.12.14 available as `python`.
3. Created a new repository-local `.venv`; no previous environment was copied.
4. Installed the curated core and Streamlit dependency lists.
5. Installed the local repository in editable mode.
6. Ran the import smoke test and all 19 unit/integration tests.
7. Ran Official RouteLLM mode and all three hierarchical resource scenarios.
8. Ran the command-line demo, simulation, and complete experiment matrix.
9. Started `run_visual_demo.ps1 -Headless -NoPause` and verified an HTTP 200 response. Port 8501 was occupied during validation, so the launcher correctly selected port 8502.
10. Re-scanned tracked files for local absolute paths, old virtual-environment references, forbidden generated files, and likely secrets.

No API key, token, existing virtual environment, Codex runtime package, cache directory, or model weight is tracked by this repository.

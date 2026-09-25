# RouteLLM Hierarchical Resource-Aware Routing

A reproducible Windows-friendly extension of [lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM) for hierarchical multi-model and model-node routing. The repository contains a deterministic cloud-edge simulator, four routing strategies, reproducible experiments, and a dual-mode Streamlit classroom demo.

The classroom path is fully offline: it needs no API key, paid LLM endpoint, model checkpoint, or GPU.

## Overview

```text
Official RouteLLM
Query -> Router -> Score -> Threshold -> Strong / Weak Model

Our extension
Query -> Query Encoder -> Predicted Quality -> Top-K Models -> q_min
      -> Resource State -> Resource-Aware Scheduler
      -> Model x Node Utility -> Final Model + Node
```

The first layer asks **which models are capable of answering the query**. The second layer asks **which capable model-node pair is preferable under the current resource state**.

## Based on RouteLLM

This project retains source and interfaces from:

- Official repository: [lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM)
- Paper: [RouteLLM: Learning to Route LLMs with Preference Data](https://proceedings.iclr.cc/paper_files/paper/2025/hash/5503a7c69d48a2f86fc00b3dc09de686-Abstract-Conference.html), ICLR 2025
- Upstream license: Apache License 2.0; the original `LICENSE` is preserved.

### Official / retained components

- `routellm/controller.py`
- `routellm/routers/routers.py`
- Official routing interfaces and the offline `RandomRouter`
- Visual Demo official mode: `Controller.route -> RandomRouter.route`

The official demo stops after model selection. Final LLM response generation is intentionally disabled, so no external API is called.

### Our incremental extension

- `MultiModelRouter` and deterministic predicted quality
- configurable Top-K candidate selection
- `q_min` quality constraint and quality fallback
- `ResourceAwareScheduler` and normalized model-node utility
- `HierarchicalController`
- deterministic cloud-edge resource simulation
- four-strategy, three-workload, multi-seed experiments
- dual-mode Streamlit visualization

`capability_only` is a **simulation baseline**. It is not presented as the official RouteLLM MF, BERT, or other learned router.

## Key Features

- Authentic offline Official RouteLLM model-selection path
- Multi-model capability ranking and Top-K candidates
- Quality-constrained resource-aware scheduling
- Joint model and execution-node decision
- Low Load, Cloud Congestion, and Edge Congestion scenarios
- deterministic seeds and identical request traces across strategies
- reproducible CSV/JSON experiment results
- 16:9 projection-friendly classroom UI

## Project Structure

```text
RouteLLM-Hierarchical-Routing/
|-- routellm/                 # retained RouteLLM code + hierarchical extension
|-- simulation/               # workload, simulator, metrics, experiments
|-- configs/                  # deterministic experiment configuration
|-- tests/                    # 19 unit/integration tests
|-- examples/                 # command-line hierarchical demo
|-- results/                  # raw and summarized experiment results
|-- docs/                     # demo guide, implementation notes, final PPT
|-- visual_demo.py
|-- setup_windows.ps1
|-- run_visual_demo.ps1
|-- run_demo.ps1
|-- run_simulation.ps1
|-- run_experiments.ps1
|-- requirements.txt
|-- requirements-visual-demo.txt
|-- pyproject.toml
|-- QUICKSTART.md
`-- LICENSE
```

## Requirements

- Windows 10 or Windows 11
- Git
- Python 3.10, 3.11, or 3.12 available as `python` in `PATH`
- PowerShell 5.1 or newer
- Internet access only during dependency installation

CPU-only execution is sufficient. The installer does not download RouteLLM model checkpoints or LLM weights.

## Clean Installation

Open PowerShell:

```powershell
git clone https://github.com/MirDream/RouteLLM-Hierarchical-Routing.git
cd RouteLLM-Hierarchical-Routing
.\setup_windows.ps1
```

The setup script creates `<project>\.venv`, upgrades packaging tools, installs the curated requirements, installs this repository in editable mode, runs an import smoke test, and executes the full unit-test suite.

No existing virtual environment, Codex workspace, cache, API key, or model weight is used.

## Quick Start

```powershell
.\run_visual_demo.ps1
```

Open <http://localhost:8501>. If 8501 is already occupied, the launcher automatically tries 8502.

All PowerShell entry points resolve their project root from `$PSScriptRoot`; they work even when invoked from another current directory.

## Run Visual Demo

```powershell
.\run_visual_demo.ps1
```

Optional flags:

```powershell
.\run_visual_demo.ps1 -Headless
.\run_visual_demo.ps1 -Headless -NoPause
```

### Official Mode

Runs the retained offline path:

```text
Query -> Controller.route -> RandomRouter.route
      -> Routing Score -> Threshold -> Strong / Weak Model
```

The query and threshold are editable. The routing score is computed by the real router; it is not hard-coded.

### Hierarchical Mode

Runs:

```text
HierarchicalController.decide
  -> MultiModelRouter
  -> predicted quality and Top-K
  -> q_min quality constraint
  -> ResourceAwareScheduler
  -> model-node utility
  -> final model + node
```

The UI displays predicted quality, Top-K, resource state, utility components, final decision, quality fallback, “Why not Top-1,” and technical details.

### Scenarios

- **Low Load:** cloud and edge are both lightly loaded.
- **Cloud Congestion:** only the cloud `NodeState` becomes congested.
- **Edge Congestion:** only the edge `NodeState` becomes congested.

Scenarios change resource inputs only. The final result is still produced by the scheduler.

## Run Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Run Command-Line Demo

```powershell
.\run_demo.ps1
```

## Run Simulation

```powershell
.\run_simulation.ps1
```

Outputs are written to `simulation_output/` and are ignored by Git because they are regenerated locally.

## Run Experiments

```powershell
.\run_experiments.ps1
```

The default experiment executes:

```text
4 strategies x 3 workloads x 5 seeds x 300 requests
= 60 runs and 18,000 simulated requests
```

Strategies:

- `capability_only`
- `resource_only`
- `joint_single_stage`
- `hierarchical`

Tracked reference results are stored in:

- `results/raw_results.csv`
- `results/summary.csv`
- `results/summary.json`

## Limitations

- `predicted_quality` is synthetic and simulation-based.
- `actual_quality` is a hidden synthetic ground-truth function used only for evaluation.
- cloud, edge, GPU, VRAM, queue, network, and throughput states are simulated.
- utility weights are manually configured.
- the classroom scale is three models and two nodes.
- this is not a real vLLM or production cloud-edge deployment.

## Future Work

- evaluate on real benchmarks and preference data
- train and calibrate a learned capability predictor
- integrate real GPU, VRAM, queue, and network monitoring
- route across multiple vLLM endpoints
- validate on a real cloud-edge deployment

## Documentation

- [Quick start](QUICKSTART.md)
- [Classroom demo guide](docs/DEMO_GUIDE.md)
- [Implementation notes](docs/IMPLEMENTATION_NOTES.md)
- [Simulation guide](docs/SIMULATION_GUIDE.md)
- [Final classroom presentation](docs/RouteLLM_Hierarchical_Routing_Final.pptx)

## Attribution

Based on and adapted from [lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM). The upstream Apache License 2.0 is preserved in [LICENSE](LICENSE). Hierarchical routing, simulation, experiments, tests, packaging, and visualization additions are incremental work in this repository.

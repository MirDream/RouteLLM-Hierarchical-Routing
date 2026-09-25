# Windows Quick Start

```powershell
git clone https://github.com/MirDream/RouteLLM-Hierarchical-Routing.git
cd RouteLLM-Hierarchical-Routing
.\setup_windows.ps1
.\run_visual_demo.ps1
```

Open <http://localhost:8501>. If that port is busy, the launcher uses port 8502.

- **Mode A — Official RouteLLM:** offline `Controller.route → RandomRouter.route` model selection.
- **Mode B — Hierarchical Router:** predicted quality, Top-K, quality constraint, resource-aware model-node scheduling.

No API key or model checkpoint is required for the classroom demo.

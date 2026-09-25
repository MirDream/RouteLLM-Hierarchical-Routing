"""Projection-friendly Streamlit demo for official and hierarchical RouteLLM.

This file is deliberately a presentation layer.  Official mode delegates to
the original ``routellm.controller.Controller`` and its official ``random``
router.  Hierarchical mode delegates to the existing ``HierarchicalController``
and scheduler; no routing or utility formula is reimplemented here.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import random
from dataclasses import dataclass
from typing import Any

import pandas as pd

# The visual demo is intentionally offline.  This prevents LiteLLM (imported by
# the untouched official Controller) from refreshing its optional price map.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
# Official routers import the OpenAI client eagerly even when RandomRouter is
# selected.  A non-secret placeholder satisfies construction; no API method is
# called in this selection-only demo.  A real user key, if present, is preserved.
os.environ.setdefault("OPENAI_API_KEY", "not-used")

try:
    import streamlit as st
except ModuleNotFoundError:  # Keeps the routing helpers importable for tests.
    st = None

from routellm.config.experiment_config import load_experiment_config
from routellm.controller import Controller
from routellm.hierarchical_controller import DecisionRecord, HierarchicalController
from routellm.monitor.resource_monitor import NodeState, SimulatedResourceMonitor
from routellm.routers.multimodel_router import CapabilityCandidate, MultiModelRouter
from routellm.scheduler.resource_scheduler import ResourceAwareScheduler
from routellm.scheduler.scoring import resource_load
from simulation.simulator import build_profiles


OFFICIAL_SIMPLE_QUERY = "What is 2 + 2?"
OFFICIAL_COMPLEX_QUERY = (
    "Explain the computational complexity of Transformer self-attention and "
    "discuss when sparse attention is useful."
)
HIERARCHICAL_DEFAULT_QUERY = (
    "Explain how Transformer self-attention works and analyze its time complexity."
)
DEMO_SEED = 5
SCENARIOS = ("Low Load", "Cloud Congestion", "Edge Congestion")


@dataclass(frozen=True)
class OfficialDemoResult:
    query: str
    router_name: str
    routing_score: float
    threshold: float
    selected_model: str
    selected_tier: str
    strong_model: str
    weak_model: str
    call_path: str


@dataclass(frozen=True)
class HierarchicalDemoResult:
    query: str
    scenario: str
    record: DecisionRecord
    all_candidates: tuple[CapabilityCandidate, ...]
    actual_qualities: dict[str, float]


def _query_seed(query: str, base_seed: int = 20260924) -> int:
    """Create a stable seed so the official random baseline is demo-reproducible."""

    digest = hashlib.sha256(f"{base_seed}|{query}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def run_official_routing(query: str, threshold: float = 0.60) -> OfficialDemoResult:
    """Run the zero-download official RouteLLM path without invoking an LLM API.

    The score comes from RouteLLM's official ``RandomRouter``.  We replay the
    same RNG state for ``Controller.route`` so the displayed score is exactly
    the score used by the official decision path.  The caller's RNG state is
    restored afterwards.
    """

    if not query.strip():
        raise ValueError("Query cannot be empty")
    strong_model = "gpt-4-1106-preview"
    weak_model = "mixtral-8x7b-instruct-v0.1"
    controller = Controller(
        routers=["random"],
        strong_model=strong_model,
        weak_model=weak_model,
        config={},
    )
    router = controller.routers["random"]
    demo_seed = _query_seed(query)
    original_state = random.getstate()
    try:
        random.seed(demo_seed)
        score = float(router.calculate_strong_win_rate(query))
        random.seed(demo_seed)
        selected = controller.route(query, router="random", threshold=threshold)
    finally:
        random.setstate(original_state)

    expected = strong_model if score >= threshold else weak_model
    if selected != expected:
        raise RuntimeError("Official score and Controller.route decision diverged")
    return OfficialDemoResult(
        query=query,
        router_name="random (official offline router)",
        routing_score=score,
        threshold=threshold,
        selected_model=selected,
        selected_tier="Strong Model" if selected == strong_model else "Weak Model",
        strong_model=strong_model,
        weak_model=weak_model,
        call_path=(
            "routellm/controller.py::Controller.route → "
            "routellm/routers/routers.py::RandomRouter.route"
        ),
    )


def build_resource_scenario(name: str) -> dict[str, NodeState]:
    """Return only resource inputs; the scheduler still makes every decision."""

    if name == "Low Load":
        states = (
            NodeState("cloud", ("model-a", "model-b"), 0.08, 80, 64, 0, 18, 260),
            NodeState("edge-1", ("model-b", "model-c"), 0.15, 24, 20, 0, 9, 75),
        )
    elif name == "Cloud Congestion":
        states = (
            NodeState("cloud", ("model-a", "model-b"), 0.95, 80, 20, 8, 80, 35),
            NodeState("edge-1", ("model-b", "model-c"), 0.25, 24, 18, 1, 10, 70),
        )
    elif name == "Edge Congestion":
        states = (
            NodeState("cloud", ("model-a", "model-b"), 0.18, 80, 60, 0, 35, 120),
            # Free VRAM is intentionally below model-b's 10 GB requirement.
            NodeState("edge-1", ("model-b", "model-c"), 0.96, 24, 5, 9, 18, 25),
        )
    else:
        raise ValueError(f"Unknown scenario: {name}")
    return {state.node: state for state in states}


def build_hierarchical_controller(
    scenario: str,
    *,
    seed: int = DEMO_SEED,
    q_min: float | None = None,
) -> HierarchicalController:
    config = load_experiment_config()
    router = MultiModelRouter(build_profiles())
    monitor = SimulatedResourceMonitor(build_resource_scenario(scenario).values())
    scheduler = ResourceAwareScheduler(
        router.models,
        weights=config.utility_weights,
        q_min=config.q_min if q_min is None else q_min,
        latency_scale_ms=config.latency_scale_ms,
    )
    return HierarchicalController(
        router=router,
        monitor=monitor,
        scheduler=scheduler,
        top_k=config.top_k,
        seed=seed,
    )


def run_hierarchical_routing(
    query: str,
    scenario: str = "Cloud Congestion",
    *,
    seed: int = DEMO_SEED,
    q_min: float | None = None,
) -> HierarchicalDemoResult:
    """Call the real hierarchical controller, then collect display-only details."""

    if not query.strip():
        raise ValueError("Query cannot be empty")
    controller = build_hierarchical_controller(scenario, seed=seed, q_min=q_min)
    record = controller.decide(query)
    all_candidates = tuple(
        controller.router.rank(
            query,
            top_k=len(controller.router.models),
            seed=controller.seed,
        )
    )
    actual_qualities = {
        model: controller.router.actual_quality(query, model)
        for model in controller.router.models
    }
    selected_rows = [
        row
        for row in record.final_utility_scores
        if row["model"] == record.selected_model and row["node"] == record.selected_node
    ]
    if len(selected_rows) != 1:
        raise RuntimeError("Controller decision is missing from scheduler pair scores")
    return HierarchicalDemoResult(
        query=query,
        scenario=scenario,
        record=record,
        all_candidates=all_candidates,
        actual_qualities=actual_qualities,
    )


def _status_for_node(state: dict[str, Any]) -> tuple[str, str]:
    node = NodeState(
        node=state["node"],
        available_models=tuple(state["available_models"]),
        gpu_utilization=state["gpu_utilization"],
        total_vram_gb=state["total_vram_gb"],
        free_vram_gb=state["free_vram_gb"],
        queue_length=state["queue_length"],
        network_latency_ms=state["network_latency_ms"],
        throughput_tokens_per_sec=state["throughput_tokens_per_sec"],
    )
    load = resource_load(node)
    if load < 0.35:
        return "AVAILABLE", "available"
    if load < 0.70:
        return "BUSY", "busy"
    return "CONGESTED", "congested"


def _escape(value: Any) -> str:
    return html.escape(str(value))


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {max-width: 1500px; padding-top: 1.2rem; padding-bottom: 3rem;}
        h1 {font-size: 2.65rem !important; letter-spacing: -0.03em;}
        h2 {font-size: 1.75rem !important; margin-top: 1.1rem !important;}
        h3 {font-size: 1.28rem !important;}
        p, label, .stMarkdown {font-size: 1.05rem;}
        div[data-testid="stMetricValue"] {font-size: 2rem;}
        .eyebrow {font-size: .82rem; font-weight: 800; letter-spacing: .12em; color: #2563eb;}
        .subtitle {font-size: 1.22rem; color: #475569; margin-top: -.7rem; margin-bottom: 1rem;}
        .info-card {border: 1px solid #dbe4f0; border-radius: 16px; padding: 18px 20px; background: white; box-shadow: 0 4px 18px rgba(15,23,42,.06); min-height: 135px;}
        .purple-card {border-top: 5px solid #7c3aed; background: #faf7ff;}
        .teal-card {border-top: 5px solid #0faaa3; background: #f2fffd;}
        .orange-card {border-top: 5px solid #f59e0b; background: #fffaf0;}
        .blue-card {border-top: 5px solid #2563eb; background: #f5f8ff;}
        .final-card {border: 2px solid #f59e0b; border-radius: 20px; padding: 24px; background: linear-gradient(135deg,#fffaf0,#fff); text-align:center; box-shadow: 0 8px 28px rgba(245,158,11,.15);}
        .final-model {font-size: 2.35rem; font-weight: 850; color: #0f172a; margin: .25rem 0;}
        .badge {display:inline-block; border-radius:999px; padding:5px 10px; font-size:.78rem; font-weight:800; letter-spacing:.04em;}
        .badge-blue {background:#dbeafe;color:#1d4ed8}.badge-purple{background:#ede9fe;color:#6d28d9}.badge-green{background:#d1fae5;color:#047857}.badge-yellow{background:#fef3c7;color:#a16207}.badge-gray{background:#e2e8f0;color:#475569}
        .node-title {font-size:1.4rem;font-weight:800;margin-bottom:.5rem}.node-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px 18px}.node-grid b{color:#0f172a}
        .status-available{color:#047857;font-weight:850}.status-busy{color:#a16207;font-weight:850}.status-congested{color:#dc2626;font-weight:850}
        .flow-row {display:flex;align-items:center;justify-content:center;gap:8px;flex-wrap:wrap;margin:.5rem 0 1.2rem}.flow-box{padding:10px 14px;border-radius:11px;background:#eaf1ff;border:1px solid #bfdbfe;font-weight:750}.flow-arrow{font-size:1.35rem;color:#64748b}.flow-selected{background:#2563eb;color:white;border-color:#2563eb}
        .top-k {font-size:.72rem;background:#7c3aed;color:white;border-radius:999px;padding:3px 8px;font-weight:800;margin-left:6px}.below{font-size:.72rem;background:#fee2e2;color:#b91c1c;border-radius:999px;padding:3px 8px;font-weight:800;margin-left:6px}
        .compare th {background:#0f172a;color:white}.small-note{color:#64748b;font-size:.9rem}.question{font-size:1.05rem;font-weight:700;color:#334155;border-left:4px solid #7c3aed;padding-left:12px}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header() -> None:
    st.title("RouteLLM Routing Demo")
    st.markdown(
        '<div class="subtitle">Official RouteLLM vs Hierarchical Resource-Aware Routing</div>',
        unsafe_allow_html=True,
    )


def _flow(items: list[str], selected: str | None = None) -> None:
    parts: list[str] = []
    for index, item in enumerate(items):
        selected_class = " flow-selected" if item == selected else ""
        parts.append(f'<div class="flow-box{selected_class}">{_escape(item)}</div>')
        if index < len(items) - 1:
            parts.append('<div class="flow-arrow">→</div>')
    st.markdown(f'<div class="flow-row">{"".join(parts)}</div>', unsafe_allow_html=True)


def _render_official() -> None:
    st.markdown('<span class="badge badge-blue">OFFICIAL ROUTELLM BASELINE</span>', unsafe_allow_html=True)
    left, right = st.columns([1.05, 1])
    with left:
        st.markdown("### 1 · Query")
        presets = {
            "Simple example": OFFICIAL_SIMPLE_QUERY,
            "Complex example": OFFICIAL_COMPLEX_QUERY,
        }
        choice = st.selectbox("Query preset", list(presets), key="official_preset")
        if "official_query" not in st.session_state:
            st.session_state.official_query = presets[choice]
        if st.button("Load selected preset", key="load_official"):
            st.session_state.official_query = presets[choice]
        query = st.text_area("Input Query", key="official_query", height=125)
        threshold = st.slider("Routing Threshold", 0.0, 1.0, 0.60, 0.05)
        run = st.button("Run Official RouteLLM", type="primary", width="stretch")
    with right:
        st.markdown(
            """
            <div class="info-card blue-card">
              <div class="eyebrow">DECISION OBJECT</div><div class="node-title">Model</div>
              <div class="eyebrow">KEY QUESTION</div>
              <div>“Which model should answer this query?”</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.info(
            "Offline classroom mode uses RouteLLM's official RandomRouter—the only "
            "zero-checkpoint official router. No score is fabricated."
        )

    if run or "official_result" not in st.session_state:
        try:
            st.session_state.official_result = run_official_routing(query, threshold)
        except Exception as exc:  # pragma: no cover - rendered interactively
            st.error(f"Official routing failed: {exc}")
            return
    result: OfficialDemoResult = st.session_state.official_result
    st.markdown("## 2 · Routing Result")
    cols = st.columns(4)
    cols[0].metric("Router Type", "RandomRouter")
    cols[1].metric("Routing Score", f"{result.routing_score:.3f}")
    cols[2].metric("Threshold", f"{result.threshold:.2f}")
    cols[3].metric("Decision", result.selected_tier)
    st.caption(f"Selected deployment name: `{result.selected_model}`")

    st.markdown("## 3 · Visual Flow")
    _flow(
        ["Query", "Official Router", f"Score {result.routing_score:.3f}", f"Threshold {result.threshold:.2f}", result.selected_tier],
        selected=result.selected_tier,
    )
    st.warning(
        "Model selection reproduced; final LLM response disabled in offline demo."
    )
    st.markdown(
        "**Original RouteLLM decides which model to use, but does not model execution "
        "node or dynamic resource state.**"
    )
    with st.expander("Technical Details"):
        st.json(
            {
                "router_name": result.router_name,
                "routing_score": result.routing_score,
                "threshold": result.threshold,
                "selected_tier": result.selected_tier,
                "selected_model": result.selected_model,
                "strong_model": result.strong_model,
                "weak_model": result.weak_model,
                "official_call_path": result.call_path,
                "inference": "disabled (offline selection-only demo)",
            }
        )


def _render_capability_ranking(result: HierarchicalDemoResult) -> None:
    record = result.record
    top_k_models = {item["model"] for item in record.top_k_candidates}
    st.markdown("## Layer 1 · Model Capability Ranking")
    st.markdown(
        '<div class="question">Task–Model Matching · “Which models are capable of handling this query?”</div>',
        unsafe_allow_html=True,
    )
    for candidate in result.all_candidates:
        is_top_k = candidate.model in top_k_models
        labels = '<span class="top-k">TOP-K</span>' if is_top_k else '<span class="badge badge-gray">OUTSIDE TOP-K</span>'
        if candidate.predicted_quality < record.quality_threshold:
            labels += '<span class="below">BELOW QUALITY THRESHOLD</span>'
        cols = st.columns([1.25, 4.5, 1])
        cols[0].markdown(f"**{candidate.model.upper()}** {labels}", unsafe_allow_html=True)
        cols[1].progress(candidate.predicted_quality)
        cols[2].markdown(f"**{candidate.predicted_quality:.3f}**")


def _render_resources(record: DecisionRecord) -> None:
    st.markdown("## Layer 2 · Real-Time Resource Status")
    st.markdown(
        '<div class="question" style="border-color:#0faaa3">Resource-Aware Scheduling · “Where should a capable model execute now?”</div>',
        unsafe_allow_html=True,
    )
    columns = st.columns(len(record.resource_states))
    for column, (node_name, state) in zip(columns, record.resource_states.items()):
        status, css = _status_for_node(state)
        with column:
            st.markdown(
                f"""
                <div class="info-card teal-card">
                  <div class="node-title">{_escape(node_name.upper())}</div>
                  <div class="node-grid">
                    <span>GPU</span><b>{state['gpu_utilization']:.0%}</b>
                    <span>Queue</span><b>{state['queue_length']}</b>
                    <span>Free VRAM</span><b>{state['free_vram_gb']:.0f} GB</b>
                    <span>Network</span><b>{state['network_latency_ms']:.0f} ms</b>
                    <span>Throughput</span><b>{state['throughput_tokens_per_sec']:.0f} tok/s</b>
                    <span>Status</span><span class="status-{css}">{status}</span>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _pair_table(record: DecisionRecord) -> pd.DataFrame:
    rows = []
    for score in record.final_utility_scores:
        selected = score["model"] == record.selected_model and score["node"] == record.selected_node
        rows.append(
            {
                "Selected": "✓" if selected else "",
                "Model": score["model"],
                "Node": score["node"],
                "Pred. Quality": score["predicted_quality"],
                "Latency (ms)": score["estimated_latency_ms"],
                "Norm. Cost": score["normalized_cost"],
                "Resource Load": score["resource_load"],
                "Utility": score["utility"],
                "Quality OK": "Yes" if score["meets_quality_constraint"] else "No",
                "Feasible": "Yes",
            }
        )
    return pd.DataFrame(rows)


def _render_utility(result: HierarchicalDemoResult) -> None:
    st.markdown("## Model × Node Utility")
    frame = _pair_table(result.record)

    def highlight(row: pd.Series) -> list[str]:
        color = "background-color: #fff0c2; font-weight: 800" if row["Selected"] == "✓" else ""
        return [color] * len(row)

    formats = {
        "Pred. Quality": "{:.3f}",
        "Latency (ms)": "{:.1f}",
        "Norm. Cost": "{:.3f}",
        "Resource Load": "{:.3f}",
        "Utility": "{:.3f}",
    }
    st.dataframe(
        frame.style.apply(highlight, axis=1).format(formats),
        width="stretch",
        hide_index=True,
    )
    weights = load_experiment_config().utility_weights
    st.caption(
        "Utility = "
        f"{weights.alpha_quality:.2f} × quality − {weights.beta_latency:.2f} × latency "
        f"− {weights.gamma_cost:.2f} × cost − {weights.delta_resource_load:.2f} × resource load"
    )


def _best_pair_for_model(record: DecisionRecord, model: str) -> dict[str, Any] | None:
    matches = [row for row in record.final_utility_scores if row["model"] == model]
    return max(matches, key=lambda row: row["utility"], default=None)


def _render_final(result: HierarchicalDemoResult) -> None:
    record = result.record
    selected_pair = _best_pair_for_model(record, record.selected_model)
    top_one = result.all_candidates[0]
    top_pair = _best_pair_for_model(record, top_one.model)
    fallback_badge = (
        '<span class="badge badge-yellow">QUALITY FALLBACK TRIGGERED</span>'
        if record.quality_fallback
        else '<span class="badge badge-green">QUALITY CONSTRAINT SATISFIED</span>'
    )
    st.markdown(
        f"""
        <div class="final-card">
          <div class="eyebrow" style="color:#b45309">FINAL DECISION</div>
          <div class="final-model">{_escape(record.selected_model.upper())} @ {_escape(record.selected_node.upper())}</div>
          {fallback_badge}
          <div style="margin-top:10px">Predicted quality <b>{record.selected_predicted_quality:.3f}</b> · Utility <b>{selected_pair['utility']:.3f}</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if record.quality_fallback:
        st.warning(
            "No feasible candidate satisfied q_min. The highest predicted-quality "
            "feasible model was selected."
        )

    st.markdown("## Why not Top-1 Model?")
    left, middle, right = st.columns([1, 0.35, 1])
    with left:
        top_detail = "No feasible deployment" if top_pair is None else (
            f"Best pair: {top_pair['model']}@{top_pair['node']}  \n"
            f"Latency: {top_pair['estimated_latency_ms']:.0f} ms  \n"
            f"Resource load: {top_pair['resource_load']:.2f}  \n"
            f"Utility: {top_pair['utility']:.3f}"
        )
        st.markdown(
            f"""
            <div class="info-card purple-card">
              <div class="eyebrow" style="color:#6d28d9">TOP-1 CAPABILITY</div>
              <div class="node-title">{_escape(top_one.model.upper())}</div>
              <b>Predicted quality: {top_one.predicted_quality:.3f}</b><br><br>
              {_escape(top_detail).replace(chr(10), '<br>')}
            </div>
            """,
            unsafe_allow_html=True,
        )
    with middle:
        st.markdown("<div style='font-size:2.3rem;text-align:center;padding-top:70px'>→</div>", unsafe_allow_html=True)
    with right:
        st.markdown(
            f"""
            <div class="info-card orange-card">
              <div class="eyebrow" style="color:#b45309">FINAL EXECUTION CHOICE</div>
              <div class="node-title">{_escape(record.selected_model.upper())} @ {_escape(record.selected_node.upper())}</div>
              <b>Predicted quality: {record.selected_predicted_quality:.3f}</b><br><br>
              Latency: {selected_pair['estimated_latency_ms']:.0f} ms<br>
              Resource load: {selected_pair['resource_load']:.2f}<br>
              Utility: <b>{selected_pair['utility']:.3f}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )
    if record.selected_model != top_one.model and top_pair is not None:
        st.success(
            f"{top_one.model.upper()} has the highest predicted quality, but "
            f"{record.selected_model.upper()}@{record.selected_node.upper()} satisfies q_min "
            f"and has higher utility ({selected_pair['utility']:.3f} > {top_pair['utility']:.3f})."
        )
        st.markdown(
            f"**中文说明：** {top_one.model.upper()} 的预测质量最高，但其最佳可用部署当前综合代价更高；"
            f"{record.selected_model.upper()} 满足质量阈值，并在 {record.selected_node.upper()} 上具有更高效用。"
        )
    else:
        st.success(
            f"The Top-1 capability model remains the best execution choice in the current "
            f"resource state ({selected_pair['utility']:.3f} utility)."
        )
    st.markdown(
        "### The strongest model is not always the best execution choice."
    )


def _render_hierarchical() -> None:
    st.markdown('<span class="badge badge-purple">HIERARCHICAL ROUTER · OURS</span>', unsafe_allow_html=True)
    input_col, context_col = st.columns([1.2, 0.8])
    with input_col:
        st.markdown("### Query & Scenario")
        if "hierarchical_query" not in st.session_state:
            st.session_state.hierarchical_query = HIERARCHICAL_DEFAULT_QUERY
        query = st.text_area("Input Query", key="hierarchical_query", height=120)
        scenario = st.radio(
            "Scenario",
            SCENARIOS,
            index=1,
            horizontal=True,
            help="Scenarios modify resource-state inputs only. The real scheduler makes the final decision.",
        )
        run = st.button("Run Hierarchical Routing", type="primary", width="stretch")
    with context_col:
        st.markdown(
            """
            <div class="info-card purple-card">
              <div class="eyebrow" style="color:#6d28d9">DECISION OBJECT</div><div class="node-title">Model + Node</div>
              <div class="eyebrow" style="color:#0f766e">INPUTS</div>
              <div>Query + Dynamic Resource State</div><br>
              <span class="badge badge-purple">TOP-K</span>
              <span class="badge badge-green">QUALITY CONSTRAINT</span>
              <span class="badge badge-blue">RESOURCE AWARE</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    state_key = (query, scenario)
    if run or "hierarchical_result" not in st.session_state:
        try:
            st.session_state.hierarchical_result = run_hierarchical_routing(query, scenario)
            st.session_state.hierarchical_result_key = state_key
        except Exception as exc:  # pragma: no cover - rendered interactively
            st.error(f"Hierarchical routing failed: {exc}")
            return
    result: HierarchicalDemoResult = st.session_state.hierarchical_result
    if st.session_state.get("hierarchical_result_key") != state_key:
        st.info("Query or scenario changed. Click **Run Hierarchical Routing** to apply the new inputs.")

    _flow(["Query", "Capability Router", "Top-K", "q_min", "Resource Scheduler", "Model × Node", "Decision"])
    _render_capability_ranking(result)
    _render_resources(result.record)
    _render_utility(result)
    _render_final(result)

    with st.expander("Technical Details"):
        config = load_experiment_config()
        st.markdown("**Query features**")
        st.json(result.record.query_features)
        st.markdown("**Quality estimates (ground truth is evaluation-only)**")
        quality_rows = []
        predicted = {item.model: item.predicted_quality for item in result.all_candidates}
        for model in predicted:
            quality_rows.append(
                {
                    "model": model,
                    "actual_quality": result.actual_qualities[model],
                    "predicted_quality": predicted[model],
                    "prediction_error": round(predicted[model] - result.actual_qualities[model], 6),
                }
            )
        st.dataframe(pd.DataFrame(quality_rows), hide_index=True, width="stretch")
        st.json(
            {
                "top_k": config.top_k,
                "top_k_candidates": result.record.top_k_candidates,
                "q_min": result.record.quality_threshold,
                "quality_fallback": result.record.quality_fallback,
                "normalized_fields": ["normalized_latency", "normalized_cost", "resource_load"],
                "utility_weights": config.utility_weights.__dict__,
                "controller_call_path": "routellm/hierarchical_controller.py::HierarchicalController.decide",
                "decision_record": result.record.to_dict(),
            }
        )


def _render_comparison() -> None:
    st.divider()
    st.markdown("## Original vs Ours")
    table = pd.DataFrame(
        [
            ["Decision Object", "Model", "Model + Execution Node"],
            ["Inputs", "Query", "Query + Resource State"],
            ["Output", "Strong / Weak Model", "Model + Node"],
            ["Resource Awareness", "No", "Yes"],
            ["Quality Constraint", "No", "Yes (q_min + fallback)"],
            ["Candidate Set", "Two-model threshold", "Multi-model Top-K"],
        ],
        columns=["Dimension", "Official RouteLLM", "Hierarchical Router"],
    )
    st.dataframe(table, width="stretch", hide_index=True)
    st.markdown(
        "**Original RouteLLM answers “which model?”; our extension further answers "
        "“which model should execute on which node right now?”**"
    )


def main() -> None:
    if st is None:
        raise RuntimeError(
            "Streamlit is not installed. Run: python -m pip install -r requirements-visual-demo.txt"
        )
    st.set_page_config(
        page_title="RouteLLM Routing Demo",
        page_icon="⇄",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_css()
    _render_header()
    mode = st.radio(
        "Routing Mode",
        ("Official RouteLLM", "Hierarchical Router"),
        index=1,
        horizontal=True,
    )
    if mode == "Official RouteLLM":
        _render_official()
    else:
        _render_hierarchical()
    _render_comparison()


if __name__ == "__main__":
    main()

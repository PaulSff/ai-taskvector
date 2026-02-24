"""
DataBIEnvSpec: integration layer for unit-based data/BI workflows.
Tables are list-of-dicts; reward from downstream metric (e.g. deal rate on selected top-K).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from schemas.process_graph import ProcessGraph
from schemas.training_config import GoalConfig

from units.agent import register_agent_units
from units.oracle import register_oracle_units
from units.data_bi import register_data_bi_units


def _load_table_from_path(path: str | Path) -> list[dict]:
    """Load table as list of dicts from JSON (or CSV with optional pandas)."""
    path = Path(path)
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "offers" in data:
        return data["offers"]
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    return [data] if isinstance(data, dict) else []


class DataBIEnvSpec:
    """EnvSpec for data/BI unit-based workflows (filter, sort, top-K, etc.)."""

    def __init__(self, **kwargs: Any):
        self._kwargs = kwargs
        self._target_metric: str | None = None
        self._feedback_column: str | None = None

    def register_units(self) -> None:
        register_data_bi_units()
        register_agent_units()
        register_oracle_units()

    def build_initial_state(
        self,
        process_graph: ProcessGraph,
        goal: GoalConfig,
        options: dict[str, Any] | None,
        randomize: bool,
        np_random: np.random.Generator,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Set DataSource state with table from data_path or options."""
        self._target_metric = goal.target_metric or "deal_rate"
        self._feedback_column = goal.feedback_column or "deal"

        data_path = (options or {}).get("data_path") or self._kwargs.get("data_path")
        table = (options or {}).get("table") or self._kwargs.get("table")
        if table is not None and isinstance(table, list):
            pass
        elif data_path:
            table = _load_table_from_path(data_path)
        else:
            table = []

        initial_state: dict[str, Any] = {}
        for u in process_graph.units:
            if u.type == "DataSource":
                initial_state[u.id] = {"table": table}
        return initial_state

    def check_done(
        self,
        outputs: dict[str, Any],
        goal_override: dict[str, Any],
        step_count: int,
        max_steps: int,
        **kwargs: Any,
    ) -> tuple[bool, bool]:
        """Truncate at max_steps; optional: terminate when output submitted."""
        truncated = step_count >= max_steps
        terminated = False
        return terminated, truncated

    def extend_info(
        self,
        info: dict[str, Any],
        outputs: dict[str, Any],
        initial_state: dict[str, Any] | None,
        **kwargs: Any,
    ) -> None:
        """Add data_bi keys: row_count, target_metric, feedback_column."""
        info["target_metric"] = self._target_metric
        info["feedback_column"] = self._feedback_column
        # Aggregate row_count from any unit that has it
        for uid, out in outputs.items():
            if isinstance(out, dict) and "row_count" in out:
                info["row_count"] = out["row_count"]
                break

    def get_goal_override(self, env: Any, **kwargs: Any) -> dict[str, Any]:
        """Return goal dict for reward evaluation."""
        return {
            "target_metric": self._target_metric,
            "target_value": getattr(env.goal, "target_value", None),
            "feedback_column": self._feedback_column,
        }

    def get_compat_attr(self, env: Any, name: str) -> Any:
        """Compatibility attrs for data_bi."""
        if name == "target_metric":
            return self._target_metric
        if name == "feedback_column":
            return self._feedback_column
        raise AttributeError(name)

    def render(self, env: Any) -> None:
        """When render_mode='human': print table summary. Set env.render_plot=True to also show histograms of numeric columns."""
        outputs = getattr(env.executor, "_outputs", {})
        step = getattr(env, "step_count", 0)
        table = None
        row_count = 0
        for out in outputs.values():
            if isinstance(out, dict) and "table" in out:
                table = out["table"]
                row_count = out.get("row_count", len(table) if isinstance(table, list) else 0)
                break
        print(f"[data_bi] step={step} row_count={row_count} target_metric={self._target_metric}")
        if not table:
            return
        try:
            import pandas as pd
            df = pd.DataFrame(table) if isinstance(table, list) else table
            if df.empty:
                return
            num = df.select_dtypes(include="number")
            if not num.columns.empty:
                print("  numeric columns:", list(num.columns))
            # Optional: show matplotlib histograms (set env.render_plot = True to enable)
            if getattr(env, "render_plot", False) and not num.columns.empty:
                import matplotlib
                if matplotlib.get_backend().lower() != "agg":
                    import matplotlib.pyplot as plt
                    ncols = min(4, len(num.columns))
                    nrows = (len(num.columns) + ncols - 1) // ncols
                    fig, axes = plt.subplots(nrows, ncols, figsize=(3 * ncols, 2.5 * nrows))
                    if nrows == 1 and ncols == 1:
                        axes = [[axes]]
                    elif nrows == 1:
                        axes = [axes]
                    for idx, col in enumerate(num.columns):
                        ax = axes[idx // ncols][idx % ncols]
                        ax.hist(num[col].dropna(), bins=min(30, max(5, len(num) // 5)), edgecolor="black", alpha=0.7)
                        ax.set_title(col)
                    for idx in range(len(num.columns), nrows * ncols):
                        axes[idx // ncols][idx % ncols].set_visible(False)
                    plt.tight_layout()
                    plt.show(block=False)
                    plt.pause(0.5)
                    plt.close()
        except Exception:
            pass

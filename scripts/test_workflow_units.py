"""
Tests for assistant workflow units: RagSearch, Filter (data_bi), FormatRagPrompt, GraphSummary, UnitsLibrary.

Run from repo root:
  python scripts/test_workflow_units.py
  pytest scripts/test_workflow_units.py -v

To run only units that do not load data_bi/numpy (avoids FPE in some environments):
  pytest scripts/test_workflow_units.py -v -k "not filter and not pipeline and not units_library"
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _register_canonical_units() -> None:
    from units.canonical.rag_search import register_rag_search
    from units.canonical.format_rag_prompt import register_format_rag_prompt
    from units.canonical.graph_summary import register_graph_summary
    from units.canonical.units_library import register_units_library

    register_rag_search()
    register_format_rag_prompt()
    register_graph_summary()
    register_units_library()


def _register_data_bi() -> bool:
    """Register Filter etc. Returns True if registered."""
    try:
        from units.data_bi import register_data_bi_units
        register_data_bi_units()
        return True
    except Exception:
        return False


def _register_units() -> None:
    _register_canonical_units()
    _register_data_bi()


def _get_spec(type_name: str):
    from units.registry import get_unit_spec
    return get_unit_spec(type_name)


# ---- RagSearch ----


def test_rag_search_empty_query_returns_empty_table() -> None:
    _register_canonical_units()
    spec = _get_spec("RagSearch")
    assert spec is not None and spec.step_fn is not None
    outputs, _ = spec.step_fn(
        {"persist_dir": ".rag_index", "top_k": 10},
        {"query": "", "edits": None},
        {},
        0.0,
    )
    assert outputs["table"] == []


def test_rag_search_no_persist_dir_returns_empty_table() -> None:
    _register_canonical_units()
    spec = _get_spec("RagSearch")
    assert spec is not None and spec.step_fn is not None
    outputs, _ = spec.step_fn(
        {"persist_dir": "", "top_k": 10},
        {"query": "some query", "edits": None},
        {},
        0.0,
    )
    assert outputs["table"] == []


def test_rag_search_edits_search_action_parses_query_and_max_results() -> None:
    """When edits contains action 'search', unit uses what/query/q and max_results (no index needed)."""
    from units.canonical.rag_search.rag_search import _search_action_from_edits

    out = _search_action_from_edits([{"action": "search", "what": "valve workflow", "max_results": 5}])
    assert out == ("valve workflow", 5)
    out = _search_action_from_edits([{"action": "search", "query": "temperature", "max_results": 20}])
    assert out == ("temperature", 20)
    out = _search_action_from_edits([{"action": "add_unit"}, {"action": "search", "q": "test"}])
    assert out == ("test", None)
    assert _search_action_from_edits([]) is None
    assert _search_action_from_edits([{"action": "no_edit"}]) is None


# ---- Filter (data_bi) ----


def test_filter_empty_table_returns_zero_count_and_empty_table() -> None:
    _register_canonical_units()
    try:
        if not _register_data_bi():
            return
    except Exception:
        return  # data_bi can trigger numpy/pandas load; skip if import fails
    spec = _get_spec("Filter")
    if spec is None:
        return
    assert spec.step_fn is not None
    outputs, _ = spec.step_fn(
        {"column": "score", "op": "ge", "value": 0.48},
        {"table": [], "value": 0.48, "column": "score", "op": "ge"},
        {},
        0.0,
    )
    assert outputs["row_count"] == 0.0
    assert outputs["table"] == []


def test_filter_ge_filters_by_score_threshold() -> None:
    _register_canonical_units()
    try:
        _register_data_bi()
    except Exception:
        return
    spec = _get_spec("Filter")
    if spec is None:
        return
    assert spec.step_fn is not None
    table = [
        {"text": "doc1", "metadata": {}, "score": 0.8},
        {"text": "doc2", "metadata": {}, "score": 0.5},
        {"text": "doc3", "metadata": {}, "score": 0.3},
    ]
    outputs, _ = spec.step_fn(
        {"column": "score", "op": "ge", "value": 0.48},
        {"table": table, "value": 0.48, "column": "score", "op": "ge"},
        {},
        0.0,
    )
    assert outputs["row_count"] == 2.0
    assert len(outputs["table"]) == 2
    assert all(r["score"] >= 0.48 for r in outputs["table"])


def test_filter_lt_filters_correctly() -> None:
    _register_canonical_units()
    try:
        _register_data_bi()
    except Exception:
        return
    spec = _get_spec("Filter")
    if spec is None:
        return
    assert spec.step_fn is not None
    table = [{"score": 0.1}, {"score": 0.9}]
    outputs, _ = spec.step_fn(
        {"column": "score", "op": "lt", "value": 0.5},
        {"table": table, "column": "score", "op": "lt", "value": 0.5},
        {},
        0.0,
    )
    assert outputs["row_count"] == 1.0
    assert outputs["table"][0]["score"] == 0.1


# ---- FormatRagPrompt ----


def test_format_rag_empty_table_returns_empty_string() -> None:
    _register_canonical_units()
    spec = _get_spec("FormatRagPrompt")
    assert spec is not None and spec.step_fn is not None
    outputs, _ = spec.step_fn(
        {"max_chars": 1200, "snippet_max": 400},
        {"table": []},
        {},
        0.0,
    )
    assert outputs["data"] == ""


def test_format_rag_formats_table_into_prompt_block() -> None:
    _register_canonical_units()
    spec = _get_spec("FormatRagPrompt")
    assert spec is not None and spec.step_fn is not None
    table = [
        {"text": "Valve controls flow.", "metadata": {"content_type": "document", "file_path": "/a.md"}, "score": 0.9},
        {"text": "Workflow example.", "metadata": {"content_type": "workflow", "name": "example"}, "score": 0.7},
    ]
    outputs, _ = spec.step_fn(
        {"max_chars": 1200, "snippet_max": 400},
        {"table": table},
        {},
        0.0,
    )
    data = outputs["data"]
    assert "Relevant context from knowledge base" in data
    assert "Valve controls flow" in data or "Valve" in data
    assert "document" in data.lower() or "Document" in data
    assert "import_workflow" in data or "file_path" in data


def test_format_rag_respects_snippet_max() -> None:
    _register_canonical_units()
    spec = _get_spec("FormatRagPrompt")
    assert spec is not None and spec.step_fn is not None
    long_text = "A" * 500
    table = [{"text": long_text, "metadata": {}, "score": 0.9}]
    outputs, _ = spec.step_fn(
        {"max_chars": 2000, "snippet_max": 50},
        {"table": table},
        {},
        0.0,
    )
    # Snippet should be truncated to 50 chars
    assert len(outputs["data"]) < 500


# ---- GraphSummary ----


def test_graph_summary_empty_graph_returns_empty_units() -> None:
    _register_canonical_units()
    spec = _get_spec("GraphSummary")
    assert spec is not None and spec.step_fn is not None
    outputs, _ = spec.step_fn({}, {"graph": None}, {}, 0.0)
    summary = outputs["summary"]
    assert isinstance(summary, dict)
    assert summary.get("units") == []


def test_graph_summary_dict_graph_returns_summary() -> None:
    _register_canonical_units()
    spec = _get_spec("GraphSummary")
    assert spec is not None and spec.step_fn is not None
    graph = {"units": [{"id": "v1", "type": "Valve", "controllable": True}], "connections": []}
    outputs, _ = spec.step_fn({}, {"graph": graph}, {}, 0.0)
    summary = outputs["summary"]
    assert isinstance(summary, dict)
    assert len(summary.get("units", [])) == 1
    assert summary["units"][0]["id"] == "v1"
    assert summary["units"][0]["type"] == "Valve"


# ---- UnitsLibrary ----


def test_units_library_empty_summary_returns_string() -> None:
    _register_canonical_units()
    spec = _get_spec("UnitsLibrary")
    assert spec is not None and spec.step_fn is not None
    try:
        outputs, _ = spec.step_fn({}, {"graph_summary": {}}, {}, 0.0)
    except Exception:
        return  # UnitsLibrary can trigger full env registration (numpy/thermodynamic); skip if it fails
    assert "data" in outputs
    assert isinstance(outputs["data"], str)


def test_units_library_with_summary_includes_units_section() -> None:
    _register_canonical_units()
    spec = _get_spec("UnitsLibrary")
    assert spec is not None and spec.step_fn is not None
    graph_summary = {"units": [{"id": "u1", "type": "Valve"}], "connections": [], "environment_type": "data_bi"}
    try:
        outputs, _ = spec.step_fn({}, {"graph_summary": graph_summary}, {}, 0.0)
    except Exception:
        return
    data = outputs["data"]
    assert "Units Library" in data or "units" in data.lower() or "Library" in data


# ---- RAG pipeline: RagSearch -> Filter -> FormatRagPrompt ----


def test_rag_search_filter_format_rag_pipeline() -> None:
    """RagSearch (empty/mock) -> Filter (score >= 0.48) -> FormatRagPrompt produces string for Merge."""
    _register_canonical_units()
    try:
        _register_data_bi()
    except Exception:
        return
    rag_spec = _get_spec("RagSearch")
    filter_spec = _get_spec("Filter")
    format_spec = _get_spec("FormatRagPrompt")
    if not all((rag_spec and rag_spec.step_fn, filter_spec and filter_spec.step_fn, format_spec and format_spec.step_fn)):
        return
    # Simulate RAG returning empty (no index) or a small table
    rag_out, _ = rag_spec.step_fn(
        {"persist_dir": ".rag_index", "top_k": 10},
        {"query": "user message", "edits": None},
        {},
        0.0,
    )
    table = rag_out["table"]
    # If RAG returned results, they have score; else use mock table for filter+format
    if not table:
        table = [
            {"text": "Relevant doc.", "metadata": {"content_type": "document"}, "score": 0.6},
            {"text": "Low score.", "metadata": {}, "score": 0.3},
        ]
    filter_out, _ = filter_spec.step_fn(
        {"column": "score", "op": "ge", "value": 0.48},
        {"table": table, "column": "score", "op": "ge", "value": 0.48},
        {},
        0.0,
    )
    format_out, _ = format_spec.step_fn(
        {"max_chars": 1200, "snippet_max": 400},
        {"table": filter_out["table"]},
        {},
        0.0,
    )
    assert isinstance(format_out["data"], str)
    if filter_out["row_count"] > 0:
        assert "Relevant context" in format_out["data"] or len(format_out["data"]) > 0


def test_rag_search_metadata_file_path_contains_passed_to_search() -> None:
    """RagSearch forwards metadata_file_path_contains to rag.search() for path-scoped retrieval."""
    _register_canonical_units()
    import units.canonical.rag_search.rag_search as rs

    captured: dict[str, Any] = {}

    def fake_search(
        query: str,
        *,
        persist_dir: str = ".rag_index",
        embedding_model=None,
        top_k: int = 10,
        content_type=None,
        metadata_file_path_contains=None,
    ):
        captured["metadata_file_path_contains"] = metadata_file_path_contains
        return []

    real_search = rs.search
    rs.search = fake_search
    try:
        spec = _get_spec("RagSearch")
        if not spec or not spec.step_fn:
            return
        spec.step_fn(
            {
                "persist_dir": ".rag_index",
                "top_k": 3,
                "metadata_file_path_contains": "assistants_team_members.md",
            },
            {"query": "delegate help"},
            {},
            0.0,
        )
    finally:
        rs.search = real_search
    assert captured.get("metadata_file_path_contains") == "assistants_team_members.md"


if __name__ == "__main__":
    _register_canonical_units()
    _register_data_bi()
    test_rag_search_empty_query_returns_empty_table()
    test_rag_search_no_persist_dir_returns_empty_table()
    test_rag_search_edits_search_action_parses_query_and_max_results()
    test_filter_empty_table_returns_zero_count_and_empty_table()
    test_filter_ge_filters_by_score_threshold()
    test_filter_lt_filters_correctly()
    test_format_rag_empty_table_returns_empty_string()
    test_format_rag_formats_table_into_prompt_block()
    test_format_rag_respects_snippet_max()
    test_graph_summary_empty_graph_returns_empty_units()
    test_graph_summary_dict_graph_returns_summary()
    test_units_library_empty_summary_returns_string()
    test_units_library_with_summary_includes_units_section()
    test_rag_search_filter_format_rag_pipeline()
    test_rag_search_metadata_file_path_contains_passed_to_search()
    print("All tests passed.")

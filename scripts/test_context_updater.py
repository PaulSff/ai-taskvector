"""
Test RAG context updater flow without running real indexing (no embeddings).
Emulates: need_indexing() + run_update() with a fake RAGIndex so mydata state is persisted.
Run from repo root: python scripts/test_context_updater.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from rag.context_updater import (
    RAG_INDEX_STATE_FILENAME,
    _compute_agents_rag_manifest,
    _compute_repo_canonical_manifest,
    load_state,
    need_indexing,
    run_update,
    save_state,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _make_fake_index():
    """Fake RAGIndex: no embedding, no Chroma; just counts and no-ops."""
    index = MagicMock()
    index.add_documents_and_index = MagicMock(return_value=0)
    index.delete_by_file_paths = MagicMock(return_value=None)
    return index


def test_need_indexing_mydata_true_when_state_mydata_null():
    """When state has mydata_hash null and mydata has files, need_mydata should be True."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rag_dir = root / "rag_data"
        mydata_dir = root / "mydata"
        units_dir = root / "units"
        rag_dir.mkdir()
        mydata_dir.mkdir()
        units_dir.mkdir()

        # State: units done, mydata never written (bug scenario)
        state_path = rag_dir / RAG_INDEX_STATE_FILENAME
        state_path.write_text(
            json.dumps(
                {
                    "units_hash": "abc",
                    "mydata_hash": None,
                    "units_files": {},
                    "mydata_files": None,
                }
            ),
            encoding="utf-8",
        )

        # One RAG-relevant file in mydata so hash is not empty
        (mydata_dir / "doc.md").write_text("hello", encoding="utf-8")

        need_u, need_m, _, _, reason = need_indexing(rag_dir, units_dir, mydata_dir)
        assert need_m is True, (
            f"expected need_mydata True when mydata_hash is null; got {reason}"
        )
        assert mydata_dir.resolve().is_dir()


def test_run_update_persists_mydata_state_with_fake_index():
    """run_update() with a fake index should persist mydata_hash and mydata_files when need_mydata is True."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rag_dir = root / "rag_data"
        mydata_dir = root / "mydata"
        units_dir = root / "units"
        rag_dir.mkdir()
        mydata_dir.mkdir()
        units_dir.mkdir()

        # Bug scenario: state has only units, mydata_hash/mydata_files null
        state_path = rag_dir / RAG_INDEX_STATE_FILENAME
        state_path.write_text(
            json.dumps(
                {
                    "units_hash": "abc",
                    "mydata_hash": None,
                    "units_files": {},
                    "mydata_files": None,
                }
            ),
            encoding="utf-8",
        )

        # Mydata content: one .md file so mydata has a real hash
        (mydata_dir / "note.md").write_text("test content", encoding="utf-8")

        # Fake RAGIndex so we don't load embeddings or Chroma
        fake_index = _make_fake_index()
        fake_index.add_documents_and_index.return_value = 1

        # run_update does "from rag.indexer import RAGIndex" inside the function; patch the source
        with patch("rag.indexer.RAGIndex", MagicMock(return_value=fake_index)):
            result = run_update(rag_dir, units_dir, mydata_dir)

        assert result.get("ok") is True, result.get("error") or result.get("message")
        assert result.get("need_index") is True

        # State must now have mydata_hash and mydata_files (no longer null)
        state = load_state(rag_dir)
        assert state.get("mydata_hash") is not None, (
            "mydata_hash should be set after run_update"
        )
        assert state.get("mydata_files") is not None, (
            "mydata_files should be set after run_update"
        )
        assert isinstance(state["mydata_files"], dict)
        assert "note.md" in state["mydata_files"], (
            "mydata manifest should list the file"
        )


def test_run_update_single_source_of_truth_mydata():
    """When need_indexing says need_mydata True, run_update runs mydata block and persists state (no re-check)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rag_dir = root / "rag_data"
        mydata_dir = root / "mydata"
        units_dir = root / "units"
        rag_dir.mkdir()
        mydata_dir.mkdir()
        units_dir.mkdir()

        state_path = rag_dir / RAG_INDEX_STATE_FILENAME
        state_path.write_text(
            json.dumps(
                {
                    "units_hash": "x",
                    "mydata_hash": None,
                    "units_files": {},
                    "mydata_files": None,
                }
            ),
            encoding="utf-8",
        )
        (mydata_dir / "w.json").write_text("{}", encoding="utf-8")

        need_u, need_m, _, _, _ = need_indexing(rag_dir, units_dir, mydata_dir)
        assert need_m is True

        fake_index = _make_fake_index()
        with patch("rag.indexer.RAGIndex", MagicMock(return_value=fake_index)):
            run_update(rag_dir, units_dir, mydata_dir)

        state = load_state(rag_dir)
        assert state["mydata_hash"] is not None
        assert state["mydata_files"] is not None


def test_compute_repo_canonical_manifest_skips_mydata():
    """Canonical JSON under mydata is excluded from repo manifest (indexed via mydata path)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        mydata = root / "mydata"
        rag_data = root / "rag_data"
        repo.mkdir()
        mydata.mkdir()
        rag_data.mkdir()
        canonical = (
            '{"units":[{"id":"a","type":"Inject","controllable":false,"params":{},"input_ports":[],'
            '"output_ports":[]}],"connections":[]}'
        )
        (mydata / "in_mydata.json").write_text(canonical, encoding="utf-8")
        (repo / "outside.json").write_text(canonical, encoding="utf-8")
        m = _compute_repo_canonical_manifest(repo, mydata, rag_data)
        assert "outside.json" in m
        assert "in_mydata.json" not in m


def test_run_update_persists_repo_canonical_state():
    """When only repo canonical graphs need indexing, run_update persists repo_canonical_* in state."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rag_dir = root / "rag_data"
        mydata_dir = root / "mydata"
        units_dir = root / "units"
        repo = root / "repo"
        for d in (rag_dir, mydata_dir, units_dir, repo):
            d.mkdir()
        (repo / "gui").mkdir()
        canonical = (
            '{"units":[{"id":"a","type":"Inject","controllable":false,"params":{},"input_ports":[],'
            '"output_ports":[]}],"connections":[]}'
        )
        (repo / "gui" / "wf.json").write_text(canonical, encoding="utf-8")
        eh = hashlib.md5(b"").hexdigest()
        (rag_dir / RAG_INDEX_STATE_FILENAME).write_text(
            json.dumps(
                {
                    "units_hash": eh,
                    "mydata_hash": eh,
                    "units_files": {},
                    "mydata_files": {},
                    "roles_rag_hash": "stable_roles_h",
                }
            ),
            encoding="utf-8",
        )
        fake_index = _make_fake_index()
        fake_index.add_documents_and_index.return_value = 1
        with (
            patch("rag.indexer.RAGIndex", MagicMock(return_value=fake_index)),
            patch(
                "agents.roles.team_members_rag.agents_roles_content_hash",
                return_value="stable_roles_h",
            ),
        ):
            result = run_update(rag_dir, units_dir, mydata_dir, repo_root=repo)
        assert result.get("ok") is True
        state = load_state(rag_dir)
        assert state.get("repo_canonical_hash") is not None
        assert isinstance(state.get("repo_canonical_files"), dict)
        assert "gui/wf.json" in state["repo_canonical_files"]
        assert state.get("agents_rag_hash") is not None
        assert isinstance(state.get("agents_rag_files"), dict)
        fake_index.add_documents_and_index.assert_called_once()
        kwargs = fake_index.add_documents_and_index.call_args.kwargs
        assert kwargs.get("repo_root_for_agents_utf8") == repo.resolve()
        assert kwargs.get("rag_units_dir") == units_dir.resolve()
        assert kwargs.get("rag_mydata_dir") == mydata_dir.resolve()


def test_compute_agents_rag_manifest_lists_md_and_py():
    """Manifest under agents/ includes .md and .py relative to repo root."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rag_data = root / "rag_data"
        repo = root / "repo"
        rag_data.mkdir()
        (repo / "agents").mkdir(parents=True)
        (repo / "agents" / "README.md").write_text("# hi", encoding="utf-8")
        (repo / "agents" / "pkg").mkdir()
        (repo / "agents" / "pkg" / "x.py").write_text("x = 1\n", encoding="utf-8")
        m = _compute_agents_rag_manifest(repo, rag_data)
        assert "agents/README.md" in m
        assert "agents/pkg/x.py" in m


if __name__ == "__main__":
    test_need_indexing_mydata_true_when_state_mydata_null()
    print("  need_indexing: mydata need=True when state mydata null")

    test_run_update_persists_mydata_state_with_fake_index()
    print("  run_update: mydata state persisted with fake index")

    test_run_update_single_source_of_truth_mydata()
    print("  run_update: single source of truth (mydata)")

    test_compute_repo_canonical_manifest_skips_mydata()
    print("  repo canonical manifest: skips mydata")

    test_run_update_persists_repo_canonical_state()
    print("  run_update: repo_canonical state persisted")

    test_compute_agents_rag_manifest_lists_md_and_py()
    print("  agents RAG manifest: md and py")

    print("All tests passed.")

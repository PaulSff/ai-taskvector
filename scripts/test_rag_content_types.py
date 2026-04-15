#!/usr/bin/env python3
"""Quick checks for ``rag.content_types`` (no RAG deps). Run from repo root: python scripts/test_rag_content_types.py"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from rag.content_types import (
    content_type_for_assistants_repo_relative,
    content_type_for_markdown_file,
    content_type_for_repo_relative_path,
)


def test_assistants_types():
    assert content_type_for_assistants_repo_relative("assistants/roles/x/prompts.py", ".py") == "role_source"
    assert content_type_for_assistants_repo_relative("assistants/tools/y/handler.py", ".py") == "tool_source"
    assert content_type_for_assistants_repo_relative("assistants/prompts.py", ".py") == "taskvector_assistants_source"
    assert content_type_for_assistants_repo_relative("assistants/roles/x/README.md", ".md") == "role_readme"
    assert content_type_for_assistants_repo_relative("assistants/tools/y/README.md", ".md") == "tool_readme"
    assert content_type_for_assistants_repo_relative("assistants/README.md", ".md") == "taskvector_assistants_readme"
    assert content_type_for_assistants_repo_relative("assistants/roles/x/other.md", ".md") == "role_readme"


def test_units_markdown_paths():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        units = root / "units"
        mydata = root / "mydata"
        units.mkdir()
        mydata.mkdir()
        u_readme = units / "canonical" / "rag_search" / "README.md"
        u_readme.parent.mkdir(parents=True)
        u_readme.write_text("# u", encoding="utf-8")
        u_other = units / "foo.md"
        u_other.write_text("x", encoding="utf-8")
        m_doc = mydata / "a.md"
        m_doc.write_text("y", encoding="utf-8")
        assert content_type_for_markdown_file(u_readme, rag_units_dir=units, rag_mydata_dir=mydata) == "unit_readme"
        assert (
            content_type_for_markdown_file(u_other, rag_units_dir=units, rag_mydata_dir=mydata)
            == "taskvector_units_readme"
        )
        assert content_type_for_markdown_file(m_doc, rag_units_dir=units, rag_mydata_dir=mydata) == "document"


def test_repo_relative_generic():
    assert content_type_for_repo_relative_path("config/README.md", ".md") == "taskvector_config_readme"
    assert content_type_for_repo_relative_path("gui/foo.py", ".py") == "taskvector_gui_source"
    assert content_type_for_repo_relative_path("units/bar/README.md", ".md") == "unit_readme"
    assert content_type_for_repo_relative_path("units/bar/guide.md", ".md") == "taskvector_units_readme"
    assert content_type_for_repo_relative_path("units/foo/x.py", ".py") == "taskvector_units_source"
    assert content_type_for_repo_relative_path("rag/design.pdf", ".pdf") == "document"


if __name__ == "__main__":
    test_assistants_types()
    print("  assistants content types OK")
    test_units_markdown_paths()
    print("  units markdown paths OK")
    test_repo_relative_generic()
    print("  repo-relative generic OK")
    print("All rag.content_types checks passed.")

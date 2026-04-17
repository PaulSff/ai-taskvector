"""
RAG content types: **indexing** labels (repo-relative paths) and **registry** packages (mydata + upload pipeline).

Packages live under ``rag/content_types/<id>/`` with ``content_type.yaml``. Use :func:`refresh_rag_content_type_registry`
after adding or editing packages in tests.
"""
from __future__ import annotations

from rag.content_types.indexing import (
    content_type_for_assistants_repo_relative,
    content_type_for_indexed_file,
    content_type_for_markdown_file,
    content_type_for_repo_relative_path,
    is_readme_md,
    repo_relative_posix,
    sanitize_taskvector_token,
)
from rag.content_types.registry import (
    MYDATA_ORGANIZED_SUBDIR,
    ContentTypePackage,
    classify_json_for_rag,
    get_package,
    list_packages,
    mydata_destination,
    mydata_subdir_for_json_kind,
    mydata_subdir_for_suffix,
    package_for_json_kind,
    package_for_suffix,
    refresh_registry as refresh_rag_content_type_registry,
    storage_category_for_suffix,
    upload_router_payload,
)

__all__ = [
    "MYDATA_ORGANIZED_SUBDIR",
    "ContentTypePackage",
    "classify_json_for_rag",
    "content_type_for_assistants_repo_relative",
    "content_type_for_indexed_file",
    "content_type_for_markdown_file",
    "content_type_for_repo_relative_path",
    "get_package",
    "is_readme_md",
    "list_packages",
    "mydata_destination",
    "mydata_subdir_for_json_kind",
    "mydata_subdir_for_suffix",
    "package_for_json_kind",
    "package_for_suffix",
    "repo_relative_posix",
    "sanitize_taskvector_token",
    "storage_category_for_suffix",
    "upload_router_payload",
    "refresh_rag_content_type_registry",
]

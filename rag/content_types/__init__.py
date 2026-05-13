"""
RAG content types: **indexing** labels (repo-relative paths) and **registry** packages (mydata + upload pipeline).

Packages live under ``rag/content_types/<id>/`` with ``content_type.yaml``. Use :func:`refresh_rag_content_type_registry`
after adding or editing packages in tests.
"""

from __future__ import annotations

from rag.content_types.registry import (
    MYDATA_ORGANIZED_SUBDIR,
    ContentTypePackage,
    classify_content,
    get_package,
    list_packages,
    mydata_destination,
    mydata_subdir_for_content_kind,
    mydata_subdir_for_suffix,
    package_for_content_kind,
    package_for_suffix,
    storage_category_for_suffix,
    upload_router_payload,
)
from rag.content_types.registry import (
    refresh_registry as refresh_rag_content_type_registry,
)

__all__ = [
    "MYDATA_ORGANIZED_SUBDIR",
    "ContentTypePackage",
    "classify_content",
    "get_package",
    "list_packages",
    "mydata_destination",
    "mydata_subdir_for_content_kind",
    "mydata_subdir_for_suffix",
    "package_for_content_kind",
    "package_for_suffix",
    "storage_category_for_suffix",
    "upload_router_payload",
    "refresh_rag_content_type_registry",
]

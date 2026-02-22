#!/usr/bin/env python3
"""
CLI for RAG indexing and search.

Examples:
  python -m rag build --workflows config/examples --nodes-url https://raw.githubusercontent.com/node-red/catalogue.nodered.org/master/catalogue.json
  python -m rag build --workflows /path/to/n8n-workflows/workflows
  python -m rag search "temperature control workflow"
  python -m rag search "MQTT sensor" --content-type node
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _get_rag_defaults() -> tuple[str, str]:
    """Get persist_dir and embedding_model from app settings when available."""
    try:
        from gui.flet.components.settings import get_rag_embedding_model, get_rag_index_dir
        return str(get_rag_index_dir()), get_rag_embedding_model()
    except ImportError:
        return ".rag_index", "sentence-transformers/all-MiniLM-L6-v2"


def main() -> None:
    _default_persist, _default_embedding = _get_rag_defaults()

    parser = argparse.ArgumentParser(description="RAG index for workflows, nodes, and documents")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # build
    build_p = sub.add_parser("build", help="Build the RAG index")
    build_p.add_argument("--workflows", type=str, help="Directory with Node-RED / n8n workflow JSON files")
    build_p.add_argument("--nodes-url", type=str, help="URL of Node-RED catalogue.json")
    build_p.add_argument("--nodes-file", type=str, help="Local path to Node-RED catalogue.json")
    build_p.add_argument("--docs", type=str, help="Directory with user documents (PDF, DOC, XLS)")
    build_p.add_argument("--persist-dir", type=str, default=_default_persist, help="Index persistence directory")
    build_p.add_argument("--embedding-model", type=str, default=_default_embedding, help="Embedding model")

    # search
    search_p = sub.add_parser("search", help="Search the RAG index")
    search_p.add_argument("query", type=str, help="Search query")
    search_p.add_argument("--top-k", type=int, default=10, help="Max results")
    search_p.add_argument("--content-type", type=str, choices=["workflow", "node", "document"], help="Filter by type")
    search_p.add_argument("--persist-dir", type=str, default=_default_persist, help="Index directory")
    search_p.add_argument("--embedding-model", type=str, default=_default_embedding, help="Embedding model (must match index)")
    search_p.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.cmd == "build":
        from rag.indexer import RAGIndex

        index = RAGIndex(persist_dir=args.persist_dir, embedding_model=args.embedding_model)
        index.build(
            workflows_dir=args.workflows or None,
            nodes_catalogue_url=args.nodes_url or None,
            nodes_catalogue_file=args.nodes_file or None,
            docs_dir=args.docs or None,
        )
        print(f"Index built at {args.persist_dir}")

    elif args.cmd == "search":
        from rag.search import search

        results = search(
            args.query,
            persist_dir=args.persist_dir,
            embedding_model=args.embedding_model,
            top_k=args.top_k,
            content_type=args.content_type,
        )
        if args.json:
            print(json.dumps(results, indent=2, default=str))
        else:
            for i, r in enumerate(results, 1):
                meta = r.get("metadata", {})
                name = meta.get("name", meta.get("id", "—"))
                ct = meta.get("content_type", "—")
                print(f"{i}. [{ct}] {name}")
                print(f"   {r.get('text', '')[:200]}...")
                if meta.get("file_path"):
                    print(f"   path: {meta['file_path']}")
                elif meta.get("url"):
                    print(f"   url: {meta['url']}")
                print()


if __name__ == "__main__":
    main()

"""RAG units: search, index, embed, Chroma, document load, format prompt, classify/extract pipelines."""

from units.rag.canonical_workflow_extractor import register_canonical_workflow_extract
from units.rag.chat_history_extractor import register_chat_history_extract
from units.rag.chroma_indexer import register_chroma_indexer
from units.rag.delete_from_index import register_delete_from_index
from units.rag.embedder import register_embedder
from units.rag.fetch_source import register_fetch_source
from units.rag.format_rag_prompt import register_format_rag_prompt
from units.rag.json_flatten_extract import register_json_flatten_extract
from units.rag.load_document import register_load_document
from units.rag.mydata_organize import register_mydata_organize
from units.rag.mydata_storage_report import register_mydata_storage_report
from units.rag.n8n_workflow_extractor import register_n8n_workflow_extract
from units.rag.node_red_workflow_extractor import register_node_red_workflow_extract
from units.rag.plain_text_extract import register_plain_text_extract
from units.rag.rag_build_index_document import register_rag_build_index_document
from units.rag.rag_chunk_builder import register_rag_chunk_builder
from units.rag.rag_content_classify import register_rag_content_classify
from units.rag.rag_detect_origin import register_rag_detect_origin
from units.rag.rag_extract import register_rag_extract
from units.rag.rag_flatten_chunks import register_rag_flatten_chunks
from units.rag.rag_pick_delegatee import register_rag_pick_delegatee
from units.rag.rag_search import register_rag_search
from units.rag.rag_update import register_rag_update

_RAG_TYPE_NAMES = (
    "RagPickDelegatee",
    "RagSearch",
    "RagDetectOrigin",
    "FormatRagPrompt",
    "LoadDocument",
    "RagUpdate",
    "Embedder",
    "ChromaIndexer",
    "DeleteFromIndex",
    "RagContentClassify",
    "RagExtract",
    "RagBuildIndexDocument",
    "RagFlattenChunks",
    "CanonicalWorkflowExtract",
    "ChatHistoryExtract",
    "N8nWorkflowExtract",
    "NodeRedWorkflowExtract",
    "RagChunkBuilder",
    "FetchSource",
    "JsonFlattenExtract",
    "PlainTextExtract",
    "MydataOrganize",
    "MydataStorageReport",
)


def register_rag_units() -> None:
    """Register all RAG-domain units and tag them for the ``rag`` environment."""
    from units.registry import UNIT_REGISTRY

    register_rag_pick_delegatee()
    register_rag_search()
    register_rag_detect_origin()
    register_format_rag_prompt()
    register_load_document()
    register_rag_update()
    register_embedder()
    register_chroma_indexer()
    register_delete_from_index()
    register_rag_content_classify()
    register_rag_extract()
    register_rag_build_index_document()
    register_rag_flatten_chunks()
    register_canonical_workflow_extract()
    register_chat_history_extract()
    register_n8n_workflow_extract()
    register_node_red_workflow_extract()
    register_rag_chunk_builder()
    register_fetch_source()
    register_json_flatten_extract()
    register_plain_text_extract()
    register_mydata_organize()
    register_mydata_storage_report()
    for name in _RAG_TYPE_NAMES:
        spec = UNIT_REGISTRY.get(name)
        if spec is not None:
            spec.environment_tags = ["rag"]
            spec.environment_tags_are_agnostic = True
            spec.runtime_scope = "canonical"


import logging

logger = logging.getLogger(__name__)

def _register_rag_env_loader() -> None:
    try:
        from units.env_loaders import register_env_loader
    except ImportError:
        logger.info("env_loaders not available; cannot register rag env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_env_loader")
        raise

    try:
        from units.rag import register_rag_units
    except ImportError:
        logger.info("units.rag not available; cannot register rag env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_rag_units")
        raise

    try:
        register_env_loader("rag", register_rag_units)
    except Exception:
        logger.exception("Failed to register rag env loader")
        raise



_register_rag_env_loader()


__all__ = ["register_rag_units"]

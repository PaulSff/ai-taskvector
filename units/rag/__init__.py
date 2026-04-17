"""RAG units: search, index, embed, Chroma, document load, format prompt, classify/extract pipelines."""

from units.rag.chroma_indexer import register_chroma_indexer
from units.rag.embedder import register_embedder
from units.rag.format_rag_prompt import register_format_rag_prompt
from units.rag.load_document import register_load_document
from units.rag.rag_build_index_document import register_rag_build_index_document
from units.rag.rag_content_classify import register_rag_content_classify
from units.rag.rag_detect_origin import register_rag_detect_origin
from units.rag.rag_extract import register_rag_extract
from units.rag.rag_flatten_chunks import register_rag_flatten_chunks
from units.rag.rag_json_index_extract import register_rag_json_index_extract
from units.rag.rag_pick_delegatee import register_rag_pick_delegatee
from units.rag.rag_search import register_rag_search
from units.rag.rag_update import register_rag_update
from units.rag.rag_canonical_workflow_extractor import register_rag_canonical_workflow_extract
from units.rag.chat_history_extractor import register_chat_history_extract
from units.rag.n8n_workflow_extractor import register_rag_n8n_workflow_extract
from units.rag.node_red_catalogue_extractor import register_node_red_catalogue_extract
from units.rag.node_red_workflow_extractor import register_node_red_workflow_extract
from units.rag.chunk_builder import register_chunk_builder

_RAG_TYPE_NAMES = (
    "RagPickDelegatee",
    "RagSearch",
    "RagDetectOrigin",
    "FormatRagPrompt",
    "LoadDocument",
    "RagUpdate",
    "Embedder",
    "ChromaIndexer",
    "RagContentClassify",
    "RagExtract",
    "RagBuildIndexDocument",
    "RagJsonIndexExtract",
    "RagFlattenChunks",
    "CanonicalWorkflowExtract",
    "ChatHistoryExtract",
    "N8nWorkflowExtract",
    "NodeRedCatalogueExtract",
    "NodeRedWorkflowExtract",
    "ChunkBuilder"
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
    register_rag_content_classify()
    register_rag_extract()
    register_rag_build_index_document()
    register_rag_json_index_extract()
    register_rag_flatten_chunks()
    register_rag_canonical_workflow_extract()
    register_chat_history_extract()
    register_rag_n8n_workflow_extract()
    register_node_red_catalogue_extract()
    register_node_red_workflow_extract()
    register_chunk_builder()
    for name in _RAG_TYPE_NAMES:
        spec = UNIT_REGISTRY.get(name)
        if spec is not None:
            spec.environment_tags = ["rag"]
            spec.environment_tags_are_agnostic = True
            spec.runtime_scope = "canonical"


from units.env_loaders import register_env_loader

register_env_loader("rag", register_rag_units)

__all__ = ["register_rag_units"]

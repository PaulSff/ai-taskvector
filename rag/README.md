# RAG Module

Semantic search over workflows, nodes, and user documents. Uses LlamaIndex, ChromaDB, and sentence-transformers. Runs on **CPU** (no GPU required).

## Install

```bash
pip install -r requirements-rag.txt
```

## Embedding model (offline use)

RAG uses the **sentence-transformers** embedding model **`sentence-transformers/all-MiniLM-L6-v2`** from the [Hugging Face Hub](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2). The library downloads it from Hugging Face on first use, so **internet is required the first time** you build the index or run search. If you see `MaxRetryError` / `Failed to resolve 'huggingface.co'`, the model has not been cached yet.

**To use RAG offline:**

1. **One-time download (with internet)**  
   Run the app or `python -m rag update` (or any RAG search) once while online. The model is cached under `~/.cache/huggingface/hub/` (or `$HF_HOME` / `$TRANSFORMERS_CACHE` if set).

2. **Use cache only**  
   In the Flet app: **Settings → RAG → check "Use RAG offline"**. The app will set `HF_HUB_OFFLINE=1` when loading the embedding model, so only the cache is used. Alternatively, run with:
   ```bash
   export HF_HUB_OFFLINE=1
   ```

3. **Pre-download from Python**  
   To populate the cache without running the full app:
   ```bash
   python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
   ```

The model name, index directory, and offline flag live in **`rag/ragconf.yaml`** (`rag_embedding_model`, `rag_index_data_dir`, `rag_offline`); the default model is `sentence-transformers/all-MiniLM-L6-v2`.

**`rag/workflows/`** holds **`rag_update.json`** (Flet runs it for index updates; path from `rag_update_workflow_path` in **`rag/ragconf.yaml`**) and **`doc_to_text.json`** (used by `rag/indexer.py` to turn office/PDF files into text; `doc_to_text_workflow_path` in **`rag/ragconf.yaml`**).

## Quick Start

### Build index

```bash
# From project root - index local workflows + Node-RED catalogue
python -m rag build \
  --workflows config/examples \
  --nodes-url https://raw.githubusercontent.com/node-red/catalogue.nodered.org/master/catalogue.json \
  --persist-dir .rag_index

# With user documents (PDF, DOC, XLS)
python -m rag build \
  --workflows config/examples \
  --nodes-url https://raw.githubusercontent.com/node-red/catalogue.nodered.org/master/catalogue.json \
  --docs /path/to/your/docs
```

### Update (incremental: units + mydata)

From project root, uses `config/app_settings.json` for `mydata_dir` and **`rag/ragconf.yaml`** for `rag_index_data_dir`, `rag_embedding_model`, `rag_update_workflow_path`, and `doc_to_text_workflow_path` (RAG keys are exposed as ``settings.*`` in workflows via ``units/canonical/app_settings_param.py``):

```bash
python -m rag update
python -m rag update --config config/app_settings.json --json
```

Updates the RAG index from **units/** and **mydata/** when content has changed (MD5 manifests). Index storage (ChromaDB + state) lives in **rag/.rag_index_data/**; content to index lives in **mydata/** (or whatever `mydata_dir` points to). Use the [mydata layout](#mydata-layout-path-based-json-classification) below so JSON is classified correctly. Prints status and short stats (what was updated).

### Search

```bash
python -m rag search "temperature control workflow"
python -m rag search "MQTT sensor" --content-type node
python -m rag search "pump valve" --top-k 5 --json
```

## Python API

```python
from rag import RAGIndex, search

# Build
index = RAGIndex(persist_dir=".rag_index")
index.build(
    workflows_dir="config/examples",
    nodes_catalogue_url="https://raw.githubusercontent.com/node-red/catalogue.nodered.org/master/catalogue.json",
    docs_dir="docs/",
)

# Search
results = search("temperature monitoring", top_k=5)
for r in results:
    print(r["metadata"].get("name"), r["metadata"].get("file_path"))
```

## Indexed Content

| Type | Source | Metadata |
|------|--------|----------|
| **Workflows** | Node-RED / n8n JSON | name, unit_types/integrations, node labels, file_path |
| **Library flows** | node-red-library-flows-refined.json (list of entries) | name, summary, readme snippet per entry |
| **Nodes** | Node-RED catalogue (catalogue.json) | id, description, keywords, node_types |
| **Documents** | PDF, DOC, XLS, PPT, HTML, MD | file path, extracted text (Docling) |
| **Plain text** | CSV, TXT, YAML, XML, etc. (see RAG_PLAIN_TEXT_SUFFIXES in context_updater) | file path, raw UTF-8 text (no Docling) |

## Mydata layout (path-based JSON classification)

For correct classification of JSON files, use this structure under **mydata/**:

| Path | Content | RAG treatment |
|------|---------|----------------|
| **mydata/node-red/nodes/** | Node-RED nodes; catalogue lives here | Catalogue (see below) indexed; other node JSON *skipped for now; rules TBD* |
| **mydata/node-red/nodes/catalogue.json** | Node-RED catalogue (`{"modules": [...]}`) | One doc per module (cap 2000) |
| **mydata/node-red/workflows/** | Single Node-RED flows + library file | Workflows → one doc per file; library list → one doc per entry (cap 500) |
| **mydata/node-red/workflows/node-red-library-flows-refined.json** | Library flows (list of {_id, flow, readme, summary}) | One searchable doc per entry |
| **mydata/n8n/workflows/** | n8n workflow JSONs | One doc per workflow |
| **mydata/n8n/nodes/** | n8n nodes | *Skipped for now; rules TBD* |

Classification is **path-first**: e.g. anything under `node-red/workflows/` is treated as Node-RED workflow or library by path; structure (list vs dict, presence of `nodes`+`connections`, etc.) is used to distinguish library vs single flow and as fallback when path does not match. Arbitrary JSON outside these paths is not indexed as workflow.

**File types indexed:** Documents (`.pdf`, `.docx`, `.doc`, `.xlsx`, `.xls`, `.pptx`, `.ppt`, `.html`, `.md`) are indexed as documents from **any** folder under **mydata/** (and **units/**) — no path rules; they are always passed to Docling and embedded. Path-based classification applies **only to `.json`** files (workflow vs catalogue vs library, node-red vs n8n). In **units/** only document types are indexed; in **mydata/** both documents and JSON are indexed.

**No-index:** A single file **`mydata/.noindex.txt`** lists paths or files to exclude. Each line is a path or glob **relative to mydata** (e.g. `node-red/private`, `backup/*.pdf`). Comments: `#`; blank lines ignored.

## Workflow Designer context

The same index is used for **retrieval-augmented context**: when you chat with the Workflow Designer, the top‑k results for your message are injected into the prompt. The assistant can request **full file content** (e.g. a CSV for calculations) by outputting `{ "action": "read_file", "path": "/abs/path/to/file.csv" }` in a separate JSON block; the path must be under mydata, units, or repo root. The system will read the file (capped at 200k chars) and inject it into a follow-up turn so the model can use it.

- **units/** (repo) and **mydata/** (repo): Both are indexed automatically at GUI startup when their content has changed. Index data is kept separate from content: **rag/.rag_index_data/** holds `chroma_db/` and `.rag_index_state.json`; **mydata/** holds only user content (workflows, nodes, docs). State uses folder hashes (`units_hash`, `mydata_hash`) and per-file manifests (`units_files`, `mydata_files`: `relative_path → content MD5`) for **incremental** updates. Only changed, new, or removed files are updated; on first run a full index is done and manifests are saved.
- You can also add other folders via **Add documents to RAG** → **Add files from folder**. Indexing is additive; retrieval returns the most relevant chunks.

## Import from RAG (Workflow Designer)

The Workflow Designer assistant can import nodes and workflows from the RAG index:

- **import_unit**: `{ "action": "import_unit", "node_id": "node-red-node-http-request", "unit_id": "optional" }` — add a node from the Node-RED catalogue by id
- **import_workflow**: `{ "action": "import_workflow", "source": "/path/to/workflow.json", "merge": false }` — load a workflow from file path or URL; `merge: true` to merge into current graph

Use `index.get_node_by_id(node_id)` to look up node metadata by catalogue id.

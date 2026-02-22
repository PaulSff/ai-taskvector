# RAG Module

Semantic search over workflows, nodes, and user documents. Uses LlamaIndex, ChromaDB, and sentence-transformers. Runs on **CPU** (no GPU required).

## Install

```bash
pip install -r requirements-rag.txt
```

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
| **Nodes** | Node-RED catalogue | id, description, keywords, node_types |
| **Documents** | PDF, DOC, XLS | file path, extracted text |

## Import from RAG (Workflow Designer)

The Workflow Designer assistant can import nodes and workflows from the RAG index:

- **import_unit**: `{ "action": "import_unit", "node_id": "node-red-node-http-request", "unit_id": "optional" }` — add a node from the Node-RED catalogue by id
- **import_workflow**: `{ "action": "import_workflow", "source": "/path/to/workflow.json", "merge": false }` — load a workflow from file path or URL; `merge: true` to merge into current graph

Use `index.get_node_by_id(node_id)` to look up node metadata by catalogue id.

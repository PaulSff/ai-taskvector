"""
Core: graph model + edit + normalize + env.
- core.schemas: canonical ProcessGraph, Unit, Connection, training config, etc.
- core.normalizer: format conversion (dict, node_red, n8n, pyflow, ...) and export.
- core.graph: graph editing (GraphEdit, apply_graph_edit, import_resolver).
- core.env_factory: build_env(process_graph, goal) -> gym.Env.
"""

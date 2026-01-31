"""
Data normalizer: map various input formats to canonical process graph and training config.
Use everywhere for consistency.
"""
from normalizer.normalizer import (
    to_process_graph,
    to_training_config,
    load_process_graph_from_file,
    load_training_config_from_file,
)

__all__ = [
    "to_process_graph",
    "to_training_config",
    "load_process_graph_from_file",
    "load_training_config_from_file",
]

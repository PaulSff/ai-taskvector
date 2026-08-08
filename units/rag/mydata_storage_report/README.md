# MydataStorageReport Unit

The `MydataStorageReport` unit generates a structured data payload used by the mydata browser to display directory listings, storage summaries, and pie chart data.


## Description

This unit scans a specified directory (`mydata_dir`) and produces a view model containing entries for a single folder level, a summary of storage usage, and source data for a pie chart. It is typically used in conjunction with a frontend browser to visualize the organization of RAG data.


## Input Ports

- `rel_parts` (Any): A list of strings or a single string representing the relative path parts to navigate within the root directory.
- `organize_moved` (int): A trigger port. When wired from a `MydataOrganize` unit, it ensures the report is refreshed after files have been moved.


## Output Ports

- `data` (Any): The resulting view model payload, including folder entries, `summary_text`, `pie_src`, and `rel_parts_effective`.
- `error` (str): Contains error messages if directory resolution or processing fails.


## Parameters

- `mydata_dir` (str): **Required**. The path to the root directory to be reported on. Supports absolute paths or paths relative to the repository root.


## Implementation Details

The unit utilizes `build_mydata_refresh_view_model` from `rag.mydata_file_manager_ops` to perform the heavy lifting of filesystem analysis. It includes safe path resolution via `_resolve_under_repo` and flexible input coercion for `rel_parts` to ensure stability regardless of whether a string or list is provided.

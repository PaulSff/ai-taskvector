# MakeDir Unit 

The `MakeDir` unit provides a standardized way to recursively create directories on the local file system within the TaskVector framework.


## Overview

The `MakeDir` unit is a coding utility designed to ensure a specific directory path exists. It handles path expansion (e.g., `~` for home directory) and recursive creation of parent folders, making it ideal for initializing project structures or output folders.


## API Specification

### Ports
- **Input Ports**:
  - `parser_output` (Any): The primary input containing the directory path request.
- **Output Ports**:
  - `data` (Any): A result dictionary containing the status and the resolved path.
  - `error` (str): An error message if the operation fails.

### Input Format
The unit accepts two dictionary formats for the `parser_output` port:
1. **Direct Path**: `{ "path": "/path/to/dir" }`
2. **Action Wrapper**: `{ "action": "make_dir", "path": "/path/to/dir" }`


## Output Details

Upon successful execution, the `data` port returns:
- `ok`: `True`
- `output_path`: The absolute resolved string path of the created directory.
- `error`: `None`

In case of failure (e.g., invalid path or OS permission error), the `error` port is populated with a descriptive string, and `data['ok']` is set to `False`.


## Usage Examples

**Example 1: Simple Directory Creation**
Input:
```json
{ "path": "~/my_project/logs" }
```
Result: Creates the `logs` folder and any missing parents in the user's home directory.

**Example 2: Using Action Wrapper**
Input:
```json
{ "action": "make_dir", "path": "/tmp/taskvector/output" }
```
Result: Ensures the directory exists at the specified absolute path.


## Technical Implementation Notes

- **Path Resolution**: Uses `pathlib.Path().expanduser().resolve()` to ensure paths are absolute and normalized.
- **Idempotency**: Uses `mkdir(parents=True, exist_ok=True)`, meaning the unit can be run multiple times without error if the directory already exists.

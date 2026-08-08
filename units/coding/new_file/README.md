# NewFile Unit

The NewFile unit is a specialized utility within the TaskVector framework designed to write arbitrary text or code files to the local filesystem. It acts as a 'sink' for parsed LLM outputs, converting structured JSON data into physical files.


## Core Functionality

The unit takes a structured input (typically from a ProcessAgent), ensures the target directory exists, resolves a unique filename to avoid overwriting existing data, and writes the provided content using UTF-8 encoding.


## Input Specification

The unit expects a single input port: `parser_output` (Type: `Any`, expected as `dict`).

**Required Fields:**
- `output_dir` (str): The absolute or relative path to the directory where the file should be saved.
- `file` (dict): A dictionary containing the file details:
    - `content` (str): The actual text/code to be written to the file.
    - `output_format` (str, optional): A hint for the file extension (e.g., 'py', 'json', 'md'). Defaults to 'txt'.
    - `file_name` (str, optional): The desired name of the file. If omitted, defaults to `new_file.<output_format>`.


## Output Specification

The unit provides two output ports:

1. **`data` (dict):**
    - `ok` (bool): True if the file was written successfully.
    - `output_path` (str): The final absolute path to the created file.
    - `file_preview` (str): The first 500 characters of the written content.
    - `error` (str | None): Error message if `ok` is False.

2. **`error` (str):** A direct string output of the error message if the operation failed.


## Filename & Collision Logic

To prevent accidental data loss, the unit implements a unique path resolution strategy:
1. **Extension Handling:** If `file_name` is provided without an extension, the `output_format` is appended.
2. **Collision Avoidance:** If the resolved path already exists, the unit appends a numeric suffix to the stem. 
   *Example:* `main.py` $
ightarrow$ `main_1.py` $
ightarrow$ `main_2.py`.


## Usage Examples

**Example 1: Writing a Python Script**
```json
{
  "output_dir": "./scripts",
  "file": {
    "output_format": "py",
    "file_name": "utils.py",
    "content": "def add(a, b):\n    return a + b"
  }
}
```

**Example 2: Writing a JSON Config (Default Filename)**
```json
{
  "output_dir": "/tmp/config",
  "file": {
    "output_format": "json",
    "content": "{\"version\": \"1.0\"}"
  }
}
```
*Result: Creates `/tmp/config/new_file.json`*

# EditFile Unit  

The EditFile unit provides a surgical way to modify existing text files using unified-diff patches. Unlike a full-file overwrite, it validates the existing content (context) before applying changes, ensuring that edits are applied to the correct version of the file.


## Core Functionality

The `EditFile` unit reads a target file from the disk, parses a provided unified-diff patch string, and applies the changes in-place. It is specifically designed for 'surgical' edits where only a few lines need to change within a larger file. If the file content does not match the expected context lines in the patch, the operation fails to prevent data corruption.


## API Specification

### Input Port: `parser_output` (Any)
Expects a dictionary with the following structure:

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `output_dir` | `string` | Yes | Absolute path to the directory containing the target file. |
| `file` | `dict` | Yes | Configuration for the file edit. |
| `file.patch` | `string` | Yes | A valid unified-diff patch string containing hunks (e.g., `@@ -1,1 +1,1 @@`). |
| `file.file_name` | `string` | No | Name of the file. If omitted, defaults to `new_file.txt`. |
| `file.output_format`| `string` | No | Extension hint (e.g., `py`, `js`). Used if `file_name` has no extension. |

### Output Port: `data` (Any)
Returns a dictionary upon success:

- `ok` (bool): `True` if the patch was applied successfully.
- `output_path` (string): The full system path to the modified file.
- `file_preview` (string): The first 500 characters of the resulting file content.

### Output Port: `error` (string)
Returns a descriptive error message if the operation fails. Common errors include:
- `target file does not exist`: The file at the specified path was not found.
- `context mismatch`: The lines in the file do not match the context lines in the patch.
- `patch contained no recognizable unified-diff hunks`: The patch string is malformed.


## Usage Example

**Scenario:** Changing a function definition in a Python file.

**Target File (`path/to/my/file/app.py`):**
```python
def greet():
    print("Hello World")
```

**Input to `EditFile`:**
```json
{
  "output_dir": "path/to/my/file",
  "file": {
    "file_name": "app.py",
    "patch": "@@ -1,2 +1,2 @@\n-def greet():\n+def greet(name):\n     print(\"Hello World\")"
  }
}
```

**Result:**
- `ok`: `true`
- `output_path`: `path/to/my/file/app.py`
- `file_preview`: `def greet(name):\n    print("Hello World")`


## Technical Constraints

- **Encoding:** Files are read and written using `UTF-8`.
- **Patch Format:** Only unified-diff format is supported. It ignores file headers (`---`/`+++`) and focuses on the `@@` hunks.
- **Atomicity:** The unit reads the entire file into memory, applies the patch, and then overwrites the file.

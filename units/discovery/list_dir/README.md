# Unit ListDir

The `ListDir` unit is used for local filesystem discovery within the user's machine.


## Overview

The `ListDir` unit provides a non-recursive listing of a local directory. It identifies and separates subdirectories from files, returning them in a structured format. It is categorized under the `discovery` environment tag.


## API Specification

### Input Ports
- **action** (`Any`): The primary control port. Expects a dictionary: 
```json 
{"action": "list_dir", "path": "/path/to/dir"}
```
- **path** (`Any`): Optional. If provided, the value must exactly match the path specified in the `action` payload.
- **data** (`Any`): Optional. Can be used as an alternative to the `action` port to provide the payload containing `path`.

### Output Ports
- **data** (`Any`): A dictionary containing the results:
  - `path`: The resolved absolute path.
  - `content`: An object containing `dirs` (list of directory names) and `files` (list of file names).
- **error** (`str`): Contains the error message if the operation fails (e.g., `FileNotFoundError`), otherwise `None`.


## Usage Examples

**Scenario 1: Standard Directory Listing**
- **Input (action):** 
```json
{"action": "list_dir", "path": "/home/user/documents"}
```
- **Output (data):** 
```json
{"path": "/home/user/documents", 
 "content": 
     {
       "dirs": ["work", "personal"], 
       "files": ["notes.txt", "budget.xlsx"]
     }
}
```

**Scenario 2: Path is a Single File**
- **Input (action):** 
```json 
{"action": "list_dir", "path": "/home/user/documents/notes.txt"}
```
- **Output (data):** 
```json
{
  "path": "/home/user/documents/notes.txt", 
   "content": 
       {
         "dirs": [], 
         "files": ["notes.txt"]
       }
}
```

**Scenario 3: Error Handling (Path not found)**
- **Input (action):** `{"action": "list_dir", "path": "/invalid/path"}`
- **Output (error):** `"path not found: /invalid/path"`


## Technical Constraints

- **Non-Recursive**: The unit only lists the immediate children of the specified path.
- **Case Sensitivity**: Directory entries are sorted using a case-insensitive lower-case key.
- **Validation**: Strict validation is performed on the `action` payload; missing keys or incorrect action names will trigger a `ValueError`.

# Rename Unit

Detailed technical documentation for the Rename unit, which provides a safe mechanism to rename files or directories within the TaskVector framework.


## Overview

The `Rename` unit is a coding utility designed to change the name of a file or folder. To prevent accidental movement of files across the filesystem, the unit strictly enforces that the rename occurs within the same parent directory as the source file.


## Interface Specification

### Input Ports
- `parser_output` (Any): The primary input. Expected to be a dictionary containing the path and the desired new name.

### Output Ports
- `data` (Any): A dictionary containing the operation result (`ok` boolean and `output_path` string).
- `error` (str): A descriptive error message if the operation fails; otherwise `None`.


## API Usage & Request Format

The unit accepts two formats for the `parser_output` input:

1. **Direct Format**:
   ```json
   {
     "path": "/path/to/old_name.txt",
     "new_name": "new_name.txt"
   }
   ```

2. **Wrapped Format**:
   ```json
   {
     "action": "rename",
     "path": "/path/to/old_name.txt",
     "new_name": "new_name.txt"
   }
   ```

**Important Note:** The `new_name` field must be a filename/folder name only. If a full path is provided in `new_name`, the unit will automatically strip the directory components and only use the base name to ensure the file stays in its original folder.


## Operational Logic & Safety

The unit implements several safety checks before executing the rename:
- **Path Validation**: Resolves the source path and ensures it exists (or is a valid symlink).
- **Collision Prevention**: Checks if the target filename already exists in the destination directory. If it does, the operation fails to prevent accidental overwriting.
- **Sanitization**: Trims whitespace from paths and names to avoid common string errors.


## Examples

**Success Case:**
Input: `{"path": "/home/user/docs/draft.txt", "new_name": "final.txt"}`
Output `data`: `{"ok": true, "output_path": "/home/user/docs/final.txt", "error": null}`

**Failure Case (Target Exists):**
Input: `{"path": "/home/user/docs/a.txt", "new_name": "b.txt"}` (where b.txt already exists)
Output `error`: `"target already exists: /home/user/docs/b.txt"`

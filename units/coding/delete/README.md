# Delete Unit

The Delete unit provides a robust mechanism for removing files, symbolic links, or directories (recursively) from the filesystem based on a provided path.


## Overview

The `Delete` unit is part of the `coding` environment. It is designed to handle filesystem cleanup by resolving paths (including user expansion like `~`) and executing the appropriate deletion method based on whether the target is a file or a directory.


## Technical Specification

- **Unit Type:** `Delete`
- **Environment Tag:** `coding`
- **Input Ports:** `parser_output` (Any)
- **Output Ports:** `data` (Any), `error` (str)


## Input API

The unit expects a dictionary on the `parser_output` port. It supports two formats:

1. **Direct Path:**
   ```json
   { "path": "/path/to/target" }
   ```

2. **Action Wrapper:**
   ```json
   { "action": "delete", "path": "/path/to/target" }
   ```

**Path Resolution:** The unit automatically calls `.expanduser().resolve()`, meaning it supports relative paths and home directory shortcuts.


## Output API

The unit returns a result dictionary via the `data` port and an error message via the `error` port if the operation fails.

**Success Response:**
```json
{
  "data": {
    "ok": true,
    "deleted_path": "/absolute/path/to/deleted/item",
    "error": null
  },
  "error": null
}
```

**Error Response:**
```json
{
  "data": {
    "ok": false,
    "deleted_path": "",
    "error": "path does not exist: /path/to/nothing"
  },
  "error": "path does not exist: /path/to/nothing"
}
```


## Behavioral Notes

- **Files/Symlinks:** Uses `unlink()` to remove the target.
- **Directories:** Performs a recursive bottom-up deletion. It finds all nested files and folders using `rglob('*')`, sorts them in reverse order to ensure children are deleted before parents, and then removes the root directory using `rmdir()`.


## Examples

**Example 1: Deleting a specific log file**
Input: `{ "path": "~/logs/app.log" }`
Result: Deletes the file in the user's home directory.

**Example 2: Recursive directory cleanup**
Input: `{ "path": "/tmp/build_cache" }`
Result: Deletes all files and subdirectories within `build_cache`, then deletes the folder itself.

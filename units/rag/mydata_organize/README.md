# MydataOrganize Unit

The MydataOrganize unit is responsible for maintaining the structural integrity of the RAG data directory by moving loose, root-level files into their designated category folders.


## Behavior

This unit acts as a file manager for the `mydata` directory. It scans the root of the specified directory and organizes files into a standardized RAG layout. Specifically, it moves files into the following subdirectories:
- `node-red/`
- `n8n/`
- `canonical/`
- `_organized/`

It utilizes the `organize_mydata_root` operation from the `rag.mydata_file_manager_ops` module to perform the actual file system manipulations.


## API Specification

### Input Ports
This unit has **no input ports**. It operates based on its internal parameters.

### Parameters
| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `mydata_dir` | String | Yes | The path to the directory to be organized. Supports absolute paths or paths relative to the repository root. |

### Output Ports
| Port | Type | Description |
| :--- | :--- | :--- |
| `moved` | Integer | The total number of files successfully moved during the operation. |
| `error` | String | Contains an error message if the operation fails (e.g., missing directory). Empty string on success. |


## Technical Implementation

- **Path Resolution**: The unit uses a helper `_resolve_under_repo` to ensure that relative paths are correctly expanded relative to the project root.
- **Error Handling**: It catches `TypeError` and `ValueError` during the organization process, returning the first 300 characters of the exception as the error output to prevent log flooding.

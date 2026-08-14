# FindAndReplace Unit

The `FindAndReplace` unit generates a unified-diff patch by replacing exact text regions within a file. It is designed for precision and safety, ensuring that replacements are deterministic and do not overlap.

## API Specification

### Input
- **Port**: `parser_output` (Any)
- **Expected Format**: A JSON object with the following structure:

```json
{
  "action": "edit_file",
  "output_dir": "/path/to/directory",
  "file": {
    "file_name": "example.py",
    "content": "optional original content",
    "replacement_1": {
      "line_num_ref": 126,
      "find": "old text",
      "replace_with": "new text"
    },
    "replacement_2": {
      "line_num_ref": 45,
      "find": "another old text",
      "replace_with": "another new text"
    }
  }
}
```

### Parameters
- `unified_diff_n_context_lines_around` (int): The number of context lines to include in the generated unified diff. Defaults to `3`.

### Output
- **Port**: `data` (Any)
- **Format**:

```json
{
  "output_dir": "/path/to/directory",
  "file": {
    "ok": true,
    "file_name": "example.py",
    "output_format": "py",
    "patch": "--- a/example.py\n+++ b/example.py...",
    "error": null,
    "file_preview": "first 500 characters of updated text",
    "audit": [
      {
        "index": 0,
        "start_line": 126,
        "end_line": 126,
        "line_num_ref": 126,
        "match_count_before_disambiguation": 1,
        "find_characters": 9,
        "replace_with_characters": 11
      }
    ]
  }
}
```

## Key Features

1. **Exact Matching**: The `find` field must match the original text exactly, including whitespace and line endings.
2. **Disambiguation**: If the `find` text appears multiple times in a file, the `line_num_ref` is used to select the occurrence closest to the specified line number.
3. **Overlap Prevention**: The unit validates that no two replacement regions overlap. If they do, the operation fails to prevent file corruption.
4. **Non-Destructive**: The unit does not write to the disk directly; it generates a patch that can be applied by a subsequent process.
5. **Audit Trail**: Every replacement is logged with start/end lines and character counts for verification.

## Error Handling

The unit provides detailed error messages and hints. Common errors include:
- **Find text not found**: Ensure the `find` string is an exact match.
- **Ambiguous match**: Provide a `line_num_ref` or make the `find` string more specific.
- **Overlapping regions**: Ensure replacements do not target the same character offsets.
- **Missing replacements**: At least `replacement_1` must be provided.
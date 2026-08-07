# NewFile Unit

Write arbitrary code/text files to disk (no LLM call).

## What it does

The **NewFile** unit writes a text file into `${output_dir}` usin `parser_output["file"]`. If the chosen filename already exists, it writes a unique suffixed name like: `<name>_1<ext>`, `<name>_2<ext>`, etc.

## Inputs

### `parser_output`
`parser_output` must contain a `file` object:

```json
{ 
  "action": "new_file"
  "output_dir": "/path/to/out",
  "file": {
    "output_format": "py",
    "file_name": "hello_world.py",
    "content": "def main():\n    print('hello world')\n\nif \_\_name\_\_ == '\_\_main\_\_':\n    main()\n"
  }
}
```

Fields:

- `action` (optional): optional action field (expected `"action": "new_file"`)
- `output_format` (optional): file extension hint (e.g., `py`, `js`, `json`, `xml`, `txt`, `sh`, etc.). Any string is accepted.
- `content` (required): exact text written to the file as-is.
- `file_name` (optional): target filename (e.g., `main.py`, `package.json`).
  - If omitted, defaults to `new_file.<output_format>`.

### Outputs

- `data.ok`: true if the write succeeded
- `data.output_path`: full path to the written file
- `data.file_preview`: first 500 characters of content (with ... if longer)
- `error`: error message string on failure

## Examples

Example - writing a Python file:

```json
{
  "output_dir": "/path/to/out",
  "file": {
    "output_format": "py",
    "file_name": "hello_world.py",
    "content": "def main():\n    print('hello world')\n\nif \_\_name\_\_ == '\_\_main\_\_':\n    main()\n"
  }
}
```

Example - writing JSON:

```json
{
  "output_dir": "/path/to/out",
  "file": {
    "output_format": "json",
    "file_name": "config.json",
    "content": "{\n  \"mode\": \"dev\"\n}\n"
  }
}
```

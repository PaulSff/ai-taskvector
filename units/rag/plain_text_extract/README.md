# PlainTextExtract Unit

The PlainTextExtract unit reads a plain-text file from the local filesystem and transforms it into a structured RAG item containing the text and associated metadata.


## API Specification

### Input Ports
- `data` (Any): Accepts a bare file path string, a dictionary containing a `file_path` key, or a RagDetectOrigin context envelope.
- `file_path` (Any): A direct path to the file. This port takes precedence over the `data` port.

### Output Ports
- `items` (Any): A list containing a single RAG item: `[{ "text": "...", "metadata": { ... } }]`.
- `error` (str): Contains error messages if the file cannot be found or read.


## Parameters

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `max_chars` | int | 50,000 | Maximum number of characters to read from the file to prevent memory overflow. |
| `encoding` | str | "utf-8" | The character encoding used to read the file. |
| `origin` | str | "plain_text" | A label stored in the metadata to identify the source of the text. |
| `content_type` | str | "text/plain" | The MIME type stored in the metadata. |


## Data Flow

1. **Path Resolution**: The unit first checks `file_path`, then `data` (as a dict or string) to find the target file.
2. **Extraction**: The file is read using the specified encoding. If the content exceeds `max_chars`, it is truncated.
3. **Structuring**: The text is wrapped in a list with metadata including the absolute resolved path, origin, and content type.
4. **Output**: The resulting list is sent to the `items` port, or an error is sent to the `error` port.

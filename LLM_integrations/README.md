## LLM integrations

This folder contains **LLM adapter modules** used by the GUI/assistants. Each adapter hides vendor/client details behind a small, consistent API so the rest of the codebase doesn’t need to know *how* a model is called (Ollama, OpenAI, etc.).

Current implementation:

- **`ollama.py`**: wrapper around `ollama-python` for local/remote Ollama servers.

---

## What an integration should provide

When you add a new model provider, create a new module in this folder, e.g.:

- `LLM_integrations/openai.py`
- `LLM_integrations/azure_openai.py`
- `LLM_integrations/lmstudio.py`
- `LLM_integrations/vllm.py`

At minimum, keep the same shape as `ollama.py`:

- **`chat(...) -> str`**
  - Inputs:
    - `model: str`
    - `messages: list[dict[str, str]]` in OpenAI-style format: `{ "role": "system"|"user"|"assistant", "content": "..." }`
    - connection settings (host/base_url, timeouts, options)
  - Output:
    - **assistant text** (string)

- **`list_models(...) -> list[str]`** (optional but recommended)
  - Returns model identifiers supported by the provider/server.

- **`format_<provider>_exception(e: Exception) -> str`** (recommended)
  - Convert transport/auth/model errors into a user-friendly message for the GUI.

Keeping this API stable makes it easy to swap providers in the chat UI without touching the assistants logic.

---

## How assistants use the integration

The assistants prompts live in **`assistants/prompts.py`**:

- `WORKFLOW_DESIGNER_SYSTEM`
- `RL_COACH_SYSTEM`

The Flet chat panel (currently `gui/flet/chat_with_the_assistants/chat.py`) builds a message list like:

- `{"role": "system", "content": <prompt from assistants/prompts.py>}`
- prior chat history (user/assistant turns)
- `{"role": "user", "content": <user message + context>}`

Then it calls `LLM_integrations.<provider>.chat(...)` and receives a **string** response.

For Workflow Designer:

- The response is expected to include a JSON edit block.
- The UI parses the JSON block and applies it via **`assistants.process_assistant.process_assistant_apply()`**, which normalizes back to `ProcessGraph`.

For RL Coach:

- The response is currently shown but **not applied** in the Flet GUI yet (training config integration is the next step).

---

## Adding a new provider (step-by-step)

### 1) Create the adapter module

Add `LLM_integrations/<provider>.py` implementing:

- `chat(...) -> str`
- (optional) `list_models(...) -> list[str]`
- (recommended) `format_<provider>_exception(e) -> str`

Keep `messages` compatible with the existing prompts and chat history:

```python
messages = [
  {"role": "system", "content": "..."},
  {"role": "user", "content": "..."},
]
```

### 2) Add settings keys (host, model, API key)

Settings are stored in **`config/app_settings.json`** and edited via:

- `gui/flet/components/settings.py`

For a new provider you’ll typically add:

- `<provider>_base_url` or `<provider>_host`
- `<provider>_model`
- `<provider>_api_key` (store securely; do **not** commit)

If you add secrets, **ignore** them in git (or load from environment variables). Avoid committing API keys.

### 3) Update the chat panel to select the provider

Update `gui/flet/chat_with_the_assistants/chat.py` to use the new adapter, e.g.:

- import `LLM_integrations.openai as openai_integration`
- select provider based on settings (or a dropdown)
- call `<provider>_integration.chat(...)`
- display the returned string as the assistant message

### 4) Validate end-to-end

For Workflow Designer, confirm:

- model output includes a valid JSON edit block
- edit applies cleanly via `process_assistant_apply()`
- the graph refreshes in the GUI

For RL Coach, confirm:

- model output includes a JSON edit or `reward_from_text` action as per `assistants/prompts.py`

---

## Provider compatibility notes

- **Message format**: Some providers use a different message schema (e.g. “content parts”, tool calls). The adapter should translate *from* our simple `{role, content}` list.
- **Timeouts**: Keep generous timeouts for first call (model load) or local servers.
- **Determinism**: For edits, lower temperature (e.g. 0.2–0.4) usually yields more reliable JSON.
- **Output parsing**: The assistant must output a JSON object inside a fenced code block where possible. If your provider supports tool/function calling, you can enhance the adapter to return structured JSON directly, but keep a fallback to text for portability.


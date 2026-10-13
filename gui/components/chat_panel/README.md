# Chat Panel Component

The Chat Panel is the primary messenger interface for TaskVector, providing a bridge between the user and the AI agent workflows.


## Overview

The `chat.py` module implements a pure UI layer using the Flet framework. It is responsible for rendering chat bubbles, managing the streaming experience, and handling user inputs. It delegates all business logic, session management, and workflow execution to the `turn_driver`.


## Key Features

- **Dynamic Layout**: Switches from a 'first-message' top-aligned composer to a standard bottom-aligned chat interface after the first interaction.
- **Streaming UI**: Supports real-time token streaming with a throttled update mechanism to ensure UI responsiveness.
- **Session Persistence**: Automatically saves chat history and allows users to restore previous sessions via a recent chats menu.
- **Graph Interaction**: Integrated with the Workflow Designer, allowing agents to trigger graph updates via `on_apply` hooks.
- **Rich Rendering**: Supports code fences and rich-text formatting within agent responses.


## Architecture & Data Flow

1. **Input**: User enters text in `ChatLayoutComponent` $\rightarrow$ `_send_from_field` captures input.
2. **Execution**: `_run_chat_turn` calls `turn_driver.handle_turn()`, passing the current graph and role configuration.
3. **Streaming**: `turn_driver` invokes a callback $\rightarrow$ `_stream_cb` updates the `stream_row` in the UI.
4. **Finalization**: Once the turn completes, the streaming bubble is replaced by a permanent rendered message row.


## Dependencies

- `flet`: UI Framework.
- `agents.chat.turn_driver`: Core logic for handling turns and session I/O.
- `agents.chat.session`: Session state and persistence management.
- `gui.components.chat_panel.ui`: Specialized UI sub-components (Layout, FocusHandler, MessageRenderer).

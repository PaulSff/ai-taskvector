# Turn Driver Component

The Turn Driver is a core orchestration component within the chat agent system, responsible for managing the lifecycle of a single interaction turn between the user and the AI.


## Overview

The `turn_driver.py` acts as the central controller for processing incoming user messages, coordinating with the LLM, managing state transitions, and ensuring that the final response is delivered back to the user. It abstracts the complexity of the 'turn' logic from the transport layer.


## Key Responsibilities

- **Input Processing**: Validating and preparing user input for the agent.
- **Context Management**: Ensuring the conversation history and system prompts are correctly injected.
- **Execution Loop**: Managing the iterative process of thought, action, and observation (if applicable).
- **Response Formatting**: Ensuring the output adheres to the expected chat interface format.


## Logic Flow

1. **Receive Request**: Accepts a turn request containing the user message and session ID.
2. **State Retrieval**: Fetches the current conversation state from the persistence layer.
3. **Agent Invocation**: Passes the state and message to the underlying AI agent.
4. **Turn Resolution**: Monitors the agent's output until a final response is generated or a timeout occurs.
5. **State Update**: Saves the updated conversation history.
6. **Return Response**: Sends the final result back to the caller.


## API Reference

### `process_turn(request: TurnRequest) -> TurnResponse`

The primary entry point for handling a single interaction turn.

**Inputs:**
- `request` (`TurnRequest`): An object containing:
    - `session_id` (str): Unique identifier for the conversation session.
    - `message` (str): The raw text input from the user.
    - `context_overrides` (dict, optional): Temporary state or prompt overrides for this specific turn.

**Outputs:**
- `TurnResponse`: An object containing:
    - `response_text` (str): The final AI-generated message.
    - `turn_id` (str): Unique identifier for the completed turn.
    - `metadata` (dict): Execution stats, tool calls made, and token usage.

**Parameters:**
- `timeout`: Maximum time allowed for the agent to resolve the turn before returning a timeout error.
- `max_iterations`: Limit on the number of thought/action cycles per turn to prevent infinite loops.

## Usage Examples

### Basic Integration
```python
from agents.chat.turn_driver import TurnDriver
from agents.chat.models import TurnRequest

# Initialize the driver
driver = TurnDriver(agent_backend=my_ai_agent)

# Create a request
request = TurnRequest(
    session_id="user_123_session_456",
    message="How do I configure the TaskVector framework?"
)

# Process the turn
response = driver.process_turn(request)
print(f"AI: {response.response_text}")
```

### Handling Context Overrides
```python
request = TurnRequest(
    session_id="user_123",
    message="Analyze this log file",
    context_overrides={"system_prompt": "You are a senior DevOps engineer."}
)
response = driver.process_turn(request)
```

## Dependencies

The component relies on the TaskVector framework's core agent interfaces and the session management system for state persistence.

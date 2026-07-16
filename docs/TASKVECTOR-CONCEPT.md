# TASKVECTOR-CONCEPT.md

## Core concept

AI TaskVector is a graph-first framework where the canonical process graph represents any workflow, and the platform acts like an operating system for an autonomous AI team. Specialized AI agents coordinate work, but their autonomy is constrained to controllable framework units/tools, ensuring predictable behavior. The system strives for continual improvement by performing training during operation and turning learnings into new or enhanced units. The long-term goal is a self-building AI team that assists users across their needs while expanding its capabilities inside the framework’s boundaries.

## Overview: “Everything is a canonical workflow (process graph)”

In TaskVector, **every process can be represented as a canonical graph**—a workflow described by:

- a set of **units** (nodes)
- a set of **directed connections** (edges) that wire **ports**
- optional **code blocks** (language-agnostic payloads preserved for roundtrip)
- optional **layout metadata** (for editors)
- optional **comments** (metadata-only notes)
- todo lists andits tasks

This **canonical process graph** is the single source of truth for topology and (when present) execution-relevant details such as units, ports, environment type, and graph structure. External formats (Node-RED, PyFlow, n8n, Ryven, etc.) are normalized *into* this schema.

The result: instead of “scripts that run somewhere,” TaskVector treats work as a **portable, inspectable, and controllable graph**.

## What TaskVector is: an operating system for autonomous agent work

TaskVector is best understood as a **local-first operation system** for an “AI team.”

Inside the system:

- specialized **agents** coordinate, design, dispatch tasks, analyze outcomes, and train/update capabilities
- the system can execute workflows deterministically via a native runtime
- training and improvement are modeled as part of graph operation, not a separate offline ritual

In other words, the platform isn’t just a prompt/chat interface—it’s a framework where agent activity is structured as runnable workflows.

## Core principles

### 1) Graph = the source of truth
The canonical graph defines:
- topology (what exists and how it connects)
- environment type (which execution semantics apply)
- optional embedded artifacts (e.g., code blocks)
- optional editor layout

Execution and summary logic read from the graph only.

### 2) Ports and connections are mandatory
Workflows are not “best-effort.” **Ports + connections define the data flow contract**. When ports are missing after import or edits, normalization enriches the graph using unit specs, ensuring the executor can run without guessing.

### 3) Structure constrains autonomy (predictable, controllable behavior)
The framework draws strict boundaries around agent actions:

- Agents **operate within defined unit/task semantics**
- Agents cannot “take over the computer” because the system only provides capabilities that exist as **tools/units** inside the framework
- A workflow’s wiring and unit types determine what is allowed and what is connected

This keeps autonomy practical: agents can act, but **only through controllable, observable framework primitives**.

### 4) Roles and tools/skills are modular and composable
TaskVector supports easy creation of:
- **roles** (agent personas with responsibilities and prompt configuration)
- **tools** (framework capabilities usable by agents)
- **units** (graph nodes representing executable functionality)

This makes skill growth systematic: adding new capability means registering it as a unit/tool and wiring it into graphs.

### 5) Training during operation (lifelong loop)
TaskVector’s concept aims for a continuous improvement loop:

- the AI team executes workflows for user goals
- outcomes generate signals (data, reward proxies, evaluation results, traces)
- the system updates models and/or training configuration
- the updated capabilities become new or improved units, which are then used in future workflows

Training is not only “before deployment”—it is part of ongoing operation.

## Agent autonomy: the “AI team” concept

The ultimate goal is an autonomous **AI team** that:

- follows a general agenda (assist users reliably)
- coordinates internal roles to complete tasks
- learns and improves by constructing **new units** and enhancing existing ones
- gradually expands its toolkit while remaining constrained by framework boundaries

Concretely, autonomy is implemented as:
- agents designing and dispatching workflows as graphs
- the system executing those workflows within the canonical runtime
- feedback loops feeding training and unit creation

## Framework structure: boundaries that make autonomy safe-by-design

TaskVector’s folder/module structure reflects responsibility boundaries that restrict agent behavior to predictable operations:

- **agents/**: role definitions and dispatcher/analyst/designer behavior
- **units/**: executable graph nodes (canonical units and environment-specific units)
- **core/**: canonical process graph schemas and training/rewards DSL components
- **runtime/**: graph executor (native workflow execution)
- **server/**: inference server / predict endpoints used by agent units when applicable
- **deploy/**: external runtime compatibility and roundtrip packaging
- **LLM_integrations/**: unified client/adapters for LLM providers (e.g., local model backends)
- **rag/**: knowledge base and long-memory mechanisms for the AI team
- **gui/**: authoring, visualization, and development instrumentation

These boundaries ensure the agents are not “operating outside the system”; they are operating through the system’s defined primitives.

## Canonical workflow mindset: “Every process is a graph”

A practical way to think about TaskVector:

- If you can draw a process with steps and data flow, you can express it as a graph.
- If a graph can be executed, it can be trained, evaluated, and improved.
- If it can be imported and normalized, it can become part of the system’s canonical world.

That makes TaskVector a convergence layer between:
- workflow authoring
- execution
- training
- capability expansion

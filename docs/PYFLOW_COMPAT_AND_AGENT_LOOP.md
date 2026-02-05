# PyFlow adapter: compatibility and where the agent sits

This doc clarifies (1) whether our inline execution is **fully compatible** with the user’s original PyFlow workflow, and (2) whether the **RL Agent is in the loop** during training.

---

## 1. Full compatibility with the user’s imported PyFlow?

**No.** Our current executor does **not** provide full compatibility with whatever the user built in the PyFlow editor.

**What we do:**

- We **import** the user’s PyFlow JSON and **normalize** it into our canonical graph (units, connections, code_blocks). Node type is taken from their JSON (e.g. `"PyFlow.Packages.Foo.Valve"` → we keep `"Valve"`). We only **execute** a subset of node types explicitly; everything else is treated as generic.

**How we execute each node:**

| Our handling | Node type / content | Compatibility |
|--------------|--------------------|----------------|
| **code_blocks** | We extract `code` / `script` / `source` / `expression` from nodes and run it with `exec()` in a limited scope (`state`, `inputs`). | Same code runs, but **scope/environment is ours**, not PyFlow’s (e.g. no PyFlow pin API). |
| **Source** | We read `params` (e.g. `temp`) and set state. | Matches for simple source nodes. |
| **RLAgent** | We load the SB3 model and call `predict(obs)`. | Our extension; not in original PyFlow. |
| **Valve, Tank, Sensor** | We don’t have special physics for these; they fall through to **pass-through** or default. | Only structure (id, type, params) is preserved; execution is “first input → output” or 0.0. |
| **All other node types** | **Pass-through**: output = first input’s value, or 0.0 if no inputs. | **Not** the same as PyFlow. Math, compound, graphInputs/graphOutputs, custom nodes, etc. are **not** executed with PyFlow semantics. |

So:

- **Topology** (which nodes exist and how they’re connected): we preserve what we parse from the PyFlow export; connection parsing may differ from PyFlow’s pin model in edge cases.
- **Execution semantics**: only **code** (in our scope) and **Source** (params) are handled in a dedicated way. Everything else is pass-through. So we do **not** guarantee full compatibility with the original PyFlow workflow; we’re compatible with “graph structure + code nodes + our Source/RLAgent handling.”

If the user’s flow uses only nodes we support (Source, code nodes, and valves/tanks/sensors used as pass-through or for structure), behavior can be close. If it uses other PyFlow node types (math, compound, custom packages, etc.), those nodes will **not** run as in PyFlow.

---

## 2. Is the RL Agent “in the loop” during training?

**No.** During training the agent is **not** a node inside the graph. It sits **outside** the loop.

**Training:**

- The **environment** is the user’s workflow: we load their PyFlow-derived graph and run it with our executor.
- The config specifies **observation_sources** (node ids whose outputs form `obs`) and **action_targets** (node ids that receive the action).
- Each step:
  1. We run the graph once (our executor).
  2. We read **obs** from the observation_sources.
  3. The **RL algorithm (e.g. PPO)** in `train.py` chooses an **action** from `obs`.
  4. We **inject** that action into the action_target nodes (`_send_action`).
  5. We run the graph again (so downstream nodes see the new action values).
  6. We compute reward (from `goal` or a reward node) and return `obs`, `reward`, etc. to the algorithm.

So the “agent” during training is the PPO (or other) policy in the training script; it is **not** an RLAgent node in the graph. The graph is the **environment**; the agent is **outside**, feeding actions into designated nodes.

**Deployment (after training):**

- We **inject** an **RLAgent** node into the flow and wire it (observations → agent, agent → action targets).
- When we run that flow with our executor, we **do** evaluate the RLAgent node in the loop: we load the trained model and call `predict(obs)` when we hit that node. So **then** the agent is literally a node in the loop.

**Summary:**

- **Training:** Agent is **not** in the loop as a node; the graph is the env, and the algorithm injects actions from outside.
- **Deployment:** Agent **is** a node in the loop; we run the graph and execute the RLAgent node inline.

So “the RLAgent node sitting in the loop and training from there” is **not** what we do today. We train with the workflow as the env and the agent outside; we only put the agent in the loop for deployment (inference).

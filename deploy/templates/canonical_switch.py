# Canonical Switch (PyFlow): action vector -> out_0, out_1, ...
# Params: num_outputs (default 8)
action = inputs.get("action")
if action is None:
    action = []
if not isinstance(action, (list, tuple)):
    action = [float(action)] if action is not None else []
action = [float(x) for x in action]
n = int(params.get("num_outputs", 8))
n = min(max(n, 1), 8)
out = {}
for i in range(n):
    out["out_%d" % i] = action[i] if i < len(action) else 0.0
return out, state

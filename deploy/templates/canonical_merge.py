# Canonical Merge (PyFlow): in_0..in_{n-1} -> data dict (Any types).
# Params: num_inputs (default 8), keys (optional list of key names for output dict)
n = int(params.get("num_inputs", __TPL_NUM_INPUTS__))
n = min(max(n, 1), 8)
keys = params.get("keys")
if not isinstance(keys, (list, tuple)) or len(keys) < n:
    keys = ["in_%d" % i for i in range(n)]
data = {}
for i in range(n):
    k = str(keys[i]) if i < len(keys) else ("in_%d" % i)
    data[k] = inputs.get("in_%d" % i)
return {"data": data}, state

# Canonical Join (PyFlow): inputs in_0..in_{n-1} -> observation vector.
# Params: num_inputs (default 8)
n = int(params.get("num_inputs", 8))
n = min(max(n, 1), 8)
obs = []
for i in range(n):
    key = "in_%d" % i
    v = inputs.get(key)
    if v is None:
        obs.append(0.0)
    elif isinstance(v, (list, tuple)):
        obs.append(float(v[0]) if v else 0.0)
    else:
        obs.append(float(v))
return {"observation": obs}, state

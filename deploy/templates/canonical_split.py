# Canonical Split (PyFlow): trigger -> out_0..out_{n-1} (same value).
# Params: num_outputs (default 8)
value = inputs.get("trigger")
n = int(params.get("num_outputs", 8))
n = min(max(n, 1), 8)
out = {"out_%d" % i: value for i in range(n)}
return out, state

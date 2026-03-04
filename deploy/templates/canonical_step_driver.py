# Canonical StepDriver (PyFlow): trigger (reset|step) -> output 0 = start, output 1 = response.
trigger = inputs.get("trigger")
if trigger == "reset":
    return {"start": {"action": "start"}, "response": {"action": "idle"}}, state
return {"start": {"action": "step"}, "response": {}}, state

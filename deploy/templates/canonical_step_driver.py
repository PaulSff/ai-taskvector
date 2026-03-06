# Canonical StepDriver (PyFlow): trigger (reset|step) -> output 0 = start, output 1 = response, output 2 = trigger.
trigger = inputs.get("trigger") or "step"
if trigger == "reset":
    return {"start": {"action": "start"}, "response": {"action": "idle"}, "trigger": trigger}, state
return {"start": {"action": "step"}, "response": {}, "trigger": trigger}, state

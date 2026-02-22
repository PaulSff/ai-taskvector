# RLOracle step driver for PyFlow (in-process). Uses state['__rl_oracle_action__'] for injection.
# Placeholders: __TPL_ACT_NAMES__, __TPL_ACTION_KEY__
# Adapter sets state[__TPL_ACTION_KEY__] before step; on reset it's unset.

_act = __TPL_ACT_NAMES__
_action_key = __TPL_ACTION_KEY__
_result = state.get(_action_key)
if _result is not None:
    return _result
return [0.0] * len(_act)

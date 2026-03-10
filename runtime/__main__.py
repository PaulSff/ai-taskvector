"""
Run a workflow from file. All parameters via the run command (no hardcoding).

  python -m runtime workflow.json
  python -m runtime workflow.json --initial-inputs '{"inject_user_message":{"data":"hi"}}'
  python -m runtime workflow.json --initial-inputs @inputs.json --unit-params @unit_params.json
"""
from runtime.run import main

if __name__ == "__main__":
    main()

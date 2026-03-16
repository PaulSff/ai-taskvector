#!/usr/bin/env python3
"""
Backup script for trained models.
Backs up an agent folder (e.g. models/temperature-control-agent) or the legacy flat models/ layout.
Run from repo root: python scripts/backup_models.py [backup_name] [model_dir]
"""
import os
import shutil
from datetime import datetime
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def backup_models(backup_name=None, model_dir=None):
    """Backup an agent's model folder to models/backup_<name> or models/backup_<timestamp>.

    Args:
        backup_name: Name for the backup folder (e.g. "v1"). If None, uses timestamp.
        model_dir: Agent folder to back up (e.g. "models/temperature-control-agent").
                   If None, uses "models/temperature-control-agent" when it exists,
                   otherwise falls back to legacy paths under models/.
    """
    root = _repo_root()
    if model_dir is None:
        default_agent = root / "models" / "temperature-control-agent"
        model_dir = str(default_agent) if default_agent.is_dir() else None
    else:
        model_dir = str(Path(model_dir).expanduser())
        if not Path(model_dir).is_absolute():
            model_dir = str(root / model_dir)

    models_dir = root / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    if backup_name:
        backup_dir = models_dir / f"backup_{backup_name}"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = models_dir / f"backup_{timestamp}"

    backup_dir = str(backup_dir)
    os.makedirs(backup_dir, exist_ok=True)

    if model_dir and os.path.isdir(model_dir):
        # Agent subfolder: copy whole tree (best/, checkpoints/, logs/, configs, final zip)
        base = model_dir.rstrip("/")
        for name in os.listdir(base):
            src = os.path.join(base, name)
            dst = os.path.join(backup_dir, name)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        print(f"Backed up agent folder: {model_dir} -> {backup_dir}")
    else:
        # Legacy flat layout (paths relative to repo root)
        files_to_backup = [
            (root / "models" / "ppo_temperature_control_final.zip", "ppo_temperature_control_final.zip"),
            (root / "models" / "best" / "best_model.zip", "best_model.zip"),
        ]
        for source_path, dest_name in files_to_backup:
            if source_path.exists():
                dest_path = os.path.join(backup_dir, dest_name)
                shutil.copy2(str(source_path), dest_path)
                print(f"✓ Backed up: {source_path} -> {dest_path}")
            else:
                print(f"✗ Not found: {source_path}")
        checkpoints_dir = root / "models" / "checkpoints"
        if checkpoints_dir.exists():
            checkpoints_backup = os.path.join(backup_dir, "checkpoints")
            if os.path.exists(checkpoints_backup):
                shutil.rmtree(checkpoints_backup)
            shutil.copytree(str(checkpoints_dir), checkpoints_backup)
            print(f"✓ Backed up checkpoints to {checkpoints_backup}")

    print(f"\nBackup complete: {backup_dir}")
    return backup_dir


if __name__ == "__main__":
    import sys

    backup_name = None
    model_dir = None
    args = sys.argv[1:]
    if args and not args[0].startswith("models/") and not (args[0].startswith("./") and "models" in args[0]):
        backup_name = args[0]
        if len(args) > 1:
            model_dir = args[1]
    elif args:
        model_dir = args[0]
        if len(args) > 1:
            backup_name = args[1]
    backup_models(backup_name=backup_name, model_dir=model_dir)

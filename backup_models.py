#!/usr/bin/env python3
"""
Backup script for trained models.
Backs up an agent folder (e.g. models/temperature-control-agent) or the legacy flat models/ layout.
"""
import os
import shutil
from datetime import datetime


def backup_models(backup_name=None, model_dir=None):
    """Backup an agent's model folder to models/backup_<name> or models/backup_<timestamp>.

    Args:
        backup_name: Name for the backup folder (e.g. "v1"). If None, uses timestamp.
        model_dir: Agent folder to back up (e.g. "models/temperature-control-agent").
                   If None, uses "models/temperature-control-agent" when it exists,
                   otherwise falls back to legacy paths under models/.
    """
    if model_dir is None:
        model_dir = "models/temperature-control-agent" if os.path.isdir("models/temperature-control-agent") else None

    if backup_name:
        backup_dir = f"./models/backup_{backup_name}"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = f"./models/backup_{timestamp}"

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
        # Legacy flat layout
        files_to_backup = [
            ("./models/ppo_temperature_control_final.zip", "ppo_temperature_control_final.zip"),
            ("./models/best/best_model.zip", "best_model.zip"),
        ]
        backed_up = []
        skipped = []
        for source_path, dest_name in files_to_backup:
            if os.path.exists(source_path):
                dest_path = os.path.join(backup_dir, dest_name)
                shutil.copy2(source_path, dest_path)
                backed_up.append(source_path)
                print(f"✓ Backed up: {source_path} -> {dest_path}")
            else:
                skipped.append(source_path)
                print(f"✗ Not found: {source_path}")
        checkpoints_dir = "./models/checkpoints"
        if os.path.exists(checkpoints_dir):
            checkpoints_backup = os.path.join(backup_dir, "checkpoints")
            if os.path.exists(checkpoints_backup):
                shutil.rmtree(checkpoints_backup)
            shutil.copytree(checkpoints_dir, checkpoints_backup)
            print(f"✓ Backed up checkpoints to {checkpoints_backup}")

    print(f"\nBackup complete: {backup_dir}")
    return backup_dir


if __name__ == "__main__":
    import sys

    backup_name = None
    model_dir = None
    args = sys.argv[1:]
    if args and not args[0].startswith("models/"):
        backup_name = args[0]
        if len(args) > 1:
            model_dir = args[1]
    elif args:
        model_dir = args[0]
        if len(args) > 1:
            backup_name = args[1]
    backup_models(backup_name=backup_name, model_dir=model_dir)

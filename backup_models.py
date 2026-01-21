#!/usr/bin/env python3
"""
Backup script for trained models.
Creates timestamped backups of final and best models.
"""
import os
import shutil
from datetime import datetime

def backup_models(backup_name=None):
    """Backup current models to a backup directory."""
    
    # Create backup directory name
    if backup_name:
        backup_dir = f"./models/backup_{backup_name}"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = f"./models/backup_{timestamp}"
    
    os.makedirs(backup_dir, exist_ok=True)
    
    # Files to backup
    files_to_backup = [
        ("./models/ppo_temperature_control_final.zip", "ppo_temperature_control_final.zip"),
        ("./models/best/best_model.zip", "best_model.zip"),
    ]
    
    backed_up = []
    skipped = []
    
    print(f"Backing up models to: {backup_dir}\n")
    
    for source_path, dest_name in files_to_backup:
        if os.path.exists(source_path):
            dest_path = os.path.join(backup_dir, dest_name)
            shutil.copy2(source_path, dest_path)
            backed_up.append(source_path)
            print(f"✓ Backed up: {source_path} -> {dest_path}")
        else:
            skipped.append(source_path)
            print(f"✗ Not found: {source_path}")
    
    # Also backup checkpoints if requested
    checkpoints_dir = "./models/checkpoints"
    if os.path.exists(checkpoints_dir):
        checkpoints_backup = os.path.join(backup_dir, "checkpoints")
        if os.path.exists(checkpoints_backup):
            shutil.rmtree(checkpoints_backup)
        shutil.copytree(checkpoints_dir, checkpoints_backup)
        checkpoint_count = len([f for f in os.listdir(checkpoints_dir) if f.endswith('.zip')])
        print(f"✓ Backed up {checkpoint_count} checkpoints to {checkpoints_backup}")
    
    print(f"\nBackup complete! Files saved to: {backup_dir}")
    print(f"Backed up {len(backed_up)} model file(s)")
    
    if skipped:
        print(f"Skipped {len(skipped)} file(s) (not found)")
    
    return backup_dir


if __name__ == "__main__":
    import sys
    
    backup_name = None
    if len(sys.argv) > 1:
        backup_name = sys.argv[1]
    
    backup_models(backup_name)

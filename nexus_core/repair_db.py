import sqlite3
import os
from pathlib import Path

db_path = Path("scanner.db")
repair_path = Path("scanner_repaired.db")
backup_path = Path("scanner_corrupted_backup.db")

if not db_path.exists():
    print("Database file not found.")
    exit(1)

print(f"Attempting to repair {db_path}...")

try:
    # Rename original suspicious file
    if backup_path.exists():
        os.remove(backup_path)
    os.rename(db_path, backup_path)
    
    # Try to recover using .dump via python sqlite3
    src = sqlite3.connect(backup_path)
    dst = sqlite3.connect(db_path)
    
    with dst:
        for line in src.iterdump():
            try:
                dst.execute(line)
            except sqlite3.Error:
                pass # Skip lines that cause error during recovery
    
    src.close()
    dst.close()
    print("Repair attempt finished. New scanner.db created from dump.")
except Exception as e:
    print(f"Failed to repair: {e}")
    # If fails, we might need to let initialize_database recreate it
    if backup_path.exists() and not db_path.exists():
         print("Restoring corrupted file as last resort...")
         os.rename(backup_path, db_path)

from nexus_core.models import Camera, initialize_database
try:
    initialize_database()
    print("Database initialized.")
    cols = Camera._meta.columns.keys()
    print(f"Columns: {cols}")
    if "parent_id" in cols:
        print("parent_id exists.")
    else:
        print("parent_id MISSING!")
except Exception as e:
    print(f"Error: {e}")

"""PocketSmart AI - Main Entry Point.
Exports app instance from app.py and runs uvicorn when executed directly.
"""
from app import app

if __name__ == "__main__":
    import uvicorn
    print("Starting PocketSmart: AI Budget Planner from main.py...")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

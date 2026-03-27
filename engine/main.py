"""Entry point for the Agent League backend.

Run with:
    python -m engine.main
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("engine.api.app:app", host="0.0.0.0", port=8000, reload=True)

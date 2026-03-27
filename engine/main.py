"""Entry point for the Agent League backend.

Local:   python -m engine.main
Railway: python -m engine.main  (with PORT env var)
"""

import os
import uvicorn


def main():
    port = int(os.environ.get("PORT", 8000))
    reload = os.environ.get("RAILWAY_ENVIRONMENT") is None
    uvicorn.run("engine.api.app:app", host="0.0.0.0", port=port, reload=reload)


if __name__ == "__main__":
    main()

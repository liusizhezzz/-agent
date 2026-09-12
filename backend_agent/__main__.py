import uvicorn

from .app import app
from .config import load_settings

if __name__ == "__main__":
    settings = load_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)

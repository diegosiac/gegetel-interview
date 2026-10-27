from pathlib import Path

from fastapi import FastAPI

from app import agent, benefits, lines
from app.db import init_db


def create_app(db_path: str | Path) -> FastAPI:
    # Initialize the database
    init_db(db_path)

    # Create the FastAPI app
    app = FastAPI(title="Gege Tel - Benefits API", version="0.1.0")

    # Store the database path in the app state
    app.state.db_path = str(db_path)

    # Routers
    app.include_router(lines.admin_router)
    app.include_router(lines.webhook_router)
    app.include_router(benefits.router)
    app.include_router(agent.router)

    return app

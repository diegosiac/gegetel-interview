import os

from app.factory import create_app

app = create_app(os.environ.get("GEGE_DB_PATH", "gege.db"))

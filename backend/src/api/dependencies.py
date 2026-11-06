"""FastAPI dependency providers.

Usage::

    from fastapi import Depends
    from src.api.dependencies import get_db

    @router.get("/example")
    def example(db: Database = Depends(get_db)):
        ...
"""

from fastapi import Request

from src.data.database import Database


def get_db(request: Request) -> Database:
    """Return the shared Database instance stored on app.state."""
    return request.app.state.db

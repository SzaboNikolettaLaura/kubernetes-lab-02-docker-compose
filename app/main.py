from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import Database


T = TypeVar("T")


class ItemCreate(BaseModel):
    name: str


class ItemResponse(BaseModel):
    id: int
    name: str


def get_database(request: Request) -> Database:
    return request.app.state.database


def _database_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="database unavailable")


def _database_call(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except Exception as error:
        raise _database_unavailable() from error


def create_app(database: Database | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active_database = (
            database if database is not None else Database.from_environment()
        )
        active_database.open()
        application.state.database = active_database
        try:
            yield
        finally:
            active_database.close()

    application = FastAPI(
        title="kubernetes-lab-api",
        version="1.0.0",
        lifespan=lifespan,
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/ready")
    def ready(database: Database = Depends(get_database)) -> dict[str, str]:
        _database_call(database.ping)
        return {"status": "ok"}

    @application.get("/")
    def root() -> dict[str, str]:
        return {"service": "kubernetes-lab-api", "docs": "/docs", "health": "/health"}

    @application.get("/hello")
    def hello(name: str = "world") -> dict[str, str]:
        return {"message": f"Hello, {name}!"}

    @application.get("/items", response_model=list[ItemResponse])
    def list_items(database: Database = Depends(get_database)) -> list[ItemResponse]:
        items = _database_call(database.list_items)
        return [ItemResponse(id=item_id, name=name) for item_id, name in items]

    @application.post("/items", response_model=ItemResponse, status_code=201)
    def create_item(
        payload: ItemCreate,
        database: Database = Depends(get_database),
    ) -> JSONResponse | ItemResponse:
        name = payload.name.strip()
        if not name:
            return JSONResponse(status_code=400, content={"error": "name is required"})
        item_id, stored_name = _database_call(lambda: database.create_item(name))
        return ItemResponse(id=item_id, name=stored_name)

    @application.get("/items/{item_id}", response_model=ItemResponse)
    def get_item(
        item_id: int,
        database: Database = Depends(get_database),
    ) -> JSONResponse | ItemResponse:
        item = _database_call(lambda: database.get_item(item_id))
        if item is None:
            return JSONResponse(status_code=404, content={"error": "not found"})
        stored_id, name = item
        return ItemResponse(id=stored_id, name=name)

    @application.delete("/items/{item_id}", status_code=204)
    def delete_item(
        item_id: int,
        database: Database = Depends(get_database),
    ) -> None:
        if not _database_call(lambda: database.delete_item(item_id)):
            raise HTTPException(status_code=404, detail="not found")
        return None

    return application


app = create_app()

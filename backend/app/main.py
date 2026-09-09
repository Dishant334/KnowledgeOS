from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from app.routers.auth import router as auth_router
from app.db.database import engine
from app.generation.memory import ensure_message_table


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    ensure_message_table()
    yield
    # shutdown (nothing to clean up yet — add teardown code here later
    # if needed, e.g. closing the psycopg connection in memory.py)


app = FastAPI(title="KnowledgeOS", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/test-db")
def test_db():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {"status": "connected"}

    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
        }


app.include_router(auth_router)
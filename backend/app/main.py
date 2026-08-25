from fastapi import FastAPI
from sqlalchemy import text
from app.routers.auth import router as auth_router


app=FastAPI(title="KnowledgeOS")


@app.get("/health")
async def health_check():
    return {"status": "ok"}

from app.db.database import engine

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

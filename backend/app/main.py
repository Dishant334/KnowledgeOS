from fastapi import FastAPI
app=FastAPI(title="KnowledgeOS")


@app.get("/health")
async def health_check():
    return {"status": "ok"}
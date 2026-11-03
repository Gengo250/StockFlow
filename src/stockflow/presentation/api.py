"""ASGI application for the StockFlow HTTP API."""

import os

from fastapi import FastAPI

from stockflow.presentation.routes.registers import router as registers_router

app = FastAPI(title="StockFlow API", version="0.1.0")
app.include_router(registers_router, prefix="/api/v1")


def run():
    import uvicorn

    uvicorn.run(
        "stockflow.presentation.api:app",
        host=os.environ.get("STOCKFLOW_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("STOCKFLOW_API_PORT", "8000")),
    )

from fastapi import FastAPI

from app.api.routes_chat import router as chat_router
from app.api.routes_health import router as health_router

app = FastAPI(title="Audience Match")
app.include_router(health_router)
app.include_router(chat_router)

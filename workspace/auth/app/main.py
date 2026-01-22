from fastapi import FastAPI
from app.routers import auth
from app.database import engine, Base
from tapper.service import Service


# @service.Service(name="auth-service", version="1.0.0", prefix="/auth")
def getApp() -> FastAPI:
    return FastAPI(title="FastAPI Auth Service")


app = Service(name="auth-service", 
              version="1.0.0", 
              prefix="/auth",
              url="http://localhost:8003")(getApp())

app.include_router(auth.router)


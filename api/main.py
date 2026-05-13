from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import leads, reunioes

app = FastAPI(
    title="EngSearch API",
    description="Robô de prospecção e agendamento para Neomot",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(leads.router)
app.include_router(reunioes.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "engsearch-api"}

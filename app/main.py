from fastapi import FastAPI

app = FastAPI(
    title="Database-Centric API",
    version="1.0.0"
)

@app.get("/")
def root():
    return {
        "message": "Backend funcionando correctamente"
    }

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }
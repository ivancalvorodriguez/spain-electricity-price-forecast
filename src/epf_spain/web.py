import os

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="spain-electricity-price-forecast")


# no consulta la base: Render la llama a menudo y despertaría a Neon en cada llamada
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    # Render fija el puerto en PORT; en local, 8000
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))

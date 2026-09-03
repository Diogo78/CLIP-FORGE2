"""
app.py

Backend do site CLIPE FORGE.
Serve a pagina (static/index.html) e expoe o endpoint que roda o
corte automatico de verdade (download + transcricao + corte +
reenquadramento vertical + legenda), chamando pipeline.py.

INSTALACAO (uma vez, no terminal):
    pip install fastapi uvicorn python-multipart yt-dlp faster-whisper opencv-python numpy
    precisa ter o ffmpeg instalado no sistema (ffmpeg.org)

USO:
    uvicorn app:app --reload
    depois abre http://localhost:8000 no navegador
"""

import os
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline import processar_video

CLIPES_DIR = "clipes"
os.makedirs(CLIPES_DIR, exist_ok=True)

app = FastAPI(title="CLIPE FORGE")
app.mount("/clipes", StaticFiles(directory=CLIPES_DIR), name="clipes")


class CortarRequest(BaseModel):
    url: str


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.post("/api/cortar")
def cortar(req: CortarRequest):
    """
    Recebe o link do YouTube, roda o pipeline completo (pode demorar
    alguns minutos dependendo do tamanho do video) e devolve os
    clipes gerados, ja com o caminho pra baixar cada um.
    """
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="envie um link valido")

    lote_id = uuid.uuid4().hex[:8]
    pasta_lote = os.path.join(CLIPES_DIR, lote_id)

    try:
        clipes = processar_video(req.url, pasta_lote)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"erro ao processar o video: {e}")

    for c in clipes:
        c["url_download"] = f"/clipes/{lote_id}/{c['arquivo']}"

    return {"lote_id": lote_id, "clipes": clipes}

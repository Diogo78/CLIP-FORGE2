"""
app.py

Backend do site CLIPE FORGE.
Serve a pagina (static/index.html) e expoe os endpoints do corte
automatico de verdade (download + transcricao + corte +
reenquadramento vertical + legenda), chamando pipeline.py.

O processamento roda em segundo plano (thread), porque pode levar
varios minutos -- se a gente esperasse tudo terminar numa unica
requisicao, servidores como a Railway derrubam a conexao por
timeout antes de terminar. Em vez disso: o site dispara o job,
recebe um id na hora, e fica perguntando "ja terminou?" de tempos
em tempos (polling).

INSTALACAO (uma vez, no terminal):
    pip install -r requirements.txt
    precisa ter o ffmpeg instalado no sistema (ffmpeg.org)

USO:
    uvicorn app:app --reload
    depois abre http://localhost:8000 no navegador
"""

import os
import threading
import traceback
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

# guarda o status de cada job em memoria: {job_id: {"status":..., "clipes":..., "erro":...}}
JOBS: dict[str, dict] = {}


class CortarRequest(BaseModel):
    url: str


@app.get("/")
def home():
    return FileResponse("static/index.html")


def _rodar_pipeline_em_segundo_plano(job_id: str, url: str):
    pasta_lote = os.path.join(CLIPES_DIR, job_id)
    try:
        clipes = processar_video(url, pasta_lote)
        for c in clipes:
            c["url_download"] = f"/clipes/{job_id}/{c['arquivo']}"
        JOBS[job_id] = {"status": "concluido", "clipes": clipes}
    except Exception:
        JOBS[job_id] = {"status": "erro", "erro": traceback.format_exc(limit=3)}


@app.post("/api/cortar")
def cortar(req: CortarRequest):
    """Dispara o processamento em segundo plano e devolve um job_id na hora."""
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="envie um link valido")

    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {"status": "processando"}

    thread = threading.Thread(
        target=_rodar_pipeline_em_segundo_plano,
        args=(job_id, req.url.strip()),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def status(job_id: str):
    """O front-end consulta esse endpoint a cada alguns segundos ate o job terminar."""
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job nao encontrado")
    return job

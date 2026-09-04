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
import shutil
import threading
import traceback
import uuid

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline import processar_video, processar_video_local

CLIPES_DIR = "clipes"
UPLOADS_DIR = "uploads"
os.makedirs(CLIPES_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

app = FastAPI(title="CLIPE FORGE")
app.mount("/clipes", StaticFiles(directory=CLIPES_DIR), name="clipes")

# guarda o status de cada job em memoria: {job_id: {"status":..., "clipes":..., "erro":...}}
JOBS: dict[str, dict] = {}

# no plano free (pouca RAM), rodar 2 jobs ao mesmo tempo derruba o
# container por falta de memoria -- esse lock garante que só um
# video seja processado por vez; os outros ficam esperando na fila
LOCK_PROCESSAMENTO = threading.Lock()


class CortarRequest(BaseModel):
    url: str
    com_legenda: bool = True


@app.get("/")
def home():
    return FileResponse("static/index.html")


def _rodar_pipeline_em_segundo_plano(job_id: str, url: str, com_legenda: bool):
    pasta_lote = os.path.join(CLIPES_DIR, job_id)
    if LOCK_PROCESSAMENTO.locked():
        JOBS[job_id] = {"status": "na_fila"}
    with LOCK_PROCESSAMENTO:
        JOBS[job_id] = {"status": "processando"}
        try:
            clipes = processar_video(url, pasta_lote, com_legenda)
            for c in clipes:
                c["url_download"] = f"/clipes/{job_id}/{c['arquivo']}"
            JOBS[job_id] = {"status": "concluido", "clipes": clipes}
        except Exception:
            JOBS[job_id] = {"status": "erro", "erro": traceback.format_exc(limit=3)}


def _rodar_pipeline_local_em_segundo_plano(job_id: str, video_path: str, com_legenda: bool):
    pasta_lote = os.path.join(CLIPES_DIR, job_id)
    if LOCK_PROCESSAMENTO.locked():
        JOBS[job_id] = {"status": "na_fila"}
    with LOCK_PROCESSAMENTO:
        JOBS[job_id] = {"status": "processando"}
        try:
            clipes = processar_video_local(video_path, pasta_lote, com_legenda)
            for c in clipes:
                c["url_download"] = f"/clipes/{job_id}/{c['arquivo']}"
            JOBS[job_id] = {"status": "concluido", "clipes": clipes}
        except Exception:
            JOBS[job_id] = {"status": "erro", "erro": traceback.format_exc(limit=3)}
        finally:
            # limpa o arquivo enviado depois de processar
            try:
                os.remove(video_path)
            except OSError:
                pass


@app.post("/api/cortar")
def cortar(req: CortarRequest):
    """Dispara o processamento em segundo plano a partir de um link e devolve um job_id na hora."""
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="envie um link valido")

    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {"status": "processando"}

    thread = threading.Thread(
        target=_rodar_pipeline_em_segundo_plano,
        args=(job_id, req.url.strip(), req.com_legenda),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id}


@app.post("/api/cortar-upload")
async def cortar_upload(arquivo: UploadFile = File(...), com_legenda: bool = Form(True)):
    """Dispara o processamento em segundo plano a partir de um arquivo de video enviado direto."""
    extensoes_validas = (".mp4", ".mov", ".mkv", ".avi", ".webm")
    if not arquivo.filename.lower().endswith(extensoes_validas):
        raise HTTPException(status_code=400, detail="formato de arquivo nao suportado")

    job_id = uuid.uuid4().hex[:8]
    caminho_upload = os.path.join(UPLOADS_DIR, f"{job_id}_{arquivo.filename}")

    with open(caminho_upload, "wb") as f:
        shutil.copyfileobj(arquivo.file, f)

    JOBS[job_id] = {"status": "processando"}

    thread = threading.Thread(
        target=_rodar_pipeline_local_em_segundo_plano,
        args=(job_id, caminho_upload, com_legenda),
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

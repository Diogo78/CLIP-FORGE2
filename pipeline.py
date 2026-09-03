"""
pipeline.py

Mesma logica do clip_cutter_pro.py, organizada em funcoes pra ser
chamada pelo backend do site (app.py) em vez de rodar por linha de comando.
"""

import os
import subprocess

import numpy as np

try:
    import cv2
    from faster_whisper import WhisperModel
except ImportError as e:
    raise ImportError(
        "Falta instalar dependencias. Rode:\n"
        "  pip install yt-dlp faster-whisper opencv-python numpy fastapi uvicorn python-multipart"
    ) from e


CLIP_MIN_SEC = 45
CLIP_MAX_SEC = 60
TOP_N_CLIPES = 6
WORK_DIR = "_temp_clipcutter_pro"

PALAVRAS_GATILHO = [
    "nao acredito", "não acredito", "meu deus", "caraca", "cara",
    "insano", "absurdo", "que isso", "eu nao consigo", "eu não consigo",
    "olha isso", "gente", "socorro", "mds", "kkkk", "haha",
]

_modelo_whisper = None


def _get_modelo():
    global _modelo_whisper
    if _modelo_whisper is None:
        _modelo_whisper = WhisperModel("small", device="cpu", compute_type="int8")
    return _modelo_whisper


def baixar_video(url: str) -> str:
    os.makedirs(WORK_DIR, exist_ok=True)
    saida = os.path.join(WORK_DIR, "video.mp4")
    comando = [
        "yt-dlp",
        "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "--merge-output-format", "mp4",
        "-o", saida,
    ]
    if os.path.exists("cookies.txt"):
        comando += ["--cookies", "cookies.txt"]
    comando.append(url)

    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"yt-dlp falhou: {resultado.stderr[-1500:]}")
    return saida


def transcrever(video_path: str):
    modelo = _get_modelo()
    segmentos, _ = modelo.transcribe(video_path, language="pt", vad_filter=True, word_timestamps=True)
    resultado = []
    for s in segmentos:
        palavras = [{"start": w.start, "end": w.end, "word": w.word} for w in (s.words or [])]
        resultado.append({"start": s.start, "end": s.end, "text": s.text.strip(), "words": palavras})
    return resultado


def pontuar_trecho(texto: str) -> float:
    t = texto.lower()
    score = 0.0
    score += t.count("!") * 2
    score += t.count("?") * 1
    for gatilho in PALAVRAS_GATILHO:
        if gatilho in t:
            score += 3
    maiusculas = sum(1 for c in texto if c.isupper())
    score += min(maiusculas / max(len(texto), 1) * 10, 3)
    return score


def selecionar_janelas(segmentos):
    candidatas = []
    i = 0
    while i < len(segmentos):
        inicio = segmentos[i]["start"]
        j = i
        textos, scores = [], []
        while j < len(segmentos) and segmentos[j]["end"] - inicio < CLIP_MAX_SEC:
            textos.append(segmentos[j]["text"])
            scores.append(pontuar_trecho(segmentos[j]["text"]))
            j += 1
        fim = segmentos[j - 1]["end"] if j > i else inicio + CLIP_MIN_SEC
        if fim - inicio >= CLIP_MIN_SEC:
            candidatas.append({
                "start": inicio, "end": fim,
                "score": sum(scores) / max(len(scores), 1),
                "texto": " ".join(textos),
                "segmentos": segmentos[i:j],
            })
        i += 1

    candidatas.sort(key=lambda c: c["score"], reverse=True)

    escolhidas = []
    for c in candidatas:
        if any(not (c["end"] <= e["start"] or c["start"] >= e["end"]) for e in escolhidas):
            continue
        escolhidas.append(c)
        if len(escolhidas) >= TOP_N_CLIPES:
            break

    escolhidas.sort(key=lambda c: c["start"])
    return escolhidas


def detectar_centro_rosto(video_path: str, inicio: float, fim: float) -> float:
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    largura = cap.get(cv2.CAP_PROP_FRAME_WIDTH)

    centros = []
    for t in np.linspace(inicio, fim, 5):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ok, frame = cap.read()
        if not ok:
            continue
        cinza = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rostos = cascade.detectMultiScale(cinza, 1.1, 5)
        if len(rostos):
            x, y, w, h = max(rostos, key=lambda r: r[2] * r[3])
            centros.append((x + w / 2) / largura)
    cap.release()
    return float(np.mean(centros)) if centros else 0.5


COR_DESTAQUE_ASS = "&H3DDC84&"   # verde da marca, formato BGR do ASS
COR_BASE_ASS = "&HFFFFFF&"       # branco


def _formatar_tempo_ass(t: float) -> str:
    t = max(0, t)
    h, resto = divmod(t, 3600)
    m, s = divmod(resto, 60)
    cs = round((s - int(s)) * 100)
    return f"{int(h)}:{int(m):02d}:{int(s):02d}.{cs:02d}"


def gerar_ass_estilo_realoficial(segmentos_janela, inicio_janela: float, caminho: str, palavras_por_linha: int = 4):
    """
    Gera legenda no estilo usado pela Real Oficial: poucas palavras
    grandes na tela por vez, em caixa alta, com a palavra sendo
    falada destacada em verde enquanto as outras ficam brancas.
    """
    cabecalho = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Arial Black,78,{COR_BASE_ASS},{COR_BASE_ASS},&H00000000&,&H00000000&,"
        "-1,0,0,0,100,100,0,0,1,6,0,2,60,60,220,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    todas_palavras = []
    for seg in segmentos_janela:
        todas_palavras.extend(seg.get("words", []))

    linhas_eventos = []
    for i in range(0, len(todas_palavras), palavras_por_linha):
        bloco = todas_palavras[i:i + palavras_por_linha]
        if not bloco:
            continue
        for idx, palavra_ativa in enumerate(bloco):
            partes = []
            for j, w in enumerate(bloco):
                texto_palavra = w["word"].strip().upper()
                if j == idx:
                    partes.append("{\\c" + COR_DESTAQUE_ASS + "}" + texto_palavra + "{\\c" + COR_BASE_ASS + "}")
                else:
                    partes.append(texto_palavra)
            texto_linha = " ".join(partes)

            inicio_evento = palavra_ativa["start"] - inicio_janela
            fim_evento = palavra_ativa["end"] - inicio_janela
            linhas_eventos.append(
                f"Dialogue: 0,{_formatar_tempo_ass(inicio_evento)},{_formatar_tempo_ass(fim_evento)},"
                f"Default,,0,0,0,,{texto_linha}\n"
            )

    with open(caminho, "w", encoding="utf-8") as f:
        f.write(cabecalho)
        f.writelines(linhas_eventos)


def cortar_reenquadrar_legendar(video_path: str, janela: dict, indice: int, pasta_saida: str) -> str:
    inicio, fim = janela["start"], janela["end"]
    duracao = fim - inicio
    centro_x = detectar_centro_rosto(video_path, inicio, fim)

    ass_path = os.path.join(WORK_DIR, f"legenda_{indice:02d}.ass")
    gerar_ass_estilo_realoficial(janela["segmentos"], inicio, ass_path)

    nome_arquivo = f"clipe_{indice:02d}.mp4"
    saida = os.path.join(pasta_saida, nome_arquivo)

    crop_filter = (
        f"crop=ih*9/16:ih:(iw-ih*9/16)*{centro_x}:0,"
        f"scale=1080:1920,"
        f"ass={ass_path}"
    )

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(inicio),
            "-i", video_path,
            "-t", str(duracao),
            "-vf", crop_filter,
            "-c:v", "libx264", "-c:a", "aac",
            saida,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return nome_arquivo


def processar_video(url: str, pasta_saida: str) -> list[dict]:
    """
    Funcao principal chamada pelo backend do site.
    Retorna uma lista de dicts com info de cada clipe gerado.
    """
    os.makedirs(pasta_saida, exist_ok=True)

    video_path = baixar_video(url)
    segmentos = transcrever(video_path)
    janelas = selecionar_janelas(segmentos)

    resultado = []
    for i, janela in enumerate(janelas, start=1):
        nome_arquivo = cortar_reenquadrar_legendar(video_path, janela, i, pasta_saida)
        resultado.append({
            "arquivo": nome_arquivo,
            "inicio": round(janela["start"], 1),
            "fim": round(janela["end"], 1),
            "score": round(janela["score"], 1),
            "trecho_falado": janela["texto"][:140],
        })
    return resultado

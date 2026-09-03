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
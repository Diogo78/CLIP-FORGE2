# CLIPE FORGE — site com corte automático real

Este é o site com o corte automático de verdade embutido (não é mais
simulado): quando você cola um link do YouTube na tela "cortar vídeo
longo" e clica em "detectar cortes", o backend baixa o vídeo,
transcreve, escolhe os melhores momentos, corta, reenquadra pra
vertical seguindo o rosto e queima a legenda — igual ao fluxo do
Opus Clip / RealOficial.

A tela de "análise de clipes" (Tela 1) ainda está com hooks/CTA
simulados por heurística local, não foi conectada a uma IA real
ainda.

## Como rodar

1. Instale o [ffmpeg](https://ffmpeg.org/download.html) no seu
   sistema (precisa estar disponível no terminal, comando `ffmpeg`).

2. Instale as dependências Python:
   ```
   pip install -r requirements.txt
   ```

3. Rode o servidor:
   ```
   uvicorn app:app --reload
   ```

4. Abra `http://localhost:8000` no navegador.

## O que esperar

- A primeira vez que você cortar um vídeo, o modelo de transcrição
  (`faster-whisper`) vai ser baixado — pode demorar um pouco.
- Vídeos longos demoram alguns minutos pra processar (download +
  transcrição + corte de cada clipe). É processamento pesado, então
  rodar isso localmente no seu PC é mais lento do que em um servidor
  com GPU (que é o que plataformas como Opus Clip usam).
- Os clipes ficam salvos em `clipes/<lote_id>/` e também ficam
  disponíveis pra baixar direto pela tela do site.

## Próximos passos possíveis

- Conectar a Tela 1 (análise de clipes já prontos) numa API de IA de
  verdade, no lugar da heurística local.
- Trocar o score de heurística por um modelo próprio, treinado com o
  histórico de views dos seus clipes já postados.

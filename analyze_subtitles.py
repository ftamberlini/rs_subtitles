import csv
import re
from pathlib import Path


def contar_dialogos_srt(caminho):
    try:
        texto = Path(caminho).read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return None
    return len(re.findall(r"-->", texto))


def parsear_log(caminho_log="legendas.log"):
    entradas = {}
    with open(caminho_log, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            partes = linha.split("|")
            imdb_id = partes[0]
            campos = {}
            for parte in partes[1:]:
                if ":" in parte:
                    chave, *resto = parte.split(":")
                    campos[chave] = ":".join(resto)
            entradas[imdb_id] = campos  # última ocorrência sobrescreve
    return entradas


def extrair_contagem(valor):
    try:
        return int(valor)
    except (ValueError, TypeError):
        return 0


log = parsear_log()

linhas = []
for imdb_id, campos in log.items():
    count_en_log = extrair_contagem(campos.get("SUBTITLE_EN", "0"))
    count_pt_log = extrair_contagem(campos.get("SUBTITLE_PTBR", campos.get("SUBTITLE_PB", "0")))

    if count_en_log == 0 or count_pt_log == 0:
        continue

    srt_en = Path("subtitle") / f"{imdb_id}_EN.srt"
    srt_pt = Path("subtitle") / f"{imdb_id}_PTBR.srt"

    dialogos_en = contar_dialogos_srt(srt_en)
    dialogos_pt = contar_dialogos_srt(srt_pt)

    if dialogos_en is None or dialogos_pt is None:
        continue

    diferenca = abs(dialogos_en - dialogos_pt)
    ratio = round(max(dialogos_en, dialogos_pt) / max(min(dialogos_en, dialogos_pt), 1), 2)

    linhas.append({
        "imdb_id": imdb_id,
        "api_count_en": count_en_log,
        "api_count_ptbr": count_pt_log,
        "dialogos_en": dialogos_en,
        "dialogos_ptbr": dialogos_pt,
        "diferenca": diferenca,
        "ratio": ratio,
    })

linhas.sort(key=lambda x: x["ratio"], reverse=True)

saida = Path("subtitle_analysis.csv")
with saida.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["imdb_id", "api_count_en", "api_count_ptbr", "dialogos_en", "dialogos_ptbr", "diferenca", "ratio"])
    writer.writeheader()
    writer.writerows(linhas)

print(f"Filmes com ambas legendas: {len(linhas)}")
print(f"Resultado salvo em: {saida}")
print()

grandes_diferencas = [l for l in linhas if l["ratio"] >= 2.0]
print(f"Filmes com ratio >= 2x (dialogos muito diferentes): {len(grandes_diferencas)}")
print()
print(f"{'IMDB ID':<12} {'API_EN':>6} {'API_PT':>6} {'SRT_EN':>7} {'SRT_PT':>7} {'DIFF':>6} {'RATIO':>6}")
print("-" * 55)
for l in linhas[:20]:
    print(f"{l['imdb_id']:<12} {l['api_count_en']:>6} {l['api_count_ptbr']:>6} {l['dialogos_en']:>7} {l['dialogos_ptbr']:>7} {l['diferenca']:>6} {l['ratio']:>6}")

import csv
import re
import requests
import os
from pathlib import Path


def carregar_env(caminho=".env"):
    caminho_env = Path(caminho)
    if not caminho_env.is_file():
        return
    with caminho_env.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            chave = chave.strip()
            valor = valor.strip().strip('"').strip("'")
            if chave and chave not in os.environ:
                os.environ[chave] = valor


carregar_env()

API_KEY = os.getenv("API_KEY", "SUA_API_KEY_AQUI")
JWT_TOKEN = os.getenv("JWT_TOKEN", "")
USER_AGENT = os.getenv("USER_AGENT", "MeuDownloaderLegendas v1.0")

PASTA_DESTINO = Path("subtitle_reprocess")
IDIOMAS = ["en", "pt-BR"]
IDIOMAS_MAP = {"en": "EN", "pt-BR": "PTBR", "pt": "PT"}


def contar_dialogos(texto):
    return len(re.findall(r"-->", texto))


def obter_link_download(file_id, headers):
    download_headers = {**headers}
    if JWT_TOKEN:
        download_headers["Authorization"] = f"Bearer {JWT_TOKEN}"
    r = requests.post(
        "https://api.opensubtitles.com/api/v1/download",
        headers=download_headers,
        json={"file_id": file_id},
    )
    r.raise_for_status()
    data = r.json()
    return data["link"], data.get("remaining")


def pontuar_legenda(atributos):
    pontos = 0
    if atributos.get("from_trusted"):
        pontos += 1000
    if not atributos.get("ai_translated") and not atributos.get("machine_translated"):
        pontos += 500
    pontos += (atributos.get("ratings") or 0) * 100
    pontos += (atributos.get("votes") or 0) * 10
    pontos += (atributos.get("download_count") or 0)
    return pontos


def buscar_melhor_legenda(imdb_id, idioma, headers):
    """
    Seleciona o melhor candidato por qualidade (sem baixar todos) e faz um único download.

    Returns:
        tuple: (nome_arquivo, dialogos, total_disponiveis, remaining, erro)
    """
    imdb_clean = imdb_id.replace("tt", "")
    extensao = IDIOMAS_MAP.get(idioma, idioma.upper())
    nome_arquivo = PASTA_DESTINO / f"{imdb_id}_{extensao}.srt"

    url = "https://api.opensubtitles.com/api/v1/subtitles"
    params = {"imdb_id": imdb_clean, "languages": idioma}

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        resultados = response.json().get("data", [])
        total = len(resultados)

        if total == 0:
            print(f"  [{idioma}] Nenhuma legenda encontrada")
            return None, 0, 0, None, None

        melhor = max(resultados, key=lambda r: pontuar_legenda(r["attributes"]))
        atributos = melhor["attributes"]
        file_id = atributos["files"][0]["file_id"]
        release = atributos.get("release", "?")
        score = pontuar_legenda(atributos)

        print(f"  [{idioma}] {total} disponíveis → melhor: {release[:60]} (score={score})")

        link, remaining = obter_link_download(file_id, headers)
        conteudo = requests.get(link).content
        texto = conteudo.decode("utf-8", errors="ignore")
        dialogos = contar_dialogos(texto)

        with open(nome_arquivo, "wb") as f:
            f.write(conteudo)

        print(f"  ✓ Salvo: {nome_arquivo} ({dialogos} diálogos, restante: {remaining})")
        return nome_arquivo, dialogos, total, remaining, None

    except requests.exceptions.RequestException as e:
        msg = str(e)
        print(f"  [{idioma}] Erro na requisição: {msg}")
        return None, 0, 0, None, msg
    except KeyError as e:
        msg = f"Chave não encontrada: {e}"
        print(f"  [{idioma}] Erro: {msg}")
        return None, 0, 0, None, msg


def escrever_log(imdb_id, resultados, caminho_log="reprocess.log"):
    partes = [imdb_id]
    for idioma, (dialogos, total_api, erro) in resultados.items():
        chave = IDIOMAS_MAP.get(idioma, idioma.upper())
        if erro:
            partes.append(f"SUBTITLE_{chave}:ERROR:{erro}")
        else:
            partes.append(f"SUBTITLE_{chave}:{dialogos}:{total_api}")

    linha = "|".join(partes) + "\n"
    with open(caminho_log, "a", encoding="utf-8") as f:
        f.write(linha)
    print(f"Log: {linha.strip()}")


def carregar_imdbs_do_csv(caminho):
    caminho_csv = Path(caminho)
    if not caminho_csv.is_file():
        print(f"Arquivo não encontrado: {caminho_csv}")
        return []

    delimitador = "\t" if caminho_csv.suffix == ".tsv" else ","

    with caminho_csv.open(encoding="utf-8", newline="") as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=delimitador)
        campos_lower = [c.strip().lower() for c in (leitor.fieldnames or [])]
        coluna_imdb = next(
            (leitor.fieldnames[i] for i, c in enumerate(campos_lower) if c in ("imdb_id", "imdbid")),
            None,
        )
        if coluna_imdb:
            return [linha[coluna_imdb].strip() for linha in leitor if linha.get(coluna_imdb)]

        arquivo.seek(0)
        leitor = csv.reader(arquivo, delimiter=delimitador)
        next(leitor, None)
        return [linha[0].strip() for linha in leitor if linha]


def carregar_processados(caminho_log="reprocess.log"):
    processados = set()
    caminho = Path(caminho_log)
    if not caminho.is_file():
        return processados
    with caminho.open(encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha:
                processados.add(linha.split("|")[0])
    return processados


if __name__ == "__main__":
    PASTA_DESTINO.mkdir(exist_ok=True)

    headers = {
        "Api-Key": API_KEY,
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
    }

    imdb_ids = carregar_imdbs_do_csv("data/reprocess_imdb.csv")
    processados = carregar_processados()
    pendentes = [i for i in imdb_ids if i not in processados]

    print(f"Total: {len(imdb_ids)} | Já processados: {len(processados)} | Pendentes: {len(pendentes)}")

    if not pendentes:
        print("Nenhum filme pendente.")
    else:
        for imdb_id in pendentes:
            print(f"\nProcessando: {imdb_id}")
            resultados = {}
            remaining = None

            for idioma in IDIOMAS:
                _, dialogos, total_api, rem, erro = buscar_melhor_legenda(imdb_id, idioma, headers)
                resultados[idioma] = (dialogos, total_api, erro)
                if rem is not None:
                    remaining = rem
                if remaining == 0:
                    break

            escrever_log(imdb_id, resultados)

            if remaining == 0:
                print("\nCota diária esgotada. Execute novamente amanhã.")
                break

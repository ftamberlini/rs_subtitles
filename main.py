import argparse
import csv
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


# Carrega variáveis do arquivo .env, se existir
carregar_env()

# Configurações
API_KEY = os.getenv("API_KEY", "SUA_API_KEY_AQUI")
JWT_TOKEN = os.getenv("JWT_TOKEN", "")
USER_AGENT = os.getenv("USER_AGENT", "MeuDownloaderLegendas v1.0")


def buscar_legenda_por_imdb(imdb_id, idioma):
    """
    Busca e baixa legenda pelo código IMDB.

    Returns:
        tuple: (nome_arquivo_ou_None, contagem_encontrada, mensagem_erro_ou_None, remaining_ou_None)
    """

    imdb_clean = imdb_id.replace('tt', '')

    idiomas_map = {
        'en': 'EN',
        'pt-BR': 'PTBR',
        'pt': 'PT'
    }

    extensao_idioma = idiomas_map.get(idioma, idioma.upper())
    nome_arquivo = Path("subtitle") / f"{imdb_id}_{extensao_idioma}.srt"

    headers = {
        'Api-Key': API_KEY,
        'User-Agent': USER_AGENT,
        'Content-Type': 'application/json'
    }

    url = "https://api.opensubtitles.com/api/v1/subtitles"
    params = {
        'imdb_id': imdb_clean,
        'languages': idioma
    }

    try:
        print(f"Buscando legendas para IMDB: {imdb_id} no idioma: {idioma}")

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        contagem = len(data.get('data', []))

        if contagem == 0:
            print(f"Nenhuma legenda encontrada para {imdb_id} no idioma {idioma}")
            return None, 0, None, None

        legenda = data['data'][0]
        file_id = legenda['attributes']['files'][0]['file_id']

        print(f"Legenda encontrada: {legenda['attributes']['release']}")
        print(f"Obtendo link de download...")

        download_headers = {**headers}
        if JWT_TOKEN:
            download_headers['Authorization'] = f'Bearer {JWT_TOKEN}'

        link_response = requests.post(
            "https://api.opensubtitles.com/api/v1/download",
            headers=download_headers,
            json={"file_id": file_id}
        )
        link_response.raise_for_status()
        link_data = link_response.json()
        download_url = link_data['link']
        remaining = link_data.get('remaining')

        print(f"Fazendo download... (cota restante: {remaining})")

        download_response = requests.get(download_url)
        download_response.raise_for_status()

        with open(nome_arquivo, 'wb') as f:
            f.write(download_response.content)

        print(f"✓ Legenda salva como: {nome_arquivo}")
        return nome_arquivo, contagem, None, remaining

    except requests.exceptions.RequestException as e:
        msg = str(e)
        print(f"Erro na requisição: {msg}")
        return None, 0, msg, None
    except KeyError as e:
        msg = f"Chave não encontrada na resposta da API: {e}"
        print(f"Erro ao processar resposta da API: {e}")
        return None, 0, msg, None


def buscar_legendas_multiplos_idiomas(imdb_id, idiomas=['en', 'pt-BR']):
    """
    Busca legendas em múltiplos idiomas para o mesmo IMDB ID.

    Returns:
        tuple: (lista_arquivos, dict{idioma: (contagem, erro)}, remaining_ou_None)
    """
    arquivos = []
    resultados = {}
    remaining = None
    for idioma in idiomas:
        print("-" * 50)
        arquivo, contagem, erro, rem = buscar_legenda_por_imdb(imdb_id, idioma)
        resultados[idioma] = (contagem, erro)
        if arquivo:
            arquivos.append(arquivo)
        if rem is not None:
            remaining = rem
        if remaining == 0:
            break
    return arquivos, resultados, remaining


def escrever_log(imdb_id, resultados_por_idioma, caminho_log="legendas.log"):
    mapa_idioma = {'en': 'EN', 'pt-BR': 'PTBR', 'pt': 'PT'}

    partes = [imdb_id]
    for idioma, (contagem, erro) in resultados_por_idioma.items():
        chave = mapa_idioma.get(idioma, idioma.upper())
        if erro:
            partes.append(f"SUBTITLE_{chave}:ERROR:{erro}")
        else:
            partes.append(f"SUBTITLE_{chave}:{contagem}")

    linha = "|".join(partes) + "\n"

    with open(caminho_log, "a", encoding="utf-8") as f:
        f.write(linha)

    print(f"Log: {linha.strip()}")


def carregar_imdbs_do_csv(caminho="data/movie_imdb.tsv"):
    caminho_csv = Path(caminho)
    if not caminho_csv.is_file():
        print(f"Arquivo não encontrado: {caminho_csv}")
        return []

    delimitador = "\t" if caminho_csv.suffix == ".tsv" else ","

    with caminho_csv.open(encoding="utf-8", newline="") as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=delimitador)
        campos_lower = [c.strip().lower() for c in (leitor.fieldnames or [])]
        coluna_imdb = next((leitor.fieldnames[i] for i, c in enumerate(campos_lower) if c in ("imdb_id", "imdbid")), None)
        if coluna_imdb:
            return [linha[coluna_imdb].strip() for linha in leitor if linha.get(coluna_imdb)]

        arquivo.seek(0)
        leitor = csv.reader(arquivo, delimiter=delimitador)
        next(leitor, None)  # pula cabeçalho
        return [linha[0].strip() for linha in leitor if linha]


def carregar_imdbs_processados(caminho_log="legendas.log"):
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
    parser = argparse.ArgumentParser()
    parser.add_argument("inicio", type=int, nargs="?", default=None, help="Linha inicial (1 = primeiro filme após o cabeçalho)")
    parser.add_argument("fim", type=int, nargs="?", default=None, help="Linha final (inclusive)")
    args = parser.parse_args()

    imdb_ids = carregar_imdbs_do_csv()

    if args.inicio is not None and args.fim is not None:
        imdb_ids = imdb_ids[args.inicio - 1:args.fim]

    processados = carregar_imdbs_processados()
    pendentes = [i for i in imdb_ids if i not in processados]

    total = len(imdb_ids)
    pulados = len(imdb_ids) - len(pendentes)
    print(f"Total: {total} | Já processados: {pulados} | Pendentes: {len(pendentes)}")

    if not pendentes:
        print("Nenhum filme pendente.")
    else:
        for imdb_id in pendentes:
            print(f"\nProcessando filme IMDB: {imdb_id}")
            _, resultados, remaining = buscar_legendas_multiplos_idiomas(imdb_id, ['en', 'pt-BR'])
            escrever_log(imdb_id, resultados)

            if remaining == 0:
                print("\nCota diária esgotada. Execute novamente amanhã.")
                break

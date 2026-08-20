"""
Coleta itens brutos via Google News RSS para cada consulta em config.json
(cada consulta pode ter idioma/país próprios, para cobrir fontes de
outros países). Acumula em data/bruto.csv, sem duplicar por URL, e
descarta itens com mais de JANELA_DIAS para não deixar o arquivo
crescer para sempre.
"""

import csv
import hashlib
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

CONFIG_PATH = "config.json"
CSV_PATH = "data/bruto.csv"
JANELA_DIAS = 45
CAMPOS = ["id", "titulo", "resumo", "link", "fonte", "publicado_em", "termo_busca", "coletado_em"]


def carregar_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def buscar_rss(termo, hl, gl):
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(termo)
        + f"&hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}"
    )
    requisicao = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(requisicao, timeout=20) as resposta:
        return resposta.read()


def limpar_html(texto):
    # descrições do Google News RSS vêm com marcação HTML simples
    import re
    return re.sub(r"<[^>]+>", " ", texto or "").strip()


def parsear_itens(xml_bytes, termo):
    raiz = ET.fromstring(xml_bytes)
    itens = []
    for item in raiz.findall(".//item"):
        titulo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        resumo = limpar_html(item.findtext("description") or "")
        fonte_el = item.find("source")
        fonte = fonte_el.text.strip() if fonte_el is not None and fonte_el.text else ""
        itens.append({
            "titulo": titulo,
            "resumo": resumo,
            "link": link,
            "fonte": fonte,
            "publicado_em": pub,
            "termo_busca": termo,
        })
    return itens


def gerar_id(link):
    return hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]


def carregar_existentes():
    if not os.path.exists(CSV_PATH):
        return {}
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        leitor = csv.DictReader(f)
        return {linha["id"]: {c: linha.get(c, "") for c in CAMPOS} for linha in leitor}


def data_valida(publicado_em, limite):
    try:
        data = parsedate_to_datetime(publicado_em)
        if data.tzinfo is None:
            data = data.replace(tzinfo=timezone.utc)
        return data >= limite
    except Exception:
        return True  # se não conseguir parsear, mantém — melhor pecar por excesso


def main():
    config = carregar_config()
    existentes = carregar_existentes()
    limite = datetime.now(timezone.utc) - timedelta(days=JANELA_DIAS)
    novos = 0

    for consulta in config["consultas"]:
        termo = consulta["termo"]
        hl = consulta.get("hl", "en-US")
        gl = consulta.get("gl", "US")
        try:
            xml_bytes = buscar_rss(termo, hl, gl)
        except Exception as exc:
            print(f"falha ao buscar '{termo}' ({hl}/{gl}): {exc}")
            continue

        for item in parsear_itens(xml_bytes, termo):
            if not item["link"]:
                continue
            id_item = gerar_id(item["link"])
            if id_item in existentes:
                continue
            linha = {
                "id": id_item,
                "titulo": item["titulo"],
                "resumo": item["resumo"],
                "link": item["link"],
                "fonte": item["fonte"],
                "publicado_em": item["publicado_em"],
                "termo_busca": item["termo_busca"],
                "coletado_em": datetime.now(timezone.utc).isoformat(),
            }
            existentes[id_item] = linha
            novos += 1

    # remove itens muito antigos para não crescer para sempre
    filtrados = {
        id_item: linha for id_item, linha in existentes.items()
        if data_valida(linha["publicado_em"], limite)
    }

    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=CAMPOS)
        escritor.writeheader()
        for linha in filtrados.values():
            escritor.writerow(linha)

    print(f"{novos} itens novos coletados. total após limpeza: {len(filtrados)}")


if __name__ == "__main__":
    main()

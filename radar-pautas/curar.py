"""
Lê data/bruto.csv, separa os itens ainda não avaliados (controlado por
data/processados.json), manda esse lote de uma vez só para a API da
Claude — que aplica os critérios de noticiabilidade do config.json,
escolhe os melhores itens e já redige, em português, o gancho de pauta
para cada um. Grava o resultado em data/ganchos.csv e devolve, via
stdout em JSON, só os itens novos de hoje (para o script de e-mail
consumir).
"""

import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

CONFIG_PATH = "config.json"
BRUTO_PATH = "data/bruto.csv"
GANCHOS_PATH = "data/ganchos.csv"
PROCESSADOS_PATH = "data/processados.json"

CAMPOS_GANCHOS = [
    "id", "data_curadoria", "titulo_original", "titulo_pt", "fonte", "link",
    "resumo", "porque_curioso", "gancho_pauta", "pontuacao",
]

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


def carregar_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def carregar_csv(caminho, campos):
    if not os.path.exists(caminho):
        return []
    with open(caminho, encoding="utf-8", newline="") as f:
        return [linha for linha in csv.DictReader(f)]


def carregar_processados():
    if not os.path.exists(PROCESSADOS_PATH):
        return set()
    with open(PROCESSADOS_PATH, encoding="utf-8") as f:
        return set(json.load(f))


def salvar_processados(ids):
    os.makedirs(os.path.dirname(PROCESSADOS_PATH), exist_ok=True)
    with open(PROCESSADOS_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, ensure_ascii=False, indent=0)


def montar_prompt(config, itens):
    perfil = config["perfil_fonte"]
    criterios = "\n".join(f"- {c}" for c in config["criterios_noticiabilidade"])
    temas = "\n".join(f"- {t}" for t in perfil["temas_que_pode_comentar"])
    experiencia = "\n".join(f"- {e}" for e in perfil["experiencia_relevante"])

    lista_itens = "\n\n".join(
        f"[{i}] título: {item['titulo']}\nresumo: {item['resumo']}\nfonte: {item['fonte']}"
        for i, item in enumerate(itens)
    )

    instrucao = f"""Você é assessor de imprensa e está triando notícias e achados internacionais para sugerir pautas de entrevista a jornalistas brasileiros.

FONTE A SER OFERECIDA:
Nome: {perfil['nome']} ({perfil['forma_de_tratamento']})
Cargo: {perfil['cargo']}
Formação: {perfil['formacao']}
Linha de pesquisa: {perfil['linha_de_pesquisa']}

Experiência relevante com imprensa e formação:
{experiencia}

Temas que pode comentar com autoridade:
{temas}

CRITÉRIOS DE NOTICIABILIDADE (um item só deve ser escolhido se atender bem a pelo menos três destes):
{criterios}

Abaixo está uma lista numerada de itens brutos coletados de fontes internacionais. Avalie cada um e escolha no máximo {config['max_itens_por_dia']} que atendam aos critérios, com pontuação de 0 a 10. Só inclua itens com pontuação maior ou igual a {config['limiar_pontuacao']}. Se nenhum item atingir esse nível, devolva uma lista vazia — não force a barra.

Para cada item escolhido, escreva:
- titulo_pt: título em português, direto, sem sensacionalismo
- resumo: 2 a 3 frases explicando o fato, em português
- porque_curioso: 1 a 2 frases explicando por que esse fato é noticiável e curioso para o público brasileiro
- gancho_pauta: um parágrafo pronto para copiar e colar num e-mail a um jornalista ou assessoria, em português-padrão, sem clichês de texto gerado por IA e sem travessões, conectando o fato a {perfil['forma_de_tratamento']} como fonte especializada, com naturalidade, sem exagero de autopromoção

Responda SOMENTE com um JSON válido, sem nenhum texto antes ou depois, no formato:
{{"escolhidos": [{{"indice": <número do item na lista>, "pontuacao": <0 a 10>, "titulo_pt": "...", "resumo": "...", "porque_curioso": "...", "gancho_pauta": "..."}}]}}

ITENS:

{lista_itens}"""
    return instrucao


def chamar_api(config, prompt, api_key):
    corpo = json.dumps({
        "model": config["modelo_ia"],
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    requisicao = urllib.request.Request(
        API_URL,
        data=corpo,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
        },
        method="POST",
    )
    with urllib.request.urlopen(requisicao, timeout=120) as resposta:
        return json.loads(resposta.read())


def extrair_json(texto):
    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio == -1 or fim == -1:
        raise ValueError("resposta da IA não contém JSON")
    return json.loads(texto[inicio:fim + 1])


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY não definida — pulando curadoria.", file=sys.stderr)
        print(json.dumps([]))
        return

    config = carregar_config()
    bruto = carregar_csv(BRUTO_PATH, None)
    processados = carregar_processados()

    pendentes = [linha for linha in bruto if linha["id"] not in processados]
    if not pendentes:
        print("nenhum item pendente para curadoria.", file=sys.stderr)
        print(json.dumps([]))
        return

    lote = pendentes[: config["max_itens_por_lote_ia"]]
    prompt = montar_prompt(config, lote)

    try:
        resposta = chamar_api(config, prompt, api_key)
        texto = "".join(bloco.get("text", "") for bloco in resposta.get("content", []))
        resultado = extrair_json(texto)
    except Exception as exc:
        print(f"falha na chamada da IA: {exc}", file=sys.stderr)
        print(json.dumps([]))
        return

    agora = datetime.now(timezone.utc).isoformat()
    novos_ganchos = []
    for escolhido in resultado.get("escolhidos", []):
        indice = escolhido.get("indice")
        if indice is None or not (0 <= indice < len(lote)):
            continue
        item_original = lote[indice]
        linha = {
            "id": item_original["id"],
            "data_curadoria": agora,
            "titulo_original": item_original["titulo"],
            "titulo_pt": escolhido.get("titulo_pt", ""),
            "fonte": item_original["fonte"],
            "link": item_original["link"],
            "resumo": escolhido.get("resumo", ""),
            "porque_curioso": escolhido.get("porque_curioso", ""),
            "gancho_pauta": escolhido.get("gancho_pauta", ""),
            "pontuacao": escolhido.get("pontuacao", ""),
        }
        novos_ganchos.append(linha)

    # grava ganchos novos (acumulando com o histórico já existente)
    historico = carregar_csv(GANCHOS_PATH, CAMPOS_GANCHOS)
    ids_existentes = {linha["id"] for linha in historico}
    for linha in novos_ganchos:
        if linha["id"] not in ids_existentes:
            historico.append(linha)

    os.makedirs(os.path.dirname(GANCHOS_PATH), exist_ok=True)
    with open(GANCHOS_PATH, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=CAMPOS_GANCHOS)
        escritor.writeheader()
        for linha in historico:
            escritor.writerow({c: linha.get(c, "") for c in CAMPOS_GANCHOS})

    # marca TODO o lote avaliado como processado, escolhido ou não,
    # para não gastar API de novo com o que já foi analisado
    processados.update(item["id"] for item in lote)
    salvar_processados(processados)

    print(f"{len(novos_ganchos)} ganchos novos de {len(lote)} itens avaliados.", file=sys.stderr)
    print(json.dumps(novos_ganchos, ensure_ascii=False))


if __name__ == "__main__":
    main()

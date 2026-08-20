"""
Recebe (via stdin) o JSON com os ganchos novos gerados por curar.py e,
se houver pelo menos um, monta e envia um e-mail com o resumo do dia.
Usa só smtplib da biblioteca padrão — funciona com Gmail (senha de
app), Outlook ou qualquer SMTP com STARTTLS.

Variáveis de ambiente esperadas:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_TO
  MAIL_FROM (opcional, usa SMTP_USER se ausente)
  PAGINA_URL (opcional, link do painel publicado no GitHub Pages)
"""

import json
import os
import smtplib
import sys
from email.mime.text import MIMEText
from email.utils import formatdate


def montar_corpo(ganchos, pagina_url):
    linhas = [f"{len(ganchos)} sugestão(ões) de pauta hoje:\n"]
    for g in ganchos:
        linhas.append(f"— {g['titulo_pt']}  (pontuação {g['pontuacao']})")
        linhas.append(f"  fonte: {g['fonte']} · {g['link']}")
        linhas.append(f"  por que é curioso: {g['porque_curioso']}")
        linhas.append("")
        linhas.append("  gancho pronto para enviar à imprensa:")
        linhas.append(f"  {g['gancho_pauta']}")
        linhas.append("")
        linhas.append("-" * 60)
        linhas.append("")
    if pagina_url:
        linhas.append(f"Painel completo com o histórico: {pagina_url}")
    return "\n".join(linhas)


def main():
    entrada = sys.stdin.read()
    try:
        ganchos = json.loads(entrada) if entrada.strip() else []
    except json.JSONDecodeError:
        ganchos = []

    if not ganchos:
        print("nenhum gancho novo — e-mail não enviado.", file=sys.stderr)
        return

    host = os.environ.get("SMTP_HOST")
    porta = os.environ.get("SMTP_PORT")
    usuario = os.environ.get("SMTP_USER")
    senha = os.environ.get("SMTP_PASS")
    destinatario = os.environ.get("MAIL_TO")
    remetente = os.environ.get("MAIL_FROM") or usuario
    pagina_url = os.environ.get("PAGINA_URL", "")

    if not all([host, porta, usuario, senha, destinatario]):
        print("credenciais de SMTP incompletas — e-mail não enviado.", file=sys.stderr)
        return

    corpo = montar_corpo(ganchos, pagina_url)
    mensagem = MIMEText(corpo, "plain", "utf-8")
    mensagem["Subject"] = f"Radar de pautas — {len(ganchos)} sugestão(ões) hoje"
    mensagem["From"] = remetente
    mensagem["To"] = destinatario
    mensagem["Date"] = formatdate(localtime=True)

    with smtplib.SMTP(host, int(porta), timeout=30) as servidor:
        servidor.starttls()
        servidor.login(usuario, senha)
        servidor.sendmail(remetente, [destinatario], mensagem.as_string())

    print(f"e-mail enviado para {destinatario} com {len(ganchos)} ganchos.", file=sys.stderr)


if __name__ == "__main__":
    main()

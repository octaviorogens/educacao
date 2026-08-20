# Radar de Pautas — IA, Narrativa e Educação

Sistema que roda sozinho todo dia: coleta itens internacionais sobre
IA, narrativa e educação, manda para a Claude selecionar os que valem
pauta e já escrever o texto de sugestão, publica tudo num painel e
manda um e-mail com as novidades do dia.

## Como funciona, passo a passo

1. **`collect.py`** busca o Google News RSS para cada consulta listada
   em `config.json` (em inglês, espanhol e francês, para pegar
   cobertura de outros países) e guarda tudo em `data/bruto.csv`.
2. **`curar.py`** pega os itens que ainda não foram avaliados, manda
   todos de uma vez só (um único lote, para gastar pouca API) para a
   Claude, junto com seu perfil e os critérios de noticiabilidade
   definidos em `config.json`. A Claude escolhe os melhores, dá uma
   pontuação de 0 a 10 e já escreve, em português, o gancho de pauta
   pronto para mandar a um jornalista. O resultado vai para
   `data/ganchos.csv`.
3. **`enviar_email.py`** manda um e-mail só com os ganchos novos do
   dia, se houver algum.
4. **`index.html`** é o painel público: lê `data/ganchos.csv` e mostra
   tudo organizado por data, com busca, pontuação e botão para copiar
   o gancho ou já abrir um e-mail com ele preenchido.
5. **`.github/workflows/rotina.yml`** roda essa sequência inteira uma
   vez por dia (07h de Brasília) e comita os arquivos atualizados —
   isso é o que mantém o painel sempre com dado novo, sem você precisar
   rodar nada manualmente.

## O que você precisa configurar antes de publicar

### 1. Chave da API da Claude (obrigatória)

O sistema usa a API da Claude para julgar noticiabilidade e escrever
os ganchos — isso tem custo por chamada, mas é só **uma chamada por
dia** (o lote inteiro do dia vai numa mensagem só), então o gasto
tende a ser pequeno. Para criar uma chave:

1. Acesse [console.anthropic.com](https://console.anthropic.com), crie
   uma conta ou entre na existente.
2. Em "API Keys", gere uma chave nova.
3. Adicione crédito à conta (é pré-pago).

### 2. E-mail para envio (opcional, mas recomendado)

Qualquer SMTP com STARTTLS funciona. Com Gmail, por exemplo:

1. Ative a verificação em duas etapas na conta Google.
2. Gere uma "senha de app" em myaccount.google.com/apppasswords.
3. Use `smtp.gmail.com`, porta `587`.

### 3. Publicar no GitHub

1. Criar um repositório novo e subir estes arquivos.
2. Em **Settings → Secrets and variables → Actions**, cadastrar:
   - `ANTHROPIC_API_KEY` — sua chave da Claude
   - `SMTP_HOST` — ex.: `smtp.gmail.com`
   - `SMTP_PORT` — ex.: `587`
   - `SMTP_USER` — seu e-mail
   - `SMTP_PASS` — a senha de app (não a senha normal da conta)
   - `MAIL_TO` — para onde os ganchos do dia devem chegar (pode ser
     você mesmo, ou já direto a assessoria)
   - `MAIL_FROM` — opcional, se quiser um remetente diferente de
     `SMTP_USER`
3. Em **Settings → Actions → General → Workflow permissions**,
   marcar "Read and write permissions" (necessário para o commit
   automático).
4. Em **Settings → Pages**, escolher "Deploy from a branch", branch
   `main`, pasta `/ (root)`.
5. Opcional: em **Settings → Secrets and variables → Actions → Variables**,
   criar `PAGINA_URL` com o link do painel publicado (algo como
   `https://seu-usuario.github.io/radar-pautas/`), para que o e-mail
   inclua o link do histórico completo.
6. Rodar manualmente uma vez (aba **Actions → radar de pautas → Run
   workflow**) para popular os dados antes da primeira visita.

### 4. Preencher seu perfil

Em `config.json`, o bloco `perfil_fonte` já vem preenchido com seus
dados públicos (Mackenzie, doutorado na PUC-SP, palestras, entrevista
à Gazeta do Povo etc.). Vale revisar e completar o campo `contato`
com o e-mail que a assessoria/jornalista deve usar, e ajustar
`temas_que_pode_comentar` se quiser abrir ou restringir o leque.

## Ajustar o que é buscado e como é julgado

- `consultas`: lista de termos de busca no Google News RSS, cada um
  com idioma (`hl`) e país (`gl`) próprios. Adicionar, remover ou
  trocar termos muda o que entra no radar.
- `criterios_noticiabilidade`: a lista de critérios que a Claude usa
  para julgar cada item. É o lugar mais importante para ajustar se o
  sistema estiver trazendo coisa fraca ou deixando passar coisa boa.
- `limiar_pontuacao`: só itens com pontuação igual ou maior entram no
  painel e no e-mail. Baixar esse número traz mais itens (com menos
  qualidade média); subir traz menos e mais seletivo.
- `max_itens_por_dia`: teto de quantos ganchos por dia, mesmo que mais
  itens atinjam o limiar.
- `max_itens_por_lote_ia`: quantos itens brutos pendentes entram na
  mesma chamada da API. Se o volume diário de notícias for muito
  maior que isso, o excesso fica na fila para o dia seguinte — vale
  aumentar esse número se você notar itens acumulando sem serem
  avaliados.

## Rodar localmente para testar

```bash
export ANTHROPIC_API_KEY="sua-chave"
python collect.py            # popula data/bruto.csv
python curar.py > hoje.json  # avalia e escreve data/ganchos.csv
cat hoje.json | python enviar_email.py   # só funciona com as variáveis de SMTP também exportadas
python -m http.server 8000   # serve o painel em localhost:8000
```

## Limites para ter em mente

- O Google News RSS não é um índice completo da imprensa mundial —
  cobre bem veículos grandes indexados pelo Google Notícias.
- A curadoria depende inteiramente da qualidade dos critérios em
  `config.json`. Vale revisar os primeiros dias de resultado e
  ajustar os critérios e os termos de busca.
- Itens avaliados e descartados pela IA não voltam a ser reavaliados
  (ficam marcados em `data/processados.json`), para não gastar API à
  toa — se um critério mudar bastante, pode fazer sentido apagar esse
  arquivo para reavaliar tudo com a régua nova.

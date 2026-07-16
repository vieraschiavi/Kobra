# 🐍 MV Kobra AI · Plataforma de Cobranças Inteligentes

_Tradução para o português brasileiro gerada por IA a partir do original em espanhol. Recomenda-se revisão por um falante nativo antes de uso comercial amplo._

**MV Kobra AI** transforma uma carteira de cobrança em um plano de ação priorizado.
Combina um modelo de **probabilidade de pagamento (ProbPago)** com um **Agente de
IA Negociador** que recomenda a melhor estratégia, desconto, canal e roteiro de
conversa, e um **Copiloto de Negociação ao Vivo** que analisa o **sentimento do
cliente** (voz ou WhatsApp) e orienta o operador em tempo real — tudo dentro de
um dashboard gerencial com KPIs, filtros, gráficos e exportação para Excel/CSV.

> **O que é isto (leia primeiro).** MV Kobra AI é uma **demo comercial
> funcional** construída sobre **dados 100% sintéticos** (sem nomes de
> clientes, apta para ser mostrada sem problemas legais). Tudo o que você vê
> funcionando é real: o pipeline, o copiloto, a integração telefônica, o
> dashboard. Mas **nenhuma métrica de impacto ou de modelo mostrada aqui é
> evidência de resultados reais** — são **ilustrativas da metodologia**. A
> seção [Honestidade dos números](#-honestidade-dos-números-leia-antes-de-vender)
> explica exatamente o que é demonstração e o que se valida com dados reais.

**Apresentação gerencial:** `presentation/MVKobraAI_Presentacion_Gerencial.pptx`
(gerada com `python presentation/build_ppt.py`) · versão **Canva** editável
(rerrotulada, com os números marcados como ilustrativos):
<https://www.canva.com/d/VJ__8kGcZ2M3Q7D> (exportável para PDF/PPTX).

---

## ⚖️ Honestidade dos números (leia antes de vender)

Esta demo gera seus próprios dados, e isso tem uma consequência direta sobre
o que se pode afirmar diante de um cliente:

1. **O "impacto do MV Kobra AI" (+pp de conversão/recuperação) é uma premissa
   programada, não um resultado medido.** O gerador de atendimentos
   (`data/generate_gestiones.py`) **injeta por design** uma melhora progressiva
   nos operadores que "adotam o MV Kobra AI" (uma curva de aprendizado codificada).
   A aba *Operadores & Evolução* e `outputs/impacto_kobra.json` depois
   "recuperam" esse efeito. É **circular de propósito**: demonstra *como se
   mediria* o impacto (grupo com vs. sem a ferramenta, evolução mensal,
   uplift por coorte), não *quanto* o MV Kobra AI melhora. **Nunca apresente
   esses números como ROI medido.**

2. **O AUC do modelo também não comprova desempenho real.** O rótulo `pago` do
   dataset sintético é gerado com uma função logística conhecida; que um
   modelo a reaprenda com AUC ≈ 0.87 é **trivial e esperado por
   construção**. Aliás, na seleção de modelos o melhor resultado foi da
   **Regressão Logística** (ver `outputs/model_selection.json`) — coerente com
   o fato de que os dados são, literalmente, logísticos. Com uma carteira real,
   o algoritmo vencedor e o AUC serão outros. O que importa aqui é a
   **metodologia** (comparação de modelos com validação cruzada +
   calibração), não o número.

3. **O sentimento e a emoção de voz são heurísticos**, não modelos de deep
   learning treinados: léxico em espanhol com negação/intensificadores para
   texto, e prosódia (energia, F0, ritmo) para voz. Funcionam bem para a demo
   e para casos claros; em produção são substituídos por modelos treinados
   (SER tipo wav2vec2/SpeechBrain, diarização pyannote) **mantendo as
   mesmas interfaces**, que foram desenhadas exatamente para isso.

4. **O Streamlit é uma interface de demo/piloto**, não de um SaaS multi-tenant.
   Aguenta um piloto com uma equipe; para centenas de operadores simultâneos
   com isolamento de dados por cliente, a camada de UI é reescrita (o motor —
   `kobra/` e `realtime/` — permanece o mesmo).

### 🧪 Como isso seria validado com dados reais

Ao implementar com a carteira real de um cliente, a evidência é construída
assim (e só então é possível afirmar números):

- **Validação temporal (walk-forward):** treinar com os meses 1…N e avaliar
  no mês N+1, deslizando a janela — nunca validação aleatória que misture
  passado e futuro.
- **Anti-leakage:** cada feature precisa estar disponível **no momento do
  atendimento** (nada posterior ao contato: sem pagamentos futuros, sem
  promessas ainda não ocorridas, sem campos preenchidos apenas no fechamento).
- **Calibração medida, não presumida:** curvas de confiabilidade e Brier score
  sobre dados reais; recalibração periódica.
- **Uplift causal com grupo de controle:** alocação aleatória de operadores ou
  subcarteiras para "com MV Kobra AI" vs. "sem MV Kobra AI" durante o piloto; a
  diferença na taxa de cura / $ recuperado por hora de operador / promessas
  cumpridas é o impacto real — exatamente a análise que a aba *Operadores &
  Evolução* já sabe fazer.
- **Monitoramento de drift** e retreinamento programado (o workflow
  `train.yml` já existe).

**Caminho comercial honesto:** demo com dados sintéticos → **piloto pago e
limitado** sobre uma subcarteira real → caso-piloto com números medidos → só
então, implementação completa com evidência própria.

---

## 🎯 O que resolve

| Problema tradicional | Com MV Kobra AI |
|---|---|
| Todos os devedores são tratados da mesma forma | Priorização pelo **valor esperado de recuperação** |
| Descontos e planos "no olho" | Decisões baseadas na **probabilidade de pagamento** |
| Não se sabe quem contatar primeiro | Ranking operacional automático |
| Roteiros de negociação improvisados | **Roteiro gerado** pelo agente de IA |
| O operador negocia "às cegas" | **Copiloto ao vivo**: sentimento + próxima jogada |
| Relatórios manuais e lentos | **Dashboard + exportação para Excel/CSV** |

---

## 🏗️ Arquitetura (end-to-end)

```
Carteira (CSV)
   │
   ├─►  ProbPago  (kobra/probpago.py)      modelo de probabilidade de pagamento (ML)
   │
   ├─►  Agente Negociador (kobra/negociador.py)   estratégia + desconto + canal + roteiro
   │
   ├─►  Copiloto ao Vivo (kobra/copiloto.py)       sentimento + técnicas + orientação em tempo real
   │        ├─ realtime/  (FastAPI + WebSocket)     áudio ao vivo durante a ligação
   │        └─ voz (kobra/voz.py)                   diarização + emoção acústica de voz
   │
   ├─►  Analítica de atendimento (kobra/analitica.py)  por operador/mês/faixa/segmento + medição de impacto
   │
   ├─►  Treinamento ML (kobra/train.py)          seleção de modelos + calibração (ProbPago)
   │
   ├─►  Pipeline (kobra/pipeline.py)       orquestra tudo e exporta
   │        ├─ outputs/kobra_scored.csv / .xlsx
   │        ├─ outputs/kobra_bundle.json
   │        └─ dashboard_estatico/kobra_data.js
   │
   ├─►  Dashboard Streamlit (app/app.py)   KPIs · filtros · gráficos · exportação
   ├─►  Dashboard estático (dashboard_estatico/index.html)   zero-install, offline
   └─►  Apresentação gerencial (presentation/*.pptx)
```

---

## 🚀 Como executar

### Opção rápida (tudo em um)
```bash
./run.sh            # instala as dependências, gera os dados, roda o modelo e abre o dashboard
```

### Passo a passo
```bash
pip install -r requirements.txt
python data/generate_dataset.py --n 12000 --seed 42   # gera a carteira sintética
python -m kobra.pipeline                              # treina ProbPago + negociador + exportações
streamlit run app/app.py                              # dashboard interativo
python presentation/build_ppt.py                      # apresentação gerencial (PPTX)
```

### 🪟 Instalador standalone para Windows (programa, sem instalar Python)

Um **`MVKobraAI_Setup.exe`** que instala o MV Kobra AI como um programa (empacota
o Python e todas as bibliotecas; duplo clique → o dashboard abre). É gerado no
**Windows via GitHub Actions** (não é possível compilar a partir de Linux/Mac):

- **Automático**: o workflow `build-windows-installer` roda em `windows-latest`
  (PyInstaller → executável, Inno Setup → instalador). O `.exe` fica disponível
  como **artefato para download** em cada execução (aba *Actions* do
  repositório) e, ao criar uma tag `vX.Y.Z`, é publicado em uma **Release**.
- **Componentes**: `electron/` (o app de desktop: janela Electron com a UI
  React), `packaging/kobra_launcher.py` (inicia o motor) e
  `packaging/kobra.spec` (empacotamento PyInstaller). O electron-builder gera
  o instalador NSIS com atalhos, ícone e **desinstalador** registrado em
  "Adicionar ou remover programas".

```
Actions → build-windows-installer → (Run workflow) → artefato "MVKobraAI_Setup_Windows"
   ou   → git tag v1.3.0 && push  → Release com MVKobraAI_Setup_v1.3.0.exe
```

### Dashboard sem instalar nada
Abra `dashboard_estatico/index.html` em qualquer navegador (funciona
offline, com bibliotecas locais). Ideal para demonstrações e para compartilhar
por e-mail.

### 🐳 Deploy com Docker (piloto/produção)

```bash
docker compose up --build
#  Dashboard:  http://localhost:8501
#  Realtime :  http://localhost:8000   (copiloto de áudio ao vivo)
```

Uma única imagem atende os dois serviços (dashboard Streamlit e API realtime).
Os dados/modelo são gerados na primeira inicialização; os volumes mantêm
dados, outputs e a **configuração das chaves de API** entre reinicializações.

### 🔑 Configuração das chaves de API (persistente)

As chaves são carregadas de três formas (prioridade de cima para baixo):

1. **Variáveis de ambiente / `.env`** (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) — ideal em produção.
2. **Dashboard → aba "Configuração"**: são inseridas uma vez e ficam
   **salvas** (`$KOBRA_CONFIG_DIR/config.json`, por padrão `~/.kobra`), assim
   carregam sozinhas a cada inicialização, sem precisar reinseri-las.
3. **Sem chaves**: o MV Kobra AI funciona do mesmo jeito (sem transcrição Whisper nem avaliação com Claude).

Com `OPENAI_API_KEY` habilita-se a transcrição real (Whisper) e com
`ANTHROPIC_API_KEY`, a avaliação qualitativa com Claude.

---

## 📊 O dashboard

Sete abas, com **filtros dinâmicos** (segmento, produto, faixa de atraso,
propensão, departamento, valor e ProbPago mínima):

1. **Visão geral** — 6 KPIs, carteira vs. recuperação por faixa, propensão,
   recuperação por segmento e top departamentos.
2. **Agente Negociador** — estratégias recomendadas, recuperação por estratégia e
   um **simulador por devedor** com o roteiro pronto para enviar.
3. **Carteira & Exportação** — tabela priorizada + download em **CSV / Excel**.
4. **Modelo ProbPago** — métricas da demo, drivers e distribuição.
5. **Copiloto ao Vivo** — análise de conversas e de gravações (voz).
6. **Operadores & Evolução** — metodologia de medição de impacto (ilustrativa).
7. **Configuração** — chaves de API persistentes.

---

## 🧠 ProbPago (o modelo)

- **Metodologia:** seleção de modelos com **validação cruzada (5 folds)** —
  Regressão Logística, Random Forest, Gradient Boosting, HistGradientBoosting —
  escolha por ROC-AUC, **calibração isotônica** e persistência
  (`python -m kobra.train` → `outputs/probpago_model.joblib` +
  `outputs/model_selection.json`).
- **O pipeline usa esse mesmo modelo selecionado e calibrado, não um separado.**
  `kobra/pipeline.py` (e, portanto, o dashboard Streamlit e o estático) carrega
  automaticamente `outputs/probpago_model.joblib` quando você já rodou
  `python -m kobra.train`; se não rodou, ele recorre a um Gradient Boosting
  ad-hoc sem calibração e **sinaliza isso na tela** (nunca é exibido um modelo
  diferente do que realmente pontuou a carteira).
- **No dataset sintético da demo, a Regressão Logística venceu**
  (esperado: o rótulo é gerado com uma função logística — ver
  [Honestidade dos números](#-honestidade-dos-números-leia-antes-de-vender)).
  Com dados reais, o vencedor e as métricas são determinados de novo, com
  validação temporal.
- **Features:** valor, dias de atraso, score de crédito (birô), contatabilidade,
  histórico de pagamentos e promessas, tempo de relacionamento, atendimentos
  anteriores, segmento, produto, departamento e canal — todas disponíveis no
  momento do atendimento.
- **Saída:** probabilidade de pagamento (0–1), decil e propensão (Alta/Média/Baixa).
- Retreinamento programado via GitHub Actions (`.github/workflows/train.yml`).

## 🤖 Agente de IA Negociador

Para cada devedor decide, maximizando a **recuperação esperada** e minimizando
o abatimento:

- **Estratégia** (lembrete suave, pagamento total facilitado, parcelamento,
  abatimento agressivo, encaminhamento especializado…).
- **Desconto** e **plano de parcelamento** sugeridos.
- **Canal** ideal (alto valor → contato humano).
- **Roteiro** parametrizado, pronto para enviar (sem nomes reais).
- **Prioridade** operacional por valor esperado (UYU).

## 🎧 Copiloto de Negociação ao Vivo

Auxilia o operador **durante** a negociação por telefone ou WhatsApp
(`kobra/copiloto.py`):

- **Análise de sentimento** turno a turno (léxico em espanhol rio-platense com
  negação e intensificadores — heurístico, substituível por um modelo
  treinado com a mesma interface).
- **Detecção de emoções** do cliente (raiva, frustração, ansiedade,
  dificuldade financeira, intenção de pagamento, objeção…).
- **Detecção de técnicas** do operador (ancoragem, fracionamento, alternativas,
  reciprocidade, urgência, escassez, validação, fechamento…).
- **Scoring de qualidade** do atendimento (critérios ponderados).
- **Orientação em tempo real**: sugestões acionáveis + a **próxima frase**
  sugerida, vinculadas à ProbPago do devedor.

Funciona **100% offline**. Se houver chaves configuradas no ambiente, ele se
enriquece automaticamente: `OPENAI_API_KEY` → transcrição de áudio (Whisper);
`ANTHROPIC_API_KEY` → avaliação qualitativa (Claude).

Disponível em três lugares:
- **Dashboard Streamlit** → aba *Copiloto ao Vivo* (colar/enviar conversa).
- **Dashboard estático** → seção *Copiloto (offline)* — motor portado para JS,
  roda no navegador sem backend (`dashboard_estatico/copiloto.js`).
- **Áudio em tempo real** → `realtime/` (ver mais abaixo).

### 🎙️ Áudio ao vivo durante a ligação (`realtime/`)

Backend **FastAPI + WebSocket** que auxilia o operador **enquanto** ele fala:

```
Microfone/ligação → transcrição ao vivo → Copiloto → orientação na tela
```

- O navegador transcreve com a **Web Speech API** (espanhol, sem chave de API)
  ou, do lado do servidor, com **Whisper** (`POST /transcribe`) se houver
  `OPENAI_API_KEY`.
- Cada turno viaja pelo WebSocket; o servidor roda o Copiloto e devolve em
  milissegundos: sentimento, emoção, técnicas, qualidade, sugestões e a
  próxima frase.
- Inclui um modo **"Simular ligação"** para demonstrar sem microfone.

```bash
python -m realtime.server     # http://localhost:8000
```

**Em produção telefônica**, o áudio é captado do softphone/PBX (gravação ou
media stream do canal), não do microfone; o restante do fluxo é idêntico.

### 🗣️ Diarização + emoção acústica de voz (`kobra/voz.py`)

Analisa o **sinal de voz** da ligação, não apenas as palavras:

- **Diarização** (quem fala):
  - *Dual-channel* (o mais comum em gravação de call center): uma perna por
    interlocutor → separação **exata** por canal.
  - *Mono*: segmentação por energia (VAD) + clustering de 2 falantes (KMeans
    sobre features espectrais). Offline, sem modelos pesados.
- **Emoção acústica (prosódia)**: a partir de energia, tom (F0), variação de
  tom, ritmo da fala e brilho espectral, estima *arousal*/*valência* e um
  rótulo (raiva, frustração, ansiedade, resignação, neutro, positivo).
  **Heurística baseada em prosódia** — suficiente para a demo; em produção é
  substituída por um modelo SER treinado (wav2vec2/SpeechBrain) e a
  diarização mono por pyannote.audio, com a mesma interface.
- **Fusão voz + texto**: o sentimento acústico é combinado com o do texto
  (`copiloto.analizar_sentimiento(texto, voz=…)`), de modo que uma **voz tensa
  do cliente antecipa o alerta** mesmo que as palavras sejam neutras.

Teste com a gravação de demo (dual-channel sintética):

```bash
python data/generate_audio_demo.py      # cria data/ejemplo_llamada.wav
# No dashboard → aba "Copiloto ao Vivo" → "Analisar gravação (voz)"
# ou via API:  POST /analizar_audio  no servidor realtime
```

### ☎️ Integração com telefonia (softphone / PBX)

Um **PBX** é a central telefônica da empresa; um **softphone** é o telefone
por software do operador. O MV Kobra AI **não os substitui**: ele se conecta
ao **áudio** que eles já processam. O MV Kobra AI é **agnóstico de
plataforma** — funciona com Avaya, Genesys, Cisco, 3CX, Asterisk/FreePBX,
Twilio etc. — porque capta o áudio por mecanismos padrão:

| Plataforma | Como o áudio é obtido |
|---|---|
| **Avaya** | Gravação dual-channel (Avaya AES/DMCC) ou media stream via SIPREC |
| **Genesys** | AudioHook / SIPREC / gravação por agente |
| **Cisco** | Built-in Bridge / Network-Based Recording (SIPREC) |
| **Asterisk / 3CX** | `MixMonitor` (dual-channel) ou forking de RTP |
| **Twilio / nuvem** | Media Streams (WebSocket de áudio ao vivo) |
| **Qualquer uma** | Arquivo de gravação `.wav` dual-channel pós-ligação |

Recomendado: **gravação dual-channel** (uma perna por interlocutor) → a
diarização é exata e a emoção por falante é mais precisa. O restante do
pipeline (transcrição → copiloto → orientação) é idêntico em todos os casos.

> ⚠️ **Microfone do computador ≠ telefonia.** O microfone só capta o áudio do
> computador (útil para VoIP no PC ou testes). Para uma ligação via central
> (Avaya etc.), o áudio passa pela telefonia: use a opção **"Central
> telefônica / gravação"**. No app realtime há um seletor **"Fonte de
> áudio"** que separa os dois modos.

### 📝 Transcrição alinhada por falante

`voz.transcribir_llamada()` / `voz.copiloto_desde_audio()` geram a
transcrição **por turno e por falante**:

- Com **`OPENAI_API_KEY`** → o Whisper transcreve o áudio real com **marcações
  de tempo por segmento**, e cada segmento é atribuído ao falante diarizado
  com maior sobreposição temporal.
- Sem chave → uma transcrição fornecida (ou a do chat) é **alinhada** aos
  falantes diarizados por ordem.

Cada turno é fundido com a **emoção acústica** daquele trecho, de modo que a
tabela mostra `Sent. texto` vs `Sent. voz+texto` — a voz tensa do cliente
leva o alerta além do que as palavras dizem. Endpoints:
`POST /copiloto_audio` (enviar gravação) e `GET /copiloto_demo`.

### 📡 Streaming ao vivo (conectores) — `realtime/connectors.py`

Para orientar **enquanto a ligação acontece**, o áudio da central entra por
WebSocket e o copiloto responde turno a turno:

| Fonte | Endpoint | Formato |
|---|---|---|
| **Twilio Media Streams** | `WS /twilio` | μ-law 8 kHz; `track` inbound→cliente, outbound→operador (protocolo real do Twilio) |
| **SIPREC** (Avaya/Genesys/Cisco) | `WS /ws_audio` | o SBC/gravador faz fork do RTP para um media server que reenvia **PCM16** |
| **Avaya DMCC/AES** | `WS /ws_audio` | o SDK entrega o áudio do canal e ele é reenviado como PCM16 |

`StreamSession` acumula áudio por falante e, ao fechar cada turno (silêncio /
troca de interlocutor), transcreve (Whisper se houver chave), calcula a
emoção acústica, funde voz+texto e devolve a orientação. Teste sem uma
central real:

```bash
python -m realtime.server            # sobe o servidor
python -m realtime.simular_stream    # transmite a gravação demo para /ws_audio
# ou no navegador: modo "Central telefônica" → "📡 Simular stream ao vivo"
```

**Para conectar sua central**: aponte o `<Stream>` do Twilio para
`wss://<host>/twilio`, ou configure o SIPREC/DMCC para reenviar o media para
`wss://<host>/ws_audio`. A orientação é roteada para a tela do operador (WS
`/ws`).

### ☎️ Conector Avaya / SIPREC (`realtime/conector_avaya.py`)

Ponte **RTP → MV Kobra AI** pronta para produção: recebe o áudio que a
central faz fork via RTP (**G.711 μ-law ou A-law** — A-law é o padrão no
Uruguai —, pacotes de 20 ms, uma perna por porta UDP), faz VAD por energia,
corta cada turno no silêncio e o envia ao Copiloto, que devolve a orientação
ao vivo e registra o atendimento ao desligar.

```bash
python -m realtime.conector_avaya --deudor KB-100773 --gestor G03
#   --puerto-gestor 5004 --puerto-cliente 5006 --silencio 0.6
#   --transcript <arquivo do CTI>   (opcional, enriquece sem Whisper)
```

- **Codecs bit-exatos**: decodificadores μ-law/A-law próprios em numpy,
  verificados byte a byte contra a referência G.711 em toda a faixa int16
  (sem depender de `audioop`, removido no Python 3.13).
- **Autodetecção de codec** por payload type RTP (0 = PCMU, 8 = PCMA).
- **Lado Avaya**: SIPREC no SBC/Aura apontando para o host do conector, ou
  DMCC/AES direcionando o RTP da estação virtual. O `id_deudor` chega pelo
  CTI (UUI/header SIP) e é passado com `--deudor`.

**Teste sem uma central física** com o simulador de RTP incluído (emite a
ligação demo como pacotes RTP reais, igual a um SBC):

```bash
python -m realtime.server                                 # terminal 1
python -m realtime.conector_avaya --deudor KB-100773      # terminal 2
python -m realtime.simular_rtp --codec alaw               # terminal 3
```

Verificado end-to-end: os 10 turnos chegam separados por perna, com emoção
de voz detectada (raiva/frustração do cliente), brief pré-ligação, orientação
turno a turno e atendimento registrado ao encerrar.

### 🔁 Ciclo completo da negociação (pré → ao vivo → pós)

1. **Antes de ligar** — `GET /brief/{id_deudor}`: briefing para o screen-pop
   do CTI (Avaya Workspaces etc.): ProbPago, estratégia, desconto máximo,
   plano, canal, roteiro e prioridade, calculados pelo pipeline. O discador
   (por ex., Avaya Proactive Outreach) pode usar a lista priorizada exportada.
2. **Durante** — a mensagem `start` de `/ws_audio` aceita `id_deudor` e
   `gestor_id`: o MV Kobra AI carrega sozinho o briefing e ajusta a proposta
   turno a turno conforme o sentimento (voz + texto) do cliente.
3. **Ao desligar** — a mensagem `stop` (aceita `resultado` com a tipificação
   real do CRM; se estiver ausente, é inferido a partir do clima + intenção
   de pagamento) **persiste a negociação** em `data/kobra_gestiones.csv` via
   `kobra/registro.py`: qualidade, sentimento, emoção dominante, técnicas,
   resultado e recuperação. Essa é a mesma base que alimenta a aba
   **Operadores & Evolução**, de modo que o dashboard passa da demo para
   **ligações reais** sem nenhuma mudança.

Teste end-to-end sem uma central: `python -m realtime.simular_stream` (mostra
o brief, a orientação ao vivo e o atendimento registrado no final).

## 🤖 Operador IA · agente autônomo de negociação (`kobra/gestor_ia.py`)

O **operador virtual** conduz a negociação completa da mesma forma que um
humano — por **voz** (voicebot) ou por **WhatsApp** (chatbot): cumprimenta,
valida a identidade, propõe conforme a ProbPago/estratégia, contorna
objeções com **concessões escalonadas dentro do teto autorizado**, fecha,
**preenche os campos do ERP** e registra o atendimento. Aparece em
*Operadores & Evolução* como operador `IA…`, para que seu desempenho seja
**medido contra os humanos**.

- **Dependências externas mínimas por design**: o cérebro (diálogo, intenção,
  sentimento) roda **100% local**. **O Claude (Anthropic) é a única IA
  externa e é opcional**: se houver `ANTHROPIC_API_KEY`, ele redige de forma
  mais natural; sem chave, usa modelos de texto prontos (funciona do mesmo
  jeito).
- **Voz local, sem nuvem**: adaptadores para **Piper TTS** (voz neural
  es-AR/es-ES, baixa latência) e **faster-whisper STT**; se não estiverem
  instalados, roda em modo texto (mesmo diálogo).
- **Campanhas simultâneas** (`realtime/voicebot.py`): **até 50 ligações
  simultâneas** (verificado: 50 linhas, pico de 50, 0 erros). O canal de voz
  real é fornecido pela telefonia do cliente (Twilio `<Connect>`,
  Avaya/SIPREC com o conector incluído, Asterisk…); na demo há um cliente
  simulado.
- **Chatbot WhatsApp** (`POST /whatsapp/webhook`): para quem não quer falar
  por telefone. O proxy do canal (WhatsApp Cloud API / Twilio WhatsApp do
  cliente) envia `{sesion, id_deudor, mensaje}` via POST e o Operador IA
  negocia e registra o atendimento como canal WhatsApp.

```bash
python -m realtime.voicebot --lineas 50 --llamadas 50   # campanha ativa (outbound)
# chatbot WhatsApp: POST /whatsapp/webhook  (ver realtime/server.py)
```

> Nota: na demo, a coorte do Operador IA em *Operadores & Evolução* é
> **sintética e ilustrativa** (como o restante). Na operação real, cada
> conversa do Operador IA registra seu atendimento e o dashboard compara IA
> vs. humanos com dados medidos.

## 📇 Analítica por operador e por mês (`kobra/analitica.py`)

Sobre o histórico de atendimentos, responde:

- **Quais características ocorrem mais** por faixa de atraso, segmento, canal
  ou produto (emoção dominante do cliente, qualidade, conversão, recuperação)
  e uma **matriz de emoções** por faixa/segmento.
- **Como evoluem mês a mês** (qualidade, sentimento, conversão, recuperação).
- **Relação entre qualidade do atendimento ↔ conversão/recuperação.**
- **Medição de impacto com grupo de controle** (*com vs. sem MV Kobra AI*) e
  evolução por operador — a mecânica exata que seria usada em um piloto real.

> ⚠️ Na demo, o histórico de atendimentos é **sintético** e o "efeito
> MV Kobra AI" está **injetado pelo gerador** para ilustrar a metodologia.
> Os uplifts exibidos na aba *Operadores & Evolução* **não são resultados
> medidos**. Com o registro pós-ligação (`kobra/registro.py`), a mesma aba
> passa a se alimentar de ligações reais, e aí sim os números significam
> algo.

## 🔬 Treinamento ML (`kobra/train.py`)

Seleção de modelos com **validação cruzada (5 folds)**: compara Regressão
Logística, Random Forest, Gradient Boosting e HistGradientBoosting, escolhe o
melhor por ROC-AUC, **calibra** (isotônica) e o persiste:

```bash
python -m kobra.train
# → outputs/probpago_model.joblib  e  outputs/model_selection.json
```

É retreinado em CI via **GitHub Actions** (`.github/workflows/train.yml`,
manual ou semanal). O workflow `ci.yml` roda os testes e um smoke test do
pipeline a cada push/PR.

---

## 🛡️ Conformidade, explicabilidade e caso de negócio

Três camadas que tornam o MV Kobra AI vendável a uma entidade regulada
(banco, financeira, cooperativa, escritório de cobrança) e não apenas
demonstrável.

### ⚖️ Conformidade regulatória — `kobra/cumplimiento.py`

Governa **quando e como** cada devedor pode ser contatado, para que a
cobrança — humana ou do Operador IA — opere dentro da lei e das boas
práticas. É a camada que o jurídico/compliance exige antes de deixar um bot
ligar para uma carteira:

- **Horário permitido**: bloqueia contatos fora da faixa (padrão 09h–20h),
  aos domingos ou em **feriados do Uruguai** (fixos + Semana de
  Turismo/Carnaval derivados da Páscoa).
- **Limite de frequência** por devedor (antiassédio): máximos por dia e por
  7 dias.
- **Lista "Não Contatar" / opt-out**: se o devedor pedir para não ser
  contatado, o Operador IA **detecta, registra e não liga mais para ele**
  (`es_pedido_no_contactar` → `registrar_no_contactar`). O voicebot **filtra
  a base** antes de discar.
- **Política 100% configurável** por empresa/país (`PoliticaContacto`).

```python
from kobra import cumplimiento as cp
d = cp.puede_contactar("KB-100773", "Llamada")   # Decision(permitido, codigo, motivo)
```

> ⚠️ Ferramenta de **apoio à conformidade, não assessoria jurídica**: cada
> empresa define sua política com sua assessoria jurídica; o MV Kobra AI
> fornece o mecanismo para fazê-la cumprir e auditar.

### 🔍 Explicabilidade da ProbPago — `kobra/explicabilidad.py`

Para cada devedor, responde **por que** o modelo atribuiu essa probabilidade:
quais características a elevam e quais a reduzem, em pontos percentuais
(atribuição por **oclusão**, model-agnostic — funciona com qualquer modelo do
pipeline). O pipeline adiciona a coluna `motivo_probpago` à carteira pontuada
e ao **brief pré-ligação**, por exemplo:

```
KB-111022 · ProbPago 99% → Score de crédito (+3.9 pp) · Promessas cumpridas (+0.5 pp)
KB-106556 · ProbPago  1% → Promessas não cumpridas (-1.1 pp) · Dias de atraso (-1.0 pp)
```

Transforma a ProbPago de "caixa-preta" em uma **decisão automatizada
auditável e defensável** — o que exigem a Lei 18.331 do Uruguai e marcos
regulatórios equivalentes.

### 💰 Caso de negócio (ROI) — `kobra/roi.py`

Traduz a carteira do comprador em uma faixa de valor sob diferentes premissas
de *uplift*, para dimensionar o prêmio e justificar um piloto pago:

```bash
python -m kobra.roi --cartera 100000000 --tasa-base 0.30 --costo-mensual 100000
#  [conservador] +2 pp → adicional $U 2.000.000 …
#  [       base] +5 pp → adicional $U 5.000.000 · ROI … · payback … m
```

> ⚠️ O *uplift* é uma **premissa que o usuário insere, não um resultado
> medido**. O módulo projeta *quanto isso valeria*, não afirma quanto o
> MV Kobra AI aumenta — coerente com a seção
> [Honestidade dos números](#-honestidade-dos-números-leia-antes-de-vender).

### 🧪 Testar com sua própria carteira — **pelo dashboard** (sem código)

No dashboard, aba **"🧪 Probar mi cartera"**: você carrega seus contatos —
**digitando-os em uma tabela**, **enviando um CSV/Excel** ou **trazendo-os
direto do seu banco de dados** (PostgreSQL, MySQL, SQL Server, SQLite… com
uma consulta somente leitura; `cartera_manual.desde_base_de_datos`) — e o
Operador IA negocia cada caso (ProbPago + o porquê, estratégia, verificação
de conformidade e a conversa completa). Os resultados são **baixados** em
CSV/Excel. Tudo por menus; não é preciso rodar nada.

A aba **"💰 Caso de negocio"** calcula o ROI sobre sua carteira com suas
premissas, e também pode ser baixada.

> Também há um CLI equivalente (`python -m realtime.mi_cartera`) para quem
> preferir o console. O CSV com dados reais fica **privado** (`.gitignore`).

A conversa é **simulada**. Para **ligar de verdade** é preciso ter telefonia
(sua conta Twilio com um número, ou sua central Avaya/Asterisk) e o
**consentimento** da pessoa — guia passo a passo em
[`GUIA_LLAMADA_REAL_TWILIO_pt.md`](GUIA_LLAMADA_REAL_TWILIO_pt.md). Comprar
o número e apontar seu webhook de voz **não precisa ser feito manualmente no
Console da Twilio**: a aba Configuração → "📞 Auto-configurar número
Twilio" (`kobra/twilio_setup.py`) faz isso via API, com as credenciais que
você já cadastrou.

> ⚖️ **Proteger o MV Kobra AI no Uruguai** (direitos autorais + marca, com
> custos): [`GUIA_REGISTRO_LEGAL_URUGUAY.md`](GUIA_REGISTRO_LEGAL_URUGUAY.md).

> 💼 **Modelo comercial** (PoC + implementação + retainer, proposta a
> confirmar): [`MODELO_COMERCIAL.md`](MODELO_COMERCIAL.md).

> 🏦 **Vender para um banco/financeira** (procurement): whitepaper de
> segurança ([`WHITEPAPER_SEGURIDAD.md`](WHITEPAPER_SEGURIDAD.md)), modelo
> de acordo de tratamento de dados ([`PLANTILLA_DPA.md`](PLANTILLA_DPA.md))
> e modelo de SLA ([`PLANTILLA_SLA.md`](PLANTILLA_SLA.md)) — os três são
> rascunhos para adaptar com seu assessor jurídico, não documentos prontos
> para assinatura.

> 🔒 **Privacidade.** Um CSV com nomes/telefones **reais** é privado:
> `data/mi_cartera_prueba.csv` e `data/*_prueba.csv` estão no `.gitignore` e
> **não são enviados ao repositório**. O produto que é vendido continua
> sendo 100% sintético (Lei 18.331). Para ligar para um terceiro, você
> precisa do consentimento dele.

### 🔌 Integração com ERP / banco de dados — `kobra/integracion.py`

Cada atendimento — do **Operador IA** ou de um **humano** — fica
**tipificado** com seu resultado e seus dados, e essa **planilha
consolidada** é exportada ou **sincronizada com qualquer ERP ou banco de
dados**:

- **Tipificação padrão de cobrança**: `Pago · Arreglo de pago · Promesa de
  pago · Informado · No contactado · Fallecido · Negativa · Número erróneo ·
  Sin acuerdo` (Pago / Acordo de pagamento / Promessa de pagamento /
  Informado / Não contatado / Falecido / Recusa / Número incorreto / Sem
  acordo), com `fecha_gestion`, `fecha_compromiso`, `fecha_pago`,
  `monto_acordado`, `cuotas`, `descuento`, `notas`, `tipo_gestor` (IA/Humano)…
- **Saídas**: arquivos **JSON / CSV / Excel**, **API REST** (POST da planilha
  consolidada para o webhook do ERP, com Bearer token) e **banco de dados**
  (SQLAlchemy → PostgreSQL, MySQL/MariaDB, SQL Server, Oracle, SQLite…).
- **Mapeamento de campos** opcional (`aplicar_mapeo`) para renomear as
  colunas do MV Kobra AI para as do ERP do cliente.
- No dashboard: aba **"🔌 Integração ERP"** com pré-visualização da planilha
  consolidada, download e envio/sincronização com um clique (as conexões são
  salvas em *Configuração*).

```python
from kobra import integracion as ig
sab = ig.sabana(gestiones_df)
ig.enviar_api(sab, "https://tu-erp.com/api/gestiones", api_key="…")
ig.sincronizar_db(sab, "postgresql://user:pass@host/db", tabla="gestiones")
```

### 🔎 Pergunte ao seu banco de dados (NL2SQL) — `kobra/consulta_bd.py`

Conecta-se a **qualquer banco relacional do cliente** (PostgreSQL, MySQL/
MariaDB, SQL Server, Oracle, SQLite… qualquer um compatível com SQLAlchemy) e
responde perguntas feitas **em espanhol**, devolvendo o SQL usado, a tabela
de resultados e um gráfico automático — sem inventar nomes de tabela/coluna:

1. **Extrai o catálogo completo** do esquema uma única vez: tabelas, colunas,
   PKs, FKs declaradas, views e relações inferidas pelo nome da coluna
   (apenas metadados — nunca o conteúdo real das linhas, exceto algumas
   amostras de valores de texto para dar contexto de domínio).
2. **RAG local (TF-IDF, sem sair para a internet)** recupera as tabelas mais
   relevantes para a pergunta.
3. **O Claude gera o SQL** usando apenas esse esquema recuperado.
4. É **validado contra o catálogo** (tabelas/colunas existem, é somente
   leitura — bloqueia `INSERT/UPDATE/DELETE/DROP/ALTER`) antes de ser
   executado.
5. É executado com **limite automático de linhas** e fica registrado no log
   de auditoria (host da conexão, nunca a URL completa).

No dashboard: aba **"🔎 Preguntá a tu base de datos"** — cole a URL de
conexão (a mesma de *Integração ERP* ou outra), conecte-se e pergunte.

```python
from kobra import consulta_bd as cb
motor = cb.MotorConsultaBD("postgresql://user:pass@host/db")
r = motor.responder("cuánto cobramos en marzo 2026 por departamento",
                    api_key="sk-ant-...")
df = motor.resultado_a_dataframe(r)
```

### 📅 Agenda de acompanhamento — `kobra/seguimiento.py`

Fecha o ciclo depois de uma "Promessa de pagamento" ou "Acordo de pagamento":
detecta quando a data combinada venceu **sem que o pagamento tenha sido
registrado** (nem no mesmo atendimento, nem em um posterior), e monta a
agenda do dia — quem recontatar e por quê — respeitando a política de
conformidade vigente (horário, feriados, limites de frequência, lista de Não
Contatar). Não é um canal novo: o recontato continua sendo um atendimento
normal do Operador IA ou de um humano.

No dashboard: aba **"📅 Agenda de seguimiento"**.

```python
from kobra import seguimiento as kseg
agenda = kseg.agenda_hoy(gestiones_df)   # + columnas contactable / motivo_bloqueo
```

### 🎙️ Voz premium opcional (ElevenLabs) — `kobra/voz_tts.py`

Por padrão, as ligações usam `<Say>` do Twilio (vozes Amazon Polly, incluídas
na conta Twilio, sem custo extra). Ao configurar `ELEVENLABS_API_KEY` e
escolher uma voz em **Configuração**, as ligações reais passam a usar o
ElevenLabs — mais vozes, sotaques regionais reais e clonagem de voz. **Tem
custo real por caractere** (ver `COSTO_POR_1000_CHARS_USD` no módulo —
referência de mercado; verifique com o seu plano real antes de fixar o
preço). Por isso, no backend de vendas (`backend_venta/`), essa voz premium
exige a feature `"voz_premium"` à parte — não vem incluída por padrão em
nenhum plano, para que o preço fixo de um plano não acabe subsidiando um
custo variável não cotado. Se falhar ou não estiver configurada, ele recai
automaticamente para Twilio/Polly — nunca interrompe a ligação.

### 📣 Campanha automática de contato — `kobra/campana.py`

Orquestra o contato ativo **sem intervenção manual**, rodando dentro de
`realtime/server.py` (exige que esse processo fique ativo 24/7 —
Docker/servidor real, não um `streamlit run` que só existe enquanto o
dashboard está aberto):

1. **Prioridade**: promessas/acordos vencidos primeiro (`kobra/seguimiento.py`),
   depois o restante da carteira por `valor_esperado_recupero`.
2. **Canal preferido por devedor**: não é uma regra fixa — é calculado a
   partir do **histórico real de atendimentos** dos últimos meses (onde ele
   foi mais contatado ou onde houve mais fechamentos).
3. **Horário preferido**: o horário do dia mais frequente nesse histórico,
   sempre subordinado a `kobra.cumplimiento.puede_contactar` (horário legal,
   feriados, limites de frequência e a lista de Não Contatar têm a última
   palavra).
4. **Execução** por canal:
   - **Ligação**: Twilio, já integrado.
   - **WhatsApp**: Twilio WhatsApp API com **modelo de mensagem aprovado
     pela Meta** (`TWILIO_WHATSAPP_CONTENT_SID`) — é uma exigência da
     plataforma WhatsApp Business para iniciar uma conversa, não algo que se
     possa contornar por aqui.
   - **E-mail**: SMTP corporativo definido pelo cliente (`SMTP_HOST/USER/
     PASSWORD/FROM`), com modelo **customizável por faixa de atraso** (aba
     Configuração → "Modelos de e-mail por faixa de atraso").

É ativada/desativada pelo dashboard (Configuração → "Campanha automática de
contato") sem reiniciar o servidor; o scheduler verifica o estado a cada
execução (`CAMPANA_INTERVALO_MIN`, padrão 60 min). Requer `PUBLIC_BASE_URL`
(para o callback do Twilio) e um CSV com os contatos reais da carteira
(`id_deudor,telefono,email` — o dataset sintético da demo não traz contatos
reais de propósito).

```python
from kobra import campana as kcamp
plan = kcamp.plan_contacto_hoy(gestiones_df)          # prioridad + canal + horario + cumplimiento
telefonos, emails = kcamp.cargar_contactos("mi_cartera_contactos.csv")
kcamp.ejecutar_plan(plan, base_url="https://tu-servidor.com", telefonos=telefonos, emails=emails)
```

### 🤖 Assistente de ajuda dentro do programa — `kobra/ayuda.py`

Na aba **❓ Guia & Ajuda** há um assistente com IA que responde dúvidas sobre
o próprio produto ("como eu carrego minha carteira?", "o que eu preciso para
ligar de verdade?"), **em espanhol** e instantaneamente:

1. A busca de seções relevantes é feita por **TF-IDF local** sobre o README e
   os `docs/*.md` do produto — a documentação não é enviada a lugar nenhum.
2. Com `ANTHROPIC_API_KEY`, o Claude redige a resposta usando **apenas** esse
   contexto (mesmo critério de "zero invenção" do restante do produto: se a
   resposta não estiver na documentação, ele diz isso).
3. Sem chave de API, **não quebra**: mostra a seção exata da documentação que
   responde à dúvida, com sua fonte.

### 🏦 Motor de originação (credit decisioning) — `kobra/originacion.py`

Extensão upstream do mesmo motor: além de cobrar melhor, **decidir melhor
para quem emprestar**. Para cada solicitação de crédito, devolve
probabilidade de inadimplência, score 0-1000, decisão sugerida (Aprovar /
Encaminhar para análise / Recusar), valor e prazo sugeridos, **top 3 razões
em linguagem simples** e um nível de confiança conforme a quantidade de
dados reais recebidos — com dados insuficientes, nunca decide sozinho:
encaminha para um analista humano.

Padrões de ML do brief Kobra 2.0: validação **walk-forward temporal** (nunca
random split), **anti-SMOTE** (ponderação de amostras), benchmark honesto
contra a regra típica do analista de crédito, e explicabilidade por decisão
individual. API: `POST /api/originacion/score` e `GET /api/nba/{id_deudor}`
(next-best-action de cobrança). Estado completo do brief: `docs/KOBRA_2_0.md`.

### 🖥️ Plataforma web profissional (React) — `webapp/`

Além do dashboard Streamlit, há um **app web SaaS profissional** com os
mesmos dados e os mesmos motores — pensado para o cliente que espera uma
interface de produto comercial:

- **Backend** (`webapp/backend/api.py`, FastAPI): API REST com **JWT**
  (reutiliza as senhas admin/operador de `kobra/autenticacion.py`) e
  **multi-tenant por diretório** desde o primeiro dia: a empresa `principal`
  usa os dados do repositório; qualquer outra resolve para
  `data/tenants/<empresa>/`, com isolamento verificado por teste. Inclui
  **API de entrada para integradores** (`POST /api/integracion/cartera`): o
  core/ERP do cliente envia sua carteira como JSON, sem arquivos
  intermediários.
- **Frontend** (`webapp/frontend/`, React + Vite + Recharts): login, tour de
  boas-vindas, Visão geral (KPIs + 4 gráficos), Carteira priorizada com
  filtros/paginação/exportação e **briefing por devedor com roteiro
  sugerido**, Agenda de promessas vencidas, ranking de Operadores,
  **Assistente de IA** e Configuração de chaves (somente admin).

```bash
cd webapp/frontend && npm install && npm run build   # compila o frontend
python -m uvicorn webapp.backend.api:app --port 8800 # serve API + frontend
```

O dashboard Streamlit continua funcionando normalmente — os dois convivem
sobre os mesmos CSV/modelos; o app React é a cara comercial, o Streamlit é o
laboratório.

---

## 📁 Estrutura

```
Kobra/
├── data/generate_dataset.py        # gerador de carteira sintética (Uruguai)
├── kobra/
│   ├── probpago.py                 # modelo de probabilidade de pagamento
│   ├── negociador.py               # agente de IA negociador
│   ├── copiloto.py                 # copiloto de negociação ao vivo (sentimento)
│   ├── voz.py                      # diarização + emoção acústica de voz
│   ├── analitica.py                # analítica por operador / mês / faixa / segmento
│   ├── cumplimiento.py             # conformidade regulatória (horários, limites, não contatar)
│   ├── explicabilidad.py           # reason codes por devedor (por que essa ProbPago)
│   ├── roi.py                      # estimador de caso de negócio (ROI)
│   ├── integracion.py              # exportar/sincronizar a planilha consolidada para ERP/banco de dados
│   ├── consulta_bd.py              # NL2SQL: pergunte ao banco do cliente em espanhol
│   ├── cartera_manual.py           # carregar sua própria carteira de teste
│   ├── registro.py                 # briefing pré-ligação + registro pós-ligação
│   ├── seguimiento.py              # agenda: promessas/acordos vencidos sem pagamento
│   ├── voz_tts.py                  # voz premium opcional (ElevenLabs) — custo por caractere
│   ├── campana.py                  # campanha automática: canal/horário/prioridade + ligação/WhatsApp/e-mail
│   ├── twilio_setup.py             # auto-configurar número Twilio (buscar/comprar/webhook) via API
│   ├── ayuda.py                    # assistente de ajuda do produto (IA sobre a própria documentação)
│   ├── originacion.py              # motor de originação: score + decisão + razões ao originar
│   ├── config.py                   # chaves de API persistentes (Configuração)
│   ├── train.py                    # treinamento ML (seleção de modelos)
│   └── pipeline.py                 # orquestração end-to-end + exportações
├── realtime/                       # copiloto de áudio ao vivo (FastAPI + WebSocket)
├── webapp/                         # plataforma web profissional: backend FastAPI (JWT, multi-tenant) + frontend React
├── app/app.py                      # dashboard Streamlit (7 abas)
├── dashboard_estatico/             # dashboard + copiloto zero-install (offline)
├── presentation/build_ppt.py       # gerador de apresentação gerencial
├── tests/test_kobra.py             # testes do pipeline e do copiloto
├── referencia_R/                   # motor R original adaptado (referência)
├── .github/workflows/              # CI (testes) + treinamento ML programado
├── Dockerfile · docker-compose.yml # deploy (dashboard + realtime)
├── outputs/                        # CSV, Excel, JSON e modelo gerados
├── assets/                         # capturas de tela do dashboard
├── requirements.txt
└── run.sh
```

---

## ⚖️ Dados e legalidade

O dataset é **100% sintético**, gerado localmente e **sem nomes nem dados
pessoais de clientes reais**. O esquema é genérico: para usá-lo com uma
carteira real, basta respeitar as mesmas colunas (`data/generate_dataset.py`
documenta o esquema). Apto para demonstração comercial no Uruguai sem expor
informações sensíveis.

> Origem: o copiloto adapta e generaliza critérios de avaliação de
> atendimentos de um motor de referência de **autoria própria**
> (`referencia_R/`), sem marcas nem dados de terceiros.

# 📞 Guia: fazer uma ligação REAL com o Operador IA (Twilio)

_Tradução para o português brasileiro gerada por IA a partir do original em espanhol. Recomenda-se revisão por um falante nativo antes de uso comercial amplo._

O modo **"Probar mi cartera"** do dashboard *simula* a conversa. Para que o
Operador IA **fale de verdade** por telefone, o MV Kobra AI já traz o fluxo
completo: o bot **cumprimenta, escuta, negocia e fecha** usando o **TTS e o
reconhecimento de voz em espanhol da Twilio** — sem precisar instalar nada de
voz local.

Você precisa de duas coisas que não dependem do código:

1. **Uma conta Twilio** com um número.
2. **Consentimento** da pessoa para quem você vai ligar. Comece testando com
   **seu próprio celular**.

---

## Como funciona (já está implementado)

```
A Twilio liga para o número
   └─► pede o TwiML em  /voz/entrante   → o Operador IA cumprimenta (dentro do <Gather>)
        └─► a Twilio transcreve o que o cliente diz → POST /voz/turno
             └─► o Operador IA responde e negocia … (se repete)
                  └─► ao encerrar: registra o atendimento (aparece no dashboard)
```

Endpoints em `realtime/server.py`: `/voz/entrante`, `/voz/turno`,
`/voz/llamar` (dispara a ligação ativa) e **`/llamar`** (página com
formulário e botão, sem console).

---

## Passo a passo (primeira ligação para o seu próprio celular)

### 1. Criar conta na Twilio (grátis para testar)
- Cadastre-se em <https://www.twilio.com/try-twilio>. A conta **trial** dá
  crédito de teste e permite ligar **apenas para números verificados**:
  verifique seu próprio celular em *Verified Caller IDs*.
- Anote o **Account SID** e o **Auth Token** (Console → Account Info).

### 2. Carregar as credenciais no MV Kobra AI (sem código)
- No **dashboard → aba ⚙️ Configuração**, insira:
  `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`. Ficam salvas.

### 3. Conseguir um número e apontar seu webhook — com um botão
Em vez de ir ao Console da Twilio para comprar o número e configurar
manualmente seu webhook de voz, a seção **📞 Auto-configurar número Twilio**
(mesma aba Configuração, logo abaixo das chaves de API) faz isso por você:

- **"Comprar número novo"**: busca números disponíveis no seu país, você
  escolhe um e, ao comprá-lo, ele já fica **apontado** para `/voz/entrante`
  do seu servidor — sem precisar voltar ao Console. É salvo automaticamente
  como `TWILIO_FROM`.
- **"Já tenho um número"**: se você já comprou um número manualmente (ou já
  o tinha de antes), esta aba apenas atualiza o webhook de voz para o seu
  servidor.

> Requer que você já tenha `PUBLIC_BASE_URL` configurada no servidor (ver
> passo 4) — sem isso, não há para qual URL apontar o webhook. Comprar um
> número tem **custo real** (verifique a tarifa vigente antes de confirmar).

Se preferir fazer manualmente mesmo assim: Console → **Phone Numbers → Buy a
number** (com *Voice*), e na ficha do número, **Voice Configuration → "A
call comes in" → Webhook**, cole `https://seu-servidor/voz/entrante`
(método `HTTP POST`) — este é o passo que a maioria dos guias pula, e por
causa dele as ligações *recebidas* não chegam ao Operador IA mesmo que as
ligações ativas já funcionem.

### 4. Deixar o servidor acessível pela internet
A Twilio precisa alcançar seu servidor. Suba o backend de voz e exponha-o:

```bash
python -m realtime.server        # http://localhost:8000
ngrok http 8000                  # te dá https://XXXX.ngrok-free.app
```

> O servidor **detecta sozinho** a URL pública (pelos headers do ngrok); você
> não precisa configurá-la. Se preferir fixá-la, defina `PUBLIC_BASE_URL`.

### 5. Ligar — com um botão
- Abra **`https://XXXX.ngrok-free.app/llamar`** no navegador.
- Preencha: **telefone** (formato internacional, ex. `+59809XXXXXXX`), nome e
  **valor da dívida**. Toque em **📞 Llamar ahora** (Ligar agora).
- O Operador IA liga, negocia e, ao desligar, **registra o atendimento**
  (aparece no dashboard *Operadores & Evolução* como operador IA).

---

## Voz mais natural (opcional)
Por padrão, usa a voz padrão da Twilio em `es-MX`. Para uma voz neural
(Amazon Polly), defina a variável `TWILIO_TTS_VOICE`, por exemplo
`Polly.Mia-Neural` (verifique se sua conta tem essa voz habilitada). Você
também pode ajustar `TWILIO_TTS_LANG` / `TWILIO_ASR_LANG`.

## Custos aproximados (verifique as tarifas vigentes)
- **Trial**: crédito grátis para os primeiros testes.
- **Número**: ~USD 1–3/mês.
- **Minutos para o Uruguai**: da ordem de centavos de USD por minuto (móvel
  vs. fixo).
- **Claude (opcional)**: se você configurar `ANTHROPIC_API_KEY`, ele redige
  de forma mais natural (centavos por conversa); sem chave, usa modelos de
  texto prontos.

## Alternativa sem Twilio: sua central
Se a empresa já tem **Avaya / Asterisk / Genesys / Cisco**, não é preciso
Twilio: o conector `realtime/conector_avaya.py` recebe o RTP que a central
faz fork (SIPREC/DMCC). Ver o README, seção *Conector Avaya / SIPREC*.

---

> ⚖️ **Antes de ligar para terceiros**: certifique-se do consentimento e
> respeite o módulo de **conformidade** (`kobra/cumplimiento.py`): horários,
> limites de frequência e a lista de *Não Contatar*. Se, na ligação, o
> cliente disser "não me liguem mais", o Operador IA **registra isso
> sozinho** e não entra em contato novamente.

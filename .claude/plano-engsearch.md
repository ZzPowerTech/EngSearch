# EngSearch — Plano de Implementação Demonstrativo

> **Para trabalhadores agênticos:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para implementar este plano tarefa por tarefa. Os passos usam sintaxe de checkbox (`- [ ]`) para rastreamento.

**Objetivo:** Construir um robô inteligente que prospecta leads no setor de construção civil via LinkedIn e Instagram, extrai o link de WhatsApp da recepção presente nos perfis, inicia contato via WhatsApp com a recepção, envia o e-mail de apresentação quando solicitado, faz follow-up 24h depois cobrando agendamento e pedindo o contato técnico, e notifica o gestor da Neomot quando uma reunião é confirmada.

**Arquitetura:** O sistema opera em quatro camadas — (1) agente de prospecção com Claude Computer Use que navega Instagram/LinkedIn e extrai o link de WhatsApp da recepção, (2) bot WhatsApp "Neo" que conduz toda a cadeia de conversas com a recepção, (3) módulo de e-mail disparado sob demanda quando a recepção solicita, e (4) worker assíncrono que executa o follow-up 24h após o envio do e-mail e notifica o gestor ao agendar reunião.

**Tech Stack:** Python · Claude API (computer-use + claude-sonnet-4-6) · Supabase (PostgreSQL) · SendGrid · Twilio WhatsApp Business API · FastAPI · Next.js (dashboard) · Celery + Redis · Docker

---

## Contexto

O cliente é gestor da Neomot, empresa de venda de elevadores para o setor de construção civil. O projeto automatiza a prospecção e o funil de contato com construtoras, incorporadoras e escritórios de engenharia/arquitetura.

**Insight do cliente:** Praticamente todas as páginas de Instagram e LinkedIn dessas empresas já possuem um link de WhatsApp direto para a recepção — esse é o canal mais assertivo para o primeiro contato, porque a recepção irá naturalmente pedir o e-mail de apresentação, tornando a conversa orgânica e não intrusiva.

**Fluxo completo revisado:**

```
Instagram / LinkedIn
        │
        ▼  Claude Computer Use
  Agente Prospector
  ─ acessa o perfil da empresa
  ─ extrai o link wa.me/ ou botão WhatsApp
  ─ salva: empresa, número da recepção, URL do perfil
        │
        ▼  Twilio WhatsApp
  Bot "Neo" contata a recepção
  ─ apresenta a Neomot brevemente
  ─ aguarda a recepção solicitar o e-mail
        │
        ▼  (recepção pede e-mail)
  Bot envia o e-mail de apresentação (SendGrid)
  ─ e-mail personalizado por setor e empresa
        │
        ▼  Celery (24h depois)
  Follow-up automático via WhatsApp
  ─ "Bom dia! Verificou nosso e-mail?"
  ─ solicita agendamento de reunião
  ─ pede contato da área técnica (engenharia)
    ou suprimentos/compras
        │
        ├─ Lead agenda reunião
        │       ▼
        │  Reunião registrada no banco
        │  Notificação enviada ao WhatsApp
        │  do gestor Neomot
        │
        └─ Lead pede contato específico
                ▼
           Gestor Neomot notificado
           com nome e contato do responsável
```

---

## Status do Lead (pipeline completo)

```
discovered → reception_contacted → email_requested → email_sent
           → followup_sent → meeting_scheduled
                           → contact_requested (pediu área técnica/compras)
                           → lost
```

---

## Mapa de Arquivos

```
engsearch/
├── agents/
│   ├── prospector.py          # Claude Computer Use — extrai WhatsApp da recepção
│   ├── email_writer.py        # Gera e envia e-mail de apresentação sob demanda
│   └── whatsapp_bot.py        # Toda a lógica conversacional (recepção + follow-up)
├── api/
│   ├── main.py
│   └── routes/
│       ├── leads.py           # CRUD de leads
│       ├── campaigns.py       # Disparar prospecção e follow-ups
│       └── webhooks.py        # Recebe mensagens WhatsApp da recepção
├── db/
│   ├── schema.sql
│   └── client.py
├── tasks/
│   ├── celery_app.py
│   ├── prospect_task.py       # Task: rodar agente prospector
│   ├── reception_task.py      # Task: iniciar contato com recepção
│   ├── followup_task.py       # Task: follow-up 24h após e-mail enviado
│   └── notify_task.py         # Task: notificar gestor Neomot no WhatsApp
├── dashboard/
│   ├── app/
│   │   ├── page.tsx           # Métricas do pipeline
│   │   └── leads/page.tsx     # Lista de leads com status e timeline
│   └── components/
│       ├── LeadCard.tsx
│       ├── StatusBadge.tsx
│       └── ConversationTimeline.tsx
├── prompts/
│   ├── prospector_system.md   # Instruções do agente de prospecção
│   ├── reception_intro.md     # Script de abertura com a recepção
│   ├── email_template.md      # Template de e-mail de apresentação
│   ├── followup_script.md     # Script de follow-up 24h
│   └── notify_template.md     # Template de notificação ao gestor
├── tests/
│   ├── test_prospector.py
│   ├── test_email_writer.py
│   ├── test_whatsapp_bot.py
│   └── test_followup.py
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

---

## Fase 1 — Infraestrutura Base

### Tarefa 1: Schema do Banco de Dados

**Arquivos:**
- Criar: `db/schema.sql`
- Criar: `db/client.py`

- [ ] **Passo 1: Escrever o teste de conexão**

```python
# tests/test_db.py
def test_supabase_connection():
    from db.client import get_client
    client = get_client()
    result = client.table("leads").select("id").limit(1).execute()
    assert result is not None
```

- [ ] **Passo 2: Criar o schema SQL**

```sql
-- db/schema.sql
CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa TEXT NOT NULL,
    segmento TEXT CHECK (segmento IN ('construtora','incorporadora','escritorio_eng','escritorio_arq','outro')),
    whatsapp_recepcao TEXT,        -- número extraído do Instagram/LinkedIn
    email_corporativo TEXT,        -- preenchido após recepção confirmar
    contato_tecnico TEXT,          -- engenharia / suprimentos (coletado no follow-up)
    cargo_contato_tecnico TEXT,
    instagram_url TEXT,
    linkedin_url TEXT,
    status TEXT DEFAULT 'discovered' CHECK (status IN (
        'discovered',
        'reception_contacted',
        'email_requested',
        'email_sent',
        'followup_sent',
        'contact_requested',
        'meeting_scheduled',
        'lost'
    )),
    notas TEXT,
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE interacoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    canal TEXT NOT NULL CHECK (canal IN ('whatsapp','email','sistema')),
    direcao TEXT NOT NULL CHECK (direcao IN ('enviado','recebido')),
    conteudo TEXT NOT NULL,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE reunioes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    data_hora TIMESTAMPTZ,
    formato TEXT CHECK (formato IN ('presencial','video','a_definir')),
    contato_confirmado TEXT,       -- nome/número que confirmou
    status TEXT DEFAULT 'agendada' CHECK (status IN ('agendada','confirmada','realizada','cancelada')),
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Índice para busca por número de WhatsApp
CREATE INDEX idx_leads_whatsapp ON leads(whatsapp_recepcao);
```

- [ ] **Passo 3: Criar o cliente Supabase**

```python
# db/client.py
import os
from supabase import create_client, Client

def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)
```

- [ ] **Passo 4: Rodar o teste**

```bash
pytest tests/test_db.py -v
```
Esperado: PASS

- [ ] **Passo 5: Commit**

```bash
git add db/ tests/test_db.py
git commit -m "feat: schema banco com pipeline de status completo"
```

---

## Fase 2 — Agente Prospector (Claude Computer Use)

### Tarefa 2: Extração do WhatsApp da recepção via Instagram/LinkedIn

**Arquivos:**
- Criar: `prompts/prospector_system.md`
- Criar: `agents/prospector.py`

- [ ] **Passo 1: Criar o system prompt do prospector**

```markdown
<!-- prompts/prospector_system.md -->
Você é o EngSearch Prospector. Sua missão é acessar perfis de empresas
no Instagram e LinkedIn do setor de construção civil e extrair o número
de WhatsApp da recepção/contato comercial.

## O que buscar
- Construtoras, incorporadoras, escritórios de engenharia e arquitetura
- Foco em empresas que constroem edifícios residenciais ou comerciais

## Como operar no Instagram
1. Acesse o perfil da empresa
2. Na bio, procure por: botão "Contato", link wa.me/, link linktr.ee/
3. Se houver Linktree, acesse e procure o link de WhatsApp
4. Anote o número no formato internacional: 5511999999999

## Como operar no LinkedIn
1. Acesse a página da empresa
2. Vá em "Contato" ou "Sobre"
3. Procure por número de telefone ou link WhatsApp

## Formato de saída (JSON por empresa)
{
  "empresa": "Nome da Empresa",
  "segmento": "construtora|incorporadora|escritorio_eng|escritorio_arq",
  "whatsapp_recepcao": "5511999999999",
  "instagram_url": "https://instagram.com/empresa",
  "linkedin_url": "https://linkedin.com/company/empresa ou null"
}

## Regras
- SÓ extraia número se tiver certeza que é WhatsApp comercial/recepção
- Se não encontrar WhatsApp, retorne whatsapp_recepcao: null
- NÃO invente números — se não encontrou, deixe null
```

- [ ] **Passo 2: Escrever o teste**

```python
# tests/test_prospector.py
from agents.prospector import ProspectorAgent

def test_parse_lead_com_whatsapp():
    agent = ProspectorAgent()
    raw = {
        "empresa": "Construtora Silva",
        "segmento": "construtora",
        "whatsapp_recepcao": "5511998887766",
        "instagram_url": "https://instagram.com/construtorasilva",
        "linkedin_url": None
    }
    lead = agent.parse_lead(raw)
    assert lead["status"] == "discovered"
    assert lead["whatsapp_recepcao"] == "5511998887766"

def test_parse_lead_sem_whatsapp():
    agent = ProspectorAgent()
    raw = {
        "empresa": "Incorporadora X",
        "segmento": "incorporadora",
        "whatsapp_recepcao": None,
        "instagram_url": "https://instagram.com/incorporadorax",
        "linkedin_url": None
    }
    lead = agent.parse_lead(raw)
    assert lead["whatsapp_recepcao"] is None
    assert lead["status"] == "discovered"
```

- [ ] **Passo 3: Implementar o ProspectorAgent**

```python
# agents/prospector.py
import anthropic
import json
from pathlib import Path
from db.client import get_client

class ProspectorAgent:
    def __init__(self):
        self.client = anthropic.Anthropic()
        self.system_prompt = Path("prompts/prospector_system.md").read_text()
        self.db = get_client()

    def parse_lead(self, raw: dict) -> dict:
        return {**raw, "status": "discovered"}

    def prospect(self, search_term: str, platform: str = "instagram", max_leads: int = 15) -> list[dict]:
        leads = []
        messages = [{
            "role": "user",
            "content": (
                f"Pesquise no {platform} por '{search_term}'. "
                f"Para cada empresa encontrada, acesse o perfil e extraia o número de WhatsApp da recepção. "
                f"Colete até {max_leads} empresas. Retorne um array JSON ao final."
            )
        }]

        while True:
            response = self.client.beta.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=self.system_prompt,
                tools=[{
                    "type": "computer_20250124",
                    "name": "computer",
                    "display_width_px": 1280,
                    "display_height_px": 800
                }],
                messages=messages,
                betas=["computer-use-2025-01-24"]
            )

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        try:
                            data = json.loads(block.text)
                            if isinstance(data, list):
                                leads.extend([self.parse_lead(l) for l in data])
                        except json.JSONDecodeError:
                            pass
                break

            # Processar tool_use e continuar
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": ""
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            if len(leads) >= max_leads:
                break

        return leads[:max_leads]

    def save_leads(self, leads: list[dict]) -> int:
        saved = 0
        for lead in leads:
            # Só salva se tem WhatsApp — sem ele não há como iniciar contato
            if not lead.get("whatsapp_recepcao"):
                continue
            result = self.db.table("leads").upsert(
                lead, on_conflict="instagram_url"
            ).execute()
            if result.data:
                saved += 1
        return saved
```

- [ ] **Passo 4: Rodar os testes**

```bash
pytest tests/test_prospector.py -v
```
Esperado: 2 testes PASS

- [ ] **Passo 5: Commit**

```bash
git add agents/prospector.py prompts/prospector_system.md tests/test_prospector.py
git commit -m "feat: prospector extrai WhatsApp da recepção via Instagram/LinkedIn"
```

---

## Fase 3 — Bot WhatsApp: Contato com a Recepção

### Tarefa 3: Primeiro contato e envio de e-mail sob demanda

**Arquivos:**
- Criar: `prompts/reception_intro.md`
- Criar: `prompts/email_template.md`
- Criar: `agents/email_writer.py`
- Criar: `agents/whatsapp_bot.py`

- [ ] **Passo 1: Criar o script de abertura com a recepção**

```markdown
<!-- prompts/reception_intro.md -->
Você é "Neo", assistente comercial da Neomot, empresa especializada em
elevadores para edifícios residenciais e comerciais.

## Missão
Você está entrando em contato com a recepção de uma construtora ou escritório
de engenharia. Seu objetivo é:
1. Se apresentar brevemente e de forma simpática
2. Aguardar a recepção pedir o e-mail de apresentação (eles sempre pedem)
3. Confirmar o e-mail para envio
4. Informar que o e-mail foi enviado e que voltará em breve

## Regras de Ouro
- Mensagens CURTAS — máximo 2 linhas no WhatsApp
- Tom: cordial, profissional, nunca invasivo
- NÃO force o assunto — deixe a recepção conduzir naturalmente
- Se a recepção pedir para ligar depois → registre e encerre educadamente
- Se perguntada se é robô → "Sou o assistente digital da Neomot,
  mas qualquer dúvida conecto você com nosso time!"

## Estados da conversa
- ABERTURA: primeiro contato, aguardando resposta
- AGUARDANDO_EMAIL: recepção pediu e-mail, coletando o endereço
- EMAIL_CONFIRMADO: e-mail coletado, aguardando confirmação antes de enviar
- ENCERRADO: e-mail enviado, conversa finalizada com sucesso

## Saída JSON por mensagem
{
  "mensagem": "texto da resposta",
  "novo_estado": "ABERTURA|AGUARDANDO_EMAIL|EMAIL_CONFIRMADO|ENCERRADO",
  "email_coletado": "email@empresa.com ou null"
}
```

- [ ] **Passo 2: Criar o template do e-mail de apresentação**

```markdown
<!-- prompts/email_template.md -->
Você é redator especialista em e-mails B2B para construção civil.
Escreva um e-mail de apresentação profissional para a empresa abaixo.

## Remetente
Empresa: Neomot
Produto: Elevadores para edifícios residenciais e comerciais
Diferencial: Projeto, fornecimento, instalação e manutenção com suporte técnico especializado

## Regras
- Máximo 180 palavras no corpo
- Mencione o segmento da empresa para mostrar personalização
- Foco em benefícios: agilidade na obra, conformidade com normas, suporte pós-obra
- CTA claro: "Podemos agendar uma conversa rápida com seu time técnico ou de suprimentos?"
- Tom: profissional e direto, nunca genérico
- Assunto: objetivo, sem clickbait

## Saída (JSON)
{"assunto": "...", "corpo": "..."}
```

- [ ] **Passo 3: Escrever testes do bot e do e-mail**

```python
# tests/test_whatsapp_bot.py
from unittest.mock import patch, MagicMock
from agents.whatsapp_bot import WhatsappBot

def test_mensagem_abertura():
    bot = WhatsappBot()
    lead = {"empresa": "Construtora Silva", "whatsapp_recepcao": "5511999999999"}
    msg = bot.gerar_abertura(lead)
    assert len(msg) > 0

def test_resposta_quando_recepcao_pede_email():
    bot = WhatsappBot()
    lead = {"empresa": "Construtora Silva", "whatsapp_recepcao": "5511999999999"}
    historico = [{"role": "assistant", "content": "Olá! Sou Neo, da Neomot..."}]
    mensagem_recepcao = "Pode mandar o e-mail para contato@construtora.com"
    with patch.object(bot.claude, "messages") as mock:
        mock.create.return_value = MagicMock(
            content=[MagicMock(text='{"mensagem": "Perfeito!", "novo_estado": "EMAIL_CONFIRMADO", "email_coletado": "contato@construtora.com"}')]
        )
        resposta = bot.responder_recepcao(lead, historico, mensagem_recepcao)
    assert resposta["email_coletado"] == "contato@construtora.com"
    assert resposta["novo_estado"] == "EMAIL_CONFIRMADO"
```

```python
# tests/test_email_writer.py
from unittest.mock import patch, MagicMock
from agents.email_writer import EmailWriter

def test_gera_email_para_construtora():
    writer = EmailWriter()
    lead = {"empresa": "Construtora Mendes", "segmento": "construtora"}
    with patch.object(writer.claude, "messages") as mock:
        mock.create.return_value = MagicMock(
            content=[MagicMock(text='{"assunto": "Elevadores para a Mendes", "corpo": "Prezados..."}')]
        )
        email = writer.gerar_email(lead)
    assert "assunto" in email
    assert "corpo" in email

def test_nao_envia_sem_destinatario():
    writer = EmailWriter()
    lead = {"empresa": "X", "segmento": "construtora", "email_corporativo": None}
    assert writer.pode_enviar(lead) is False
```

- [ ] **Passo 4: Implementar o EmailWriter**

```python
# agents/email_writer.py
import anthropic
import json
import os
from pathlib import Path
import sendgrid
from sendgrid.helpers.mail import Mail

class EmailWriter:
    def __init__(self):
        self.claude = anthropic.Anthropic()
        self.sg = sendgrid.SendGridAPIClient(os.environ["SENDGRID_API_KEY"])
        self.remetente = os.environ["EMAIL_REMETENTE"]
        self.system_prompt = Path("prompts/email_template.md").read_text()

    def pode_enviar(self, lead: dict) -> bool:
        return bool(lead.get("email_corporativo"))

    def gerar_email(self, lead: dict) -> dict:
        response = self.claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=self.system_prompt,
            messages=[{"role": "user", "content": f"Empresa: {lead['empresa']}, Segmento: {lead.get('segmento', 'construção civil')}"}]
        )
        return json.loads(response.content[0].text)

    def enviar(self, lead: dict) -> bool:
        if not self.pode_enviar(lead):
            return False
        email_data = self.gerar_email(lead)
        message = Mail(
            from_email=self.remetente,
            to_emails=lead["email_corporativo"],
            subject=email_data["assunto"],
            plain_text_content=email_data["corpo"]
        )
        response = self.sg.send(message)
        return response.status_code == 202
```

- [ ] **Passo 5: Implementar o WhatsappBot**

```python
# agents/whatsapp_bot.py
import anthropic
import json
import os
from pathlib import Path
from db.client import get_client
from twilio.rest import Client as TwilioClient

class WhatsappBot:
    def __init__(self):
        self.claude = anthropic.Anthropic()
        self.reception_prompt = Path("prompts/reception_intro.md").read_text()
        self.followup_prompt = Path("prompts/followup_script.md").read_text()
        self.db = get_client()
        self.twilio = TwilioClient(
            os.environ["TWILIO_ACCOUNT_SID"],
            os.environ["TWILIO_AUTH_TOKEN"]
        )
        self.numero_neomot = os.environ["WHATSAPP_FROM"]

    def gerar_abertura(self, lead: dict) -> str:
        response = self.claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            system=self.reception_prompt,
            messages=[{
                "role": "user",
                "content": f"Inicie o contato com a recepção da empresa '{lead['empresa']}' ({lead.get('segmento', 'construção civil')}). Gere apenas a primeira mensagem."
            }]
        )
        data = json.loads(response.content[0].text)
        return data["mensagem"]

    def responder_recepcao(self, lead: dict, historico: list, mensagem: str) -> dict:
        messages = historico + [{"role": "user", "content": f"Recepção diz: {mensagem}"}]
        response = self.claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=self.reception_prompt,
            messages=messages
        )
        return json.loads(response.content[0].text)

    def responder_followup(self, lead: dict, historico: list, mensagem: str) -> dict:
        messages = historico + [{"role": "user", "content": f"Lead diz: {mensagem}"}]
        response = self.claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=self.followup_prompt,
            messages=messages
        )
        return json.loads(response.content[0].text)

    def enviar_whatsapp(self, numero: str, texto: str) -> bool:
        try:
            self.twilio.messages.create(
                from_=f"whatsapp:{self.numero_neomot}",
                to=f"whatsapp:{numero}",
                body=texto
            )
            return True
        except Exception:
            return False

    def salvar_reuniao(self, lead_id: str, dados: dict) -> bool:
        result = self.db.table("reunioes").insert({
            "lead_id": lead_id,
            "data_hora": dados.get("data_hora"),
            "formato": dados.get("formato", "a_definir"),
            "contato_confirmado": dados.get("contato_confirmado")
        }).execute()
        if result.data:
            self.db.table("leads").update({"status": "meeting_scheduled"}).eq("id", lead_id).execute()
            return True
        return False
```

- [ ] **Passo 6: Rodar os testes**

```bash
pytest tests/test_whatsapp_bot.py tests/test_email_writer.py -v
```
Esperado: 4 testes PASS

- [ ] **Passo 7: Commit**

```bash
git add agents/ prompts/reception_intro.md prompts/email_template.md tests/
git commit -m "feat: bot WhatsApp para recepção + e-mail sob demanda"
```

---

## Fase 4 — Follow-up 24h + Notificação ao Gestor

### Tarefa 4: Follow-up automático e notificação

**Arquivos:**
- Criar: `prompts/followup_script.md`
- Criar: `prompts/notify_template.md`
- Criar: `tasks/followup_task.py`
- Criar: `tasks/notify_task.py`

- [ ] **Passo 1: Criar o script de follow-up**

```markdown
<!-- prompts/followup_script.md -->
Você é "Neo", assistente da Neomot. Você está fazendo follow-up via WhatsApp
com alguém de uma construtora/incorporadora que recebeu nosso e-mail de apresentação
24 horas atrás.

## Missão
1. Verificar se o e-mail foi recebido e lido
2. Propor agendamento de uma reunião rápida (15-20 min)
3. Perguntar com qual área interna falar:
   → Área técnica / Engenharia
   → Suprimentos / Compras
4. Se a pessoa fornecer um contato específico, registrar e encerrar

## Regras
- Mensagens CURTAS — máximo 3 linhas
- Não seja insistente se a resposta for negativa — encerre com elegância
- Se disser que não é a pessoa certa → peça para indicar o responsável
- Tom: leve, sem pressão, profissional

## Estados
- FOLLOWUP_ABERTO: primeiro follow-up enviado
- AGENDANDO: em processo de coleta de data/hora da reunião
- PEDINDO_CONTATO: pedindo o nome do responsável técnico/compras
- REUNIAO_AGENDADA: reunião confirmada — registrar dados
- CONTATO_COLETADO: responsável técnico ou de compras identificado
- ENCERRADO_SEM_INTERESSE: lead sem interesse no momento

## Saída JSON
{
  "mensagem": "texto da resposta",
  "novo_estado": "FOLLOWUP_ABERTO|AGENDANDO|PEDINDO_CONTATO|REUNIAO_AGENDADA|CONTATO_COLETADO|ENCERRADO_SEM_INTERESSE",
  "dados_reuniao": {"data_hora": null, "formato": null, "contato_confirmado": null},
  "contato_tecnico": {"nome": null, "cargo": null, "whatsapp": null}
}
```

- [ ] **Passo 2: Criar o template de notificação ao gestor**

```markdown
<!-- prompts/notify_template.md -->
Você formata mensagens de notificação para o gestor comercial da Neomot via WhatsApp.
As mensagens devem ser claras, objetivas e incluir os dados relevantes.

## Tipos de notificação

### REUNIAO_AGENDADA
"✅ *Nova reunião agendada!*
Empresa: {empresa}
Data/Hora: {data_hora}
Formato: {formato}
Confirmado por: {contato_confirmado}"

### CONTATO_TECNICO_COLETADO
"📋 *Contato técnico identificado!*
Empresa: {empresa}
Responsável: {nome} ({cargo})
WhatsApp: {whatsapp}
Próximo passo: entrar em contato diretamente"

### LEAD_SEM_INTERESSE
"ℹ️ Lead sem interesse no momento
Empresa: {empresa}
Observação: {motivo}"
```

- [ ] **Passo 3: Escrever o teste do follow-up**

```python
# tests/test_followup.py
from unittest.mock import patch, MagicMock
from agents.whatsapp_bot import WhatsappBot

def test_followup_coleta_contato_tecnico():
    bot = WhatsappBot()
    lead = {"empresa": "Construtora Silva", "id": "uuid-123"}
    historico = [
        {"role": "assistant", "content": "Bom dia! Conseguiu ver nosso e-mail?"},
        {"role": "user", "content": "Vi sim, mas quem cuida disso aqui é o eng. Carlos, 11 98765-4321"}
    ]
    with patch.object(bot.claude, "messages") as mock:
        mock.create.return_value = MagicMock(content=[MagicMock(text=json.dumps({
            "mensagem": "Ótimo! Anotei o contato do eng. Carlos, obrigado!",
            "novo_estado": "CONTATO_COLETADO",
            "dados_reuniao": {"data_hora": None, "formato": None, "contato_confirmado": None},
            "contato_tecnico": {"nome": "Carlos", "cargo": "Engenheiro", "whatsapp": "5511987654321"}
        }))])
        import json
        resposta = bot.responder_followup(lead, historico, "Vi sim, eng. Carlos 11 98765-4321")
    assert resposta["novo_estado"] == "CONTATO_COLETADO"
    assert resposta["contato_tecnico"]["nome"] == "Carlos"
```

- [ ] **Passo 4: Implementar a task de follow-up**

```python
# tasks/followup_task.py
from tasks.celery_app import app
from agents.whatsapp_bot import WhatsappBot
from agents.email_writer import EmailWriter
from db.client import get_client

@app.task(bind=True, max_retries=2)
def iniciar_followup(self, lead_id: str):
    """Executada 24h após o e-mail ser enviado."""
    db = get_client()
    bot = WhatsappBot()
    try:
        lead = db.table("leads").select("*").eq("id", lead_id).single().execute().data
        if lead["status"] != "email_sent":
            return {"status": "ignorado", "motivo": f"status atual: {lead['status']}"}

        mensagem = (
            f"Bom dia! 😊 Sou o Neo, da Neomot. "
            f"Enviamos um e-mail ontem para {lead['email_corporativo']} — conseguiu dar uma olhada? "
            f"Podemos bater um papo rápido com sua equipe técnica ou de compras?"
        )
        enviado = bot.enviar_whatsapp(lead["whatsapp_recepcao"], mensagem)
        if enviado:
            db.table("leads").update({"status": "followup_sent"}).eq("id", lead_id).execute()
            db.table("interacoes").insert({
                "lead_id": lead_id, "canal": "whatsapp",
                "direcao": "enviado", "conteudo": mensagem
            }).execute()
        return {"status": "enviado" if enviado else "falha"}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)
```

- [ ] **Passo 5: Implementar a task de notificação ao gestor**

```python
# tasks/notify_task.py
import os
from tasks.celery_app import app
from twilio.rest import Client as TwilioClient

@app.task
def notificar_gestor(tipo: str, dados: dict):
    """Notifica o WhatsApp principal do gestor Neomot."""
    twilio = TwilioClient(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    numero_gestor = os.environ["WHATSAPP_GESTOR"]
    numero_neomot = os.environ["WHATSAPP_FROM"]

    templates = {
        "REUNIAO_AGENDADA": (
            "✅ *Nova reunião agendada!*\n"
            "Empresa: {empresa}\n"
            "Data/Hora: {data_hora}\n"
            "Formato: {formato}\n"
            "Confirmado por: {contato_confirmado}"
        ),
        "CONTATO_TECNICO_COLETADO": (
            "📋 *Contato técnico identificado!*\n"
            "Empresa: {empresa}\n"
            "Responsável: {nome} ({cargo})\n"
            "WhatsApp: {whatsapp}\n"
            "Próximo passo: entrar em contato diretamente"
        ),
        "LEAD_SEM_INTERESSE": (
            "ℹ️ Lead sem interesse no momento\n"
            "Empresa: {empresa}\n"
            "Observação: {motivo}"
        )
    }

    template = templates.get(tipo, "Notificação EngSearch: {empresa}")
    mensagem = template.format(**dados)

    twilio.messages.create(
        from_=f"whatsapp:{numero_neomot}",
        to=f"whatsapp:{numero_gestor}",
        body=mensagem
    )
```

- [ ] **Passo 6: Rodar os testes**

```bash
pytest tests/test_followup.py -v
```
Esperado: PASS

- [ ] **Passo 7: Commit**

```bash
git add prompts/followup_script.md prompts/notify_template.md tasks/followup_task.py tasks/notify_task.py tests/test_followup.py
git commit -m "feat: follow-up 24h + notificação ao gestor via WhatsApp"
```

---

## Fase 5 — Webhook WhatsApp (Recebimento de Mensagens)

### Tarefa 5: Roteamento inteligente por fase do lead

**Arquivos:**
- Criar: `api/routes/webhooks.py`

- [ ] **Passo 1: Implementar o webhook com roteamento por status**

```python
# api/routes/webhooks.py
from fastapi import APIRouter, Form
from agents.whatsapp_bot import WhatsappBot
from agents.email_writer import EmailWriter
from tasks.followup_task import iniciar_followup
from tasks.notify_task import notificar_gestor
from db.client import get_client

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
bot = WhatsappBot()
email_writer = EmailWriter()

@router.post("/whatsapp")
async def receber_whatsapp(From: str = Form(...), Body: str = Form(...)):
    numero = From.replace("whatsapp:", "")
    db = get_client()

    lead_result = db.table("leads").select("*").eq("whatsapp_recepcao", numero).maybe_single().execute()
    if not lead_result.data:
        return {"status": "lead_nao_encontrado"}

    lead = lead_result.data
    lead_id = lead["id"]

    # Buscar histórico do canal WhatsApp
    hist_result = db.table("interacoes").select("*").eq("lead_id", lead_id).eq("canal", "whatsapp").order("criado_em").execute()
    historico = [
        {"role": "assistant" if i["direcao"] == "enviado" else "user", "content": i["conteudo"]}
        for i in hist_result.data
    ]

    # Registrar mensagem recebida
    db.table("interacoes").insert({
        "lead_id": lead_id, "canal": "whatsapp", "direcao": "recebido", "conteudo": Body
    }).execute()

    # ── FASE DE RECEPÇÃO (antes do e-mail ser enviado) ──────────────────────
    if lead["status"] in ("reception_contacted", "email_requested"):
        resposta = bot.responder_recepcao(lead, historico, Body)

        # Recepção forneceu o e-mail
        if resposta.get("email_coletado"):
            db.table("leads").update({
                "email_corporativo": resposta["email_coletado"],
                "status": "email_requested"
            }).eq("id", lead_id).execute()
            lead["email_corporativo"] = resposta["email_coletado"]

        # Confirmar e enviar e-mail
        if resposta["novo_estado"] == "EMAIL_CONFIRMADO" and lead.get("email_corporativo"):
            enviado = email_writer.enviar(lead)
            if enviado:
                db.table("leads").update({"status": "email_sent"}).eq("id", lead_id).execute()
                db.table("interacoes").insert({
                    "lead_id": lead_id, "canal": "email", "direcao": "enviado",
                    "conteudo": f"E-mail de apresentação enviado para {lead['email_corporativo']}"
                }).execute()
                # Agendar follow-up para 24h depois
                iniciar_followup.apply_async(args=[lead_id], countdown=86400)

        if resposta["novo_estado"] == "ENCERRADO":
            db.table("leads").update({"status": "email_sent"}).eq("id", lead_id).execute()

    # ── FASE DE FOLLOW-UP (após e-mail enviado) ─────────────────────────────
    elif lead["status"] in ("email_sent", "followup_sent"):
        resposta = bot.responder_followup(lead, historico, Body)

        if resposta["novo_estado"] == "REUNIAO_AGENDADA":
            dados = resposta["dados_reuniao"]
            bot.salvar_reuniao(lead_id, dados)
            notificar_gestor.delay("REUNIAO_AGENDADA", {
                "empresa": lead["empresa"],
                "data_hora": dados.get("data_hora", "a definir"),
                "formato": dados.get("formato", "a definir"),
                "contato_confirmado": dados.get("contato_confirmado", "recepção")
            })

        elif resposta["novo_estado"] == "CONTATO_COLETADO":
            ct = resposta["contato_tecnico"]
            db.table("leads").update({
                "contato_tecnico": ct.get("whatsapp"),
                "cargo_contato_tecnico": ct.get("cargo"),
                "status": "contact_requested"
            }).eq("id", lead_id).execute()
            notificar_gestor.delay("CONTATO_TECNICO_COLETADO", {
                "empresa": lead["empresa"],
                "nome": ct.get("nome", "N/A"),
                "cargo": ct.get("cargo", "N/A"),
                "whatsapp": ct.get("whatsapp", "N/A")
            })

        elif resposta["novo_estado"] == "ENCERRADO_SEM_INTERESSE":
            db.table("leads").update({"status": "lost"}).eq("id", lead_id).execute()
            notificar_gestor.delay("LEAD_SEM_INTERESSE", {
                "empresa": lead["empresa"],
                "motivo": Body[:200]
            })

    else:
        return {"status": "status_nao_tratado", "lead_status": lead["status"]}

    # Enviar resposta para o lead
    bot.enviar_whatsapp(numero, resposta["mensagem"])

    # Registrar resposta enviada
    db.table("interacoes").insert({
        "lead_id": lead_id, "canal": "whatsapp", "direcao": "enviado",
        "conteudo": resposta["mensagem"]
    }).execute()

    return {"status": "ok"}
```

- [ ] **Passo 2: Commit**

```bash
git add api/routes/webhooks.py
git commit -m "feat: webhook WhatsApp com roteamento por fase do pipeline"
```

---

## Fase 6 — Tarefas Assíncronas e Campanhas

### Tarefa 6: Celery + rotas de campanha

**Arquivos:**
- Criar: `tasks/celery_app.py`
- Criar: `tasks/prospect_task.py`
- Criar: `tasks/reception_task.py`
- Criar: `api/routes/campaigns.py`

- [ ] **Passo 1: Configurar Celery**

```python
# tasks/celery_app.py
import os
from celery import Celery

app = Celery(
    "engsearch",
    broker=os.environ["REDIS_URL"],
    backend=os.environ["REDIS_URL"],
    include=[
        "tasks.prospect_task",
        "tasks.reception_task",
        "tasks.followup_task",
        "tasks.notify_task"
    ]
)
app.conf.timezone = "America/Sao_Paulo"
```

- [ ] **Passo 2: Task de prospecção**

```python
# tasks/prospect_task.py
from tasks.celery_app import app
from agents.prospector import ProspectorAgent

@app.task(bind=True, max_retries=2)
def prospectar(self, search_term: str, platform: str = "instagram", max_leads: int = 15):
    try:
        agent = ProspectorAgent()
        leads = agent.prospect(search_term, platform, max_leads)
        saved = agent.save_leads(leads)
        return {"leads_encontrados": len(leads), "leads_salvos": saved}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)
```

- [ ] **Passo 3: Task de contato com a recepção**

```python
# tasks/reception_task.py
from tasks.celery_app import app
from agents.whatsapp_bot import WhatsappBot
from db.client import get_client

@app.task(bind=True, max_retries=2)
def contatar_recepcao(self, lead_id: str):
    """Envia a mensagem de abertura para a recepção via WhatsApp."""
    db = get_client()
    bot = WhatsappBot()
    try:
        lead = db.table("leads").select("*").eq("id", lead_id).single().execute().data
        if lead["status"] != "discovered":
            return {"status": "ignorado"}
        if not lead.get("whatsapp_recepcao"):
            return {"status": "sem_whatsapp"}

        mensagem = bot.gerar_abertura(lead)
        enviado = bot.enviar_whatsapp(lead["whatsapp_recepcao"], mensagem)

        if enviado:
            db.table("leads").update({"status": "reception_contacted"}).eq("id", lead_id).execute()
            db.table("interacoes").insert({
                "lead_id": lead_id, "canal": "whatsapp",
                "direcao": "enviado", "conteudo": mensagem
            }).execute()
        return {"status": "enviado" if enviado else "falha"}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
```

- [ ] **Passo 4: Rotas de campanha**

```python
# api/routes/campaigns.py
from fastapi import APIRouter
from tasks.prospect_task import prospectar
from tasks.reception_task import contatar_recepcao
from db.client import get_client

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

@router.post("/prospect")
async def iniciar_prospeccao(termo: str, plataforma: str = "instagram", max_leads: int = 15):
    task = prospectar.delay(termo, plataforma, max_leads)
    return {"task_id": task.id, "status": "iniciado"}

@router.post("/contact-all")
async def contatar_todos_leads():
    """Dispara contato com todas as recepções que ainda não foram contatadas."""
    db = get_client()
    leads = db.table("leads").select("id").eq("status", "discovered").execute().data
    for lead in leads:
        contatar_recepcao.delay(lead["id"])
    return {"leads_em_fila": len(leads)}
```

- [ ] **Passo 5: Commit**

```bash
git add tasks/ api/routes/campaigns.py
git commit -m "feat: Celery tasks para prospecção, recepção e follow-up"
```

---

## Fase 7 — Dashboard do Gestor (Next.js)

### Tarefa 7: Painel com pipeline visual

**Arquivos:**
- Criar: `dashboard/components/StatusBadge.tsx`
- Criar: `dashboard/components/LeadCard.tsx`
- Criar: `dashboard/app/page.tsx`
- Criar: `dashboard/app/leads/page.tsx`

- [ ] **Passo 1: StatusBadge com todos os status do pipeline**

```tsx
// dashboard/components/StatusBadge.tsx
const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  discovered:           { label: "Encontrado",             color: "bg-gray-100 text-gray-700" },
  reception_contacted:  { label: "Recepção Contatada",     color: "bg-blue-100 text-blue-700" },
  email_requested:      { label: "E-mail Solicitado",      color: "bg-yellow-100 text-yellow-700" },
  email_sent:           { label: "E-mail Enviado",         color: "bg-orange-100 text-orange-700" },
  followup_sent:        { label: "Follow-up Enviado",      color: "bg-purple-100 text-purple-700" },
  contact_requested:    { label: "Contato Técnico",        color: "bg-indigo-100 text-indigo-700" },
  meeting_scheduled:    { label: "Reunião Agendada ✓",     color: "bg-green-100 text-green-700" },
  lost:                 { label: "Sem Interesse",          color: "bg-red-100 text-red-700" },
}

export function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, color: "bg-gray-100 text-gray-700" }
  return (
    <span className={`text-xs font-medium px-2 py-1 rounded-full ${cfg.color}`}>
      {cfg.label}
    </span>
  )
}
```

- [ ] **Passo 2: LeadCard**

```tsx
// dashboard/components/LeadCard.tsx
import { StatusBadge } from "./StatusBadge"

type Lead = {
  id: string; empresa: string; segmento: string
  whatsapp_recepcao: string | null; email_corporativo: string | null
  contato_tecnico: string | null; cargo_contato_tecnico: string | null
  status: string; criado_em: string
}

export function LeadCard({ lead }: { lead: Lead }) {
  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm space-y-2">
      <div className="flex justify-between items-start">
        <div>
          <h3 className="font-semibold text-gray-900">{lead.empresa}</h3>
          <p className="text-sm text-gray-500 capitalize">{lead.segmento?.replace("_", " ")}</p>
        </div>
        <StatusBadge status={lead.status} />
      </div>
      <div className="text-sm text-gray-600 space-y-1">
        {lead.whatsapp_recepcao && <p>📱 Recepção: {lead.whatsapp_recepcao}</p>}
        {lead.email_corporativo  && <p>✉️ {lead.email_corporativo}</p>}
        {lead.contato_tecnico    && <p>🔧 {lead.cargo_contato_tecnico}: {lead.contato_tecnico}</p>}
      </div>
    </div>
  )
}
```

- [ ] **Passo 3: Dashboard de métricas**

```tsx
// dashboard/app/page.tsx
async function getMetrics() {
  const leads = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/leads`, { cache: "no-store" }).then(r => r.json())
  return {
    total:              leads.length,
    recepcionadas:      leads.filter((l: any) => l.status === "reception_contacted").length,
    emailEnviado:       leads.filter((l: any) => ["email_sent","followup_sent"].includes(l.status)).length,
    contatoTecnico:     leads.filter((l: any) => l.status === "contact_requested").length,
    reunioesAgendadas:  leads.filter((l: any) => l.status === "meeting_scheduled").length,
  }
}

export default async function DashboardPage() {
  const m = await getMetrics()
  const cards = [
    { label: "Leads Encontrados",     value: m.total,             color: "bg-gray-50",   icon: "🔍" },
    { label: "Recepções Contatadas",  value: m.recepcionadas,     color: "bg-blue-50",   icon: "💬" },
    { label: "E-mails Enviados",      value: m.emailEnviado,      color: "bg-orange-50", icon: "✉️" },
    { label: "Contatos Técnicos",     value: m.contatoTecnico,    color: "bg-indigo-50", icon: "🔧" },
    { label: "Reuniões Agendadas",    value: m.reunioesAgendadas, color: "bg-green-50",  icon: "✅" },
  ]
  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">EngSearch — Painel Neomot</h1>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        {cards.map(c => (
          <div key={c.label} className={`${c.color} rounded-lg p-4 text-center`}>
            <p className="text-2xl mb-1">{c.icon}</p>
            <p className="text-3xl font-bold">{c.value}</p>
            <p className="text-xs text-gray-600 mt-1">{c.label}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Passo 4: Commit**

```bash
git add dashboard/
git commit -m "feat: dashboard com pipeline completo de 5 etapas"
```

---

## Fase 8 — Containerização

### Tarefa 8: Docker Compose

- [ ] **Passo 1: docker-compose.yml**

```yaml
# docker-compose.yml
version: "3.9"
services:
  api:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [redis]
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

  worker:
    build: .
    env_file: .env
    depends_on: [redis]
    command: celery -A tasks.celery_app worker --loglevel=info -c 4

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  dashboard:
    build: ./dashboard
    ports: ["3000:3000"]
    environment:
      - NEXT_PUBLIC_API_URL=http://api:8000
```

- [ ] **Passo 2: .env.example**

```bash
# .env.example
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_SERVICE_KEY=sua-chave-secreta
REDIS_URL=redis://redis:6379/0
SENDGRID_API_KEY=sua-chave-sendgrid
EMAIL_REMETENTE=neo@neomot.com.br
TWILIO_ACCOUNT_SID=seu-account-sid
TWILIO_AUTH_TOKEN=seu-auth-token
WHATSAPP_FROM=+14155238886          # número Twilio/sandbox
WHATSAPP_GESTOR=+5511999999999      # WhatsApp principal do gestor Neomot
ANTHROPIC_API_KEY=sua-chave-anthropic
```

- [ ] **Passo 3: Commit**

```bash
git add docker-compose.yml .env.example requirements.txt
git commit -m "chore: Docker, variáveis de ambiente e dependências"
```

---

## Verificação End-to-End

```bash
# 1. Subir ambiente
docker-compose up -d

# 2. Prospectar no Instagram
curl -X POST "http://localhost:8000/campaigns/prospect?termo=construtora+SP&plataforma=instagram&max_leads=5"
# → Aguardar worker; checar leads no Supabase com whatsapp_recepcao preenchido

# 3. Contatar todas as recepções encontradas
curl -X POST "http://localhost:8000/campaigns/contact-all"
# → Bot envia mensagem de abertura para cada recepção via WhatsApp

# 4. Simular resposta da recepção (Twilio Sandbox)
# Recepção responde: "Pode mandar para obras@empresa.com"
# → Bot reconhece o e-mail, envia via SendGrid, agenda follow-up para 24h

# 5. Após 24h (ou forçar a task):
#    celery -A tasks.celery_app call tasks.followup_task.iniciar_followup --args='["lead-uuid"]'
# → Follow-up enviado; lead responde com data de reunião ou contato técnico

# 6. Verificar notificação no WhatsApp do gestor Neomot (WHATSAPP_GESTOR)

# 7. Checar dashboard: http://localhost:3000

# 8. Rodar todos os testes
pytest tests/ -v
```

---

## Estimativa de Desenvolvimento

| Fase | Descrição | Tempo Estimado |
|------|-----------|----------------|
| 1 | Infraestrutura (DB + API) | 2 dias |
| 2 | Agente Prospector (Computer Use) | 3 dias |
| 3 | Bot WhatsApp recepção + e-mail | 3 dias |
| 4 | Follow-up 24h + notificação gestor | 2 dias |
| 5 | Webhook com roteamento | 1 dia |
| 6 | Celery tasks + campanhas | 1 dia |
| 7 | Dashboard Next.js | 2 dias |
| 8 | Docker + testes finais | 1 dia |
| **Total** | | **~15 dias úteis** |

---

## Notas de Conformidade e Boas Práticas

- **LGPD:** Coletar apenas dados de perfis públicos e números disponibilizados voluntariamente na bio. Toda mensagem deve permitir opt-out ("Prefere não receber mais contatos? É só me avisar!").
- **Rate limiting:** O agente respeita limites das plataformas — pausas entre navegações, máximo de sessões por dia configurável.
- **WhatsApp Business:** Mensagens proativas (primeiro contato e follow-up) precisam usar templates aprovados no Meta Business Manager. Respostas dentro de janela de 24h não precisam.
- **Twilio Sandbox:** Para desenvolvimento, usar o sandbox do Twilio. Para produção, migrar para número aprovado com WABA.
- **Monitoramento:** Integrar Sentry para alertas de erros nas tasks e no bot.

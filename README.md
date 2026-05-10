# EngSearch

Robô de prospecção inteligente para o setor de construção civil. Encontra leads qualificados no LinkedIn e Instagram, faz o primeiro contato por e-mail e conduz o agendamento de reuniões via WhatsApp — de forma automatizada e com linguagem natural.

Desenvolvido para o gestor comercial da **Neomot** (venda de elevadores para construtoras).

---

## O que o EngSearch faz

```
LinkedIn / Instagram
        │
        ▼ (Claude Computer Use)
  Agente Prospector
  ─ busca construtoras, engenheiros, diretores
  ─ extrai: nome, cargo, empresa, e-mail, WhatsApp
        │
        ▼
   Banco de Leads (Supabase)
        │
        ▼ (SendGrid)
  E-mail de Apresentação
  ─ gerado por IA, personalizado por cargo/empresa
  ─ CTA: "Posso enviar mais detalhes por WhatsApp?"
        │
        ▼ (quando o lead responde)
   Bot WhatsApp "Neo" (Twilio)
  ─ conversa natural, mensagens curtas
  ─ coleta: data, horário, formato da reunião
  ─ confirma e registra o agendamento
        │
        ▼
   Reunião Agendada ✓
   Dashboard do Gestor
```

---

## Stack Técnica

| Camada | Tecnologia |
|--------|-----------|
| IA / Agente | Claude API (claude-sonnet-4-6 + computer-use) |
| Backend | Python · FastAPI |
| Banco de dados | Supabase (PostgreSQL) |
| E-mail | SendGrid |
| WhatsApp | Twilio WhatsApp Business API |
| Filas assíncronas | Celery + Redis |
| Dashboard | Next.js |
| Infraestrutura | Docker Compose |

---

## Estrutura do Projeto

```
engsearch/
├── agents/
│   ├── prospector.py       # Agente de prospecção (Claude Computer Use)
│   ├── email_writer.py     # Geração e envio de e-mails personalizados
│   └── whatsapp_bot.py     # Bot conversacional para agendamento
├── api/
│   ├── main.py             # FastAPI entrypoint
│   └── routes/
│       ├── leads.py        # CRUD de leads
│       ├── campaigns.py    # Disparo de campanhas
│       └── webhooks.py     # Recebimento de mensagens WhatsApp
├── db/
│   ├── schema.sql          # Tabelas: leads, interacoes, reunioes
│   └── client.py           # Cliente Supabase
├── tasks/
│   ├── celery_app.py       # Configuração das filas
│   ├── prospect_task.py    # Task de prospecção assíncrona
│   └── email_task.py       # Task de envio de e-mail
├── dashboard/              # Painel Next.js do gestor
├── prompts/
│   ├── prospector_system.md  # Instruções do agente prospector
│   ├── email_template.md     # Template de e-mail de apresentação
│   └── whatsapp_persona.md   # Persona "Neo" do bot WhatsApp
├── tests/
├── docker-compose.yml
└── .env.example
```

---

## Fluxo de Status dos Leads

```
discovered → email_sent → responded → whatsapp_active → meeting_scheduled
                                                      ↘ lost
```

---

## Como Rodar

```bash
# 1. Configurar variáveis de ambiente
cp .env.example .env
# Preencher: SUPABASE_URL, SENDGRID_API_KEY, TWILIO_*, ANTHROPIC_API_KEY

# 2. Subir os serviços
docker-compose up -d

# 3. Aplicar o schema no Supabase
# (executar db/schema.sql no SQL Editor do Supabase)

# 4. Iniciar uma campanha de prospecção
curl -X POST "http://localhost:8000/campaigns/prospect?termo=construtora+SP&max_leads=20"

# 5. Disparar e-mails para leads descobertos
curl -X POST "http://localhost:8000/campaigns/email-blast"

# 6. Acessar o dashboard
open http://localhost:3000
```

---

## Variáveis de Ambiente

| Variável | Descrição |
|----------|-----------|
| `SUPABASE_URL` | URL do projeto Supabase |
| `SUPABASE_SERVICE_KEY` | Chave de serviço Supabase |
| `REDIS_URL` | URL do Redis (ex: `redis://redis:6379/0`) |
| `SENDGRID_API_KEY` | Chave da API SendGrid |
| `EMAIL_REMETENTE` | E-mail de envio (ex: `contato@neomot.com.br`) |
| `TWILIO_ACCOUNT_SID` | Account SID do Twilio |
| `TWILIO_AUTH_TOKEN` | Auth Token do Twilio |
| `WHATSAPP_FROM` | Número WhatsApp Twilio (ex: `+14155238886`) |
| `ANTHROPIC_API_KEY` | Chave da API Anthropic (Claude) |

---

## Plano de Implementação

O plano técnico detalhado com todas as tarefas, testes e código está em:

`.claude/plano-engsearch.md`

**Estimativa total de desenvolvimento:** ~13 dias úteis

---

## Conformidade e Boas Práticas

- **LGPD:** Apenas dados de perfis públicos são coletados. Todo e-mail inclui opção de descadastro.
- **Rate limiting:** O agente respeita os limites das plataformas com pausas entre ações.
- **WhatsApp Business:** Templates proativos aprovados no Meta Business Manager. Respostas a mensagens recebidas não exigem template.

---

*Desenvolvido por [ZzPowerTech](https://github.com/ZzPowerTech)*

# EngSearch

Robô de prospecção e contato inteligente para o setor de construção civil. Acessa perfis de construtoras, incorporadoras e escritórios de engenharia no Instagram e LinkedIn, extrai o link de WhatsApp da recepção, inicia o contato via WhatsApp, envia o e-mail de apresentação quando solicitado e agenda reuniões de forma automatizada — notificando o gestor da Neomot a cada avanço.

Desenvolvido para o gestor comercial da **Neomot** (venda de elevadores para construtoras).

---

## Fluxo Completo

```
Instagram / LinkedIn
        │
        ▼  Claude Computer Use
  Agente Prospector
  ─ acessa o perfil da empresa
  ─ extrai o link wa.me/ ou botão WhatsApp da bio
  ─ salva: empresa, número da recepção, URL do perfil
        │
        ▼  Twilio WhatsApp
  Bot "Neo" contata a recepção
  ─ apresenta a Neomot brevemente
  ─ aguarda a recepção solicitar o e-mail
        │
        ▼  (recepção pede o e-mail)
  Bot envia o e-mail de apresentação  (SendGrid)
  ─ gerado por IA, personalizado por segmento
        │
        ▼  Celery (24h depois)
  Follow-up automático via WhatsApp
  ─ "Conseguiu ver nosso e-mail?"
  ─ propõe reunião rápida
  ─ pergunta com qual área falar:
      → Engenharia / Área Técnica
      → Suprimentos / Compras
        │
        ├─ Reunião agendada ──────────────────────┐
        │                                         ▼
        └─ Contato técnico coletado ──►  Notificação WhatsApp
                                         para o gestor Neomot
```

---

## Pipeline de Status

```
discovered
    → reception_contacted   (primeiro WhatsApp enviado)
    → email_requested       (recepção forneceu o e-mail)
    → email_sent            (e-mail de apresentação enviado)
    → followup_sent         (follow-up 24h enviado)
    → meeting_scheduled     (reunião agendada ✓)
    → contact_requested     (contato técnico/compras coletado)
    → lost                  (sem interesse)
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
│   ├── prospector.py       # Extrai WhatsApp da recepção via Instagram/LinkedIn
│   ├── email_writer.py     # Gera e envia e-mail sob demanda
│   └── whatsapp_bot.py     # Toda a lógica conversacional (recepção + follow-up)
├── api/
│   ├── main.py
│   └── routes/
│       ├── leads.py        # CRUD de leads
│       ├── campaigns.py    # Disparar prospecção e contatos em massa
│       └── webhooks.py     # Recebe mensagens WhatsApp e roteia por fase
├── db/
│   ├── schema.sql          # Tabelas: leads, interacoes, reunioes
│   └── client.py
├── tasks/
│   ├── celery_app.py
│   ├── prospect_task.py    # Prospecção assíncrona
│   ├── reception_task.py   # Envio de abertura para recepção
│   ├── followup_task.py    # Follow-up 24h após e-mail
│   └── notify_task.py      # Notificação ao gestor Neomot
├── dashboard/              # Painel Next.js com métricas do pipeline
├── prompts/
│   ├── prospector_system.md   # Instruções do agente de prospecção
│   ├── reception_intro.md     # Script de abertura com a recepção
│   ├── email_template.md      # Template de e-mail de apresentação
│   ├── followup_script.md     # Script de follow-up 24h
│   └── notify_template.md     # Templates de notificação ao gestor
└── tests/
```

---

## Como Rodar

```bash
# 1. Configurar variáveis de ambiente
cp .env.example .env
# Preencher todas as chaves (ver seção abaixo)

# 2. Subir os serviços
docker-compose up -d

# 3. Aplicar schema no Supabase
# Executar o conteúdo de db/schema.sql no SQL Editor do Supabase

# 4. Iniciar uma campanha de prospecção
curl -X POST "http://localhost:8000/campaigns/prospect?termo=construtora+SP&plataforma=instagram&max_leads=15"

# 5. Contatar todas as recepções encontradas
curl -X POST "http://localhost:8000/campaigns/contact-all"

# 6. Acompanhar o pipeline no dashboard
open http://localhost:3000
```

---

## Variáveis de Ambiente

| Variável | Descrição |
|----------|-----------|
| `SUPABASE_URL` | URL do projeto Supabase |
| `SUPABASE_SERVICE_KEY` | Chave de serviço Supabase |
| `REDIS_URL` | URL do Redis |
| `SENDGRID_API_KEY` | Chave da API SendGrid |
| `EMAIL_REMETENTE` | E-mail de envio (ex: `neo@neomot.com.br`) |
| `TWILIO_ACCOUNT_SID` | Account SID do Twilio |
| `TWILIO_AUTH_TOKEN` | Auth Token do Twilio |
| `WHATSAPP_FROM` | Número WhatsApp Twilio |
| `WHATSAPP_GESTOR` | WhatsApp do gestor Neomot (recebe notificações) |
| `ANTHROPIC_API_KEY` | Chave da API Anthropic (Claude) |

---

## Plano de Implementação

O plano técnico detalhado está em `.claude/plano-engsearch.md`

**Estimativa total de desenvolvimento:** ~15 dias úteis

---

## Conformidade

- **LGPD:** Apenas números/e-mails disponibilizados publicamente nos perfis são coletados. Toda mensagem inclui opção de descadastro.
- **WhatsApp Business:** Templates proativos aprovados no Meta Business Manager para primeiro contato e follow-up.
- **Rate limiting:** Agente opera com pausas entre ações para respeitar limites das plataformas.

---

*Desenvolvido por [ZzPowerTech](https://github.com/ZzPowerTech)*

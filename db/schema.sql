-- EngSearch — Schema Supabase
-- Fase 1: Infraestrutura Base
-- Aplicar via SQL Editor do Supabase

-- ─────────────────────────────────────────────
-- TABELA: leads
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leads (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa               TEXT NOT NULL,
    segmento              TEXT CHECK (segmento IN (
                              'construtora', 'incorporadora',
                              'escritorio_eng', 'escritorio_arq', 'outro'
                          )),
    whatsapp_recepcao     TEXT,            -- número extraído do Instagram/LinkedIn (formato: 5547999999999)
    email_corporativo     TEXT,            -- preenchido após recepção confirmar
    contato_tecnico       TEXT,            -- WhatsApp do eng./suprimentos (coletado no follow-up)
    cargo_contato_tecnico TEXT,
    instagram_url         TEXT UNIQUE,
    linkedin_url          TEXT,
    status                TEXT NOT NULL DEFAULT 'discovered' CHECK (status IN (
                              'discovered',
                              'reception_contacted',
                              'email_requested',
                              'email_sent',
                              'followup_sent',
                              'contact_requested',
                              'meeting_scheduled',
                              'lost'
                          )),
    notas                 TEXT,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- TABELA: interacoes
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS interacoes (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id   UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    canal     TEXT NOT NULL CHECK (canal IN ('whatsapp', 'email', 'sistema')),
    direcao   TEXT NOT NULL CHECK (direcao IN ('enviado', 'recebido')),
    conteudo  TEXT NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- TABELA: reunioes
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reunioes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id             UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    data_hora           TIMESTAMPTZ,
    formato             TEXT CHECK (formato IN ('presencial', 'video', 'a_definir')),
    contato_confirmado  TEXT,         -- nome/número que confirmou a reunião
    status              TEXT NOT NULL DEFAULT 'agendada' CHECK (status IN (
                            'agendada', 'confirmada', 'realizada', 'cancelada'
                        )),
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- ÍNDICES
-- ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_leads_whatsapp  ON leads(whatsapp_recepcao);
CREATE INDEX IF NOT EXISTS idx_leads_status    ON leads(status);
CREATE INDEX IF NOT EXISTS idx_interacoes_lead ON interacoes(lead_id, criado_em DESC);

-- ─────────────────────────────────────────────
-- TRIGGER: atualiza atualizado_em automaticamente
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_atualizado_em()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_leads_atualizado_em
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_atualizado_em();

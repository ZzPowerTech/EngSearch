from pydantic import BaseModel, field_validator
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID


LeadStatus = Literal[
    "discovered",
    "reception_contacted",
    "email_requested",
    "email_sent",
    "followup_sent",
    "contact_requested",
    "meeting_scheduled",
    "lost",
]

LeadSegmento = Literal[
    "construtora", "incorporadora", "escritorio_eng", "escritorio_arq", "outro"
]


class LeadCreate(BaseModel):
    empresa: str
    segmento: Optional[LeadSegmento] = None
    whatsapp_recepcao: Optional[str] = None
    email_corporativo: Optional[str] = None
    contato_tecnico: Optional[str] = None
    cargo_contato_tecnico: Optional[str] = None
    instagram_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    notas: Optional[str] = None

    @field_validator("whatsapp_recepcao", "contato_tecnico", mode="before")
    @classmethod
    def strip_non_digits(cls, v: Optional[str]) -> Optional[str]:
        """Normalize WhatsApp numbers to digits only (e.g. '47 99273-1177' → '5547992731177')."""
        if v is None:
            return v
        digits = "".join(c for c in v if c.isdigit())
        # Auto-prefix Brazil country code if missing
        if digits and not digits.startswith("55") and len(digits) <= 11:
            digits = "55" + digits
        return digits or None


class LeadUpdate(BaseModel):
    empresa: Optional[str] = None
    segmento: Optional[LeadSegmento] = None
    whatsapp_recepcao: Optional[str] = None
    email_corporativo: Optional[str] = None
    contato_tecnico: Optional[str] = None
    cargo_contato_tecnico: Optional[str] = None
    instagram_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    status: Optional[LeadStatus] = None
    notas: Optional[str] = None


class LeadResponse(BaseModel):
    id: UUID
    empresa: str
    segmento: Optional[str] = None
    whatsapp_recepcao: Optional[str] = None
    email_corporativo: Optional[str] = None
    contato_tecnico: Optional[str] = None
    cargo_contato_tecnico: Optional[str] = None
    instagram_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    status: str
    notas: Optional[str] = None
    criado_em: datetime
    atualizado_em: datetime


# ── Reuniões ────────────────────────────────────────────────────────────────

class ReuniaoCreate(BaseModel):
    lead_id: UUID
    data_hora: Optional[datetime] = None
    formato: Optional[Literal["presencial", "video", "a_definir"]] = "a_definir"
    contato_confirmado: Optional[str] = None


class ReuniaoResponse(ReuniaoCreate):
    id: UUID
    status: str
    criado_em: datetime

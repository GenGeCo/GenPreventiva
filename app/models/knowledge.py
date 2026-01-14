"""
Knowledge model - Conoscenza aziendale appresa dall'AI
Memorizza tutto ciò che l'AI impara dalle conversazioni:
- Correzioni sui costi
- Informazioni su macchinari
- Tempi di lavorazione
- Materiali e loro costi
- Processi specifici dell'officina
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Numeric, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import enum


class KnowledgeType(str, enum.Enum):
    """Tipi di conoscenza che il sistema può apprendere"""
    COST_CORRECTION = "cost_correction"  # Correzione su un costo
    MACHINE_INFO = "machine_info"  # Info su macchinario
    MATERIAL_INFO = "material_info"  # Info su materiale
    PROCESS_INFO = "process_info"  # Info su processo/lavorazione
    TIME_ESTIMATE = "time_estimate"  # Stima tempi
    TOOL_INFO = "tool_info"  # Info su utensili
    GENERAL = "general"  # Conoscenza generica


class KnowledgeItem(Base):
    """Singolo elemento di conoscenza appresa"""
    __tablename__ = "knowledge_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Tipo di conoscenza
    knowledge_type = Column(String(50), nullable=False, default=KnowledgeType.GENERAL)

    # Contenuto principale
    title = Column(String(255), nullable=False)  # Titolo breve
    content = Column(Text, nullable=False)  # Contenuto completo

    # Testo per embedding (ottimizzato per ricerca semantica)
    embedding_text = Column(Text, nullable=False)

    # ChromaDB reference
    chroma_id = Column(String(100), nullable=True, unique=True)

    # Metadati strutturati (dipende dal tipo)
    # Es. per COST_CORRECTION: {"piece_type": "flangia", "old_cost": 80, "new_cost": 150}
    # Es. per MACHINE_INFO: {"machine_name": "Tornio CNC", "hourly_rate": 45, "capabilities": [...]}
    metadata = Column(JSON, nullable=True)

    # Fonte della conoscenza
    source_session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)
    source_message_id = Column(Integer, nullable=True)  # ID del messaggio che ha generato la conoscenza

    # Contesto del disegno se presente
    related_file_id = Column(Integer, ForeignKey("chat_session_files.id"), nullable=True)

    # Validazione
    confidence = Column(Numeric(3, 2), default=1.0)  # 0.0 - 1.0, quanto siamo sicuri
    times_used = Column(Integer, default=0)  # Quante volte usata in risposte
    times_confirmed = Column(Integer, default=0)  # Quante volte confermata corretta

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="knowledge_items")
    source_session = relationship("ChatSession")
    related_file = relationship("ChatSessionFile")

    def __repr__(self):
        return f"<KnowledgeItem {self.knowledge_type}: {self.title[:30]}>"

    def to_context_string(self) -> str:
        """Genera stringa per contesto RAG"""
        parts = [f"[{self.knowledge_type.upper()}] {self.title}", self.content]
        if self.metadata:
            for key, value in self.metadata.items():
                if value is not None:
                    parts.append(f"{key}: {value}")
        return "\n".join(parts)

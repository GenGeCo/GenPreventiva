"""
LearningExample model - Esempi di apprendimento per il sistema RAG
Questi sono i preventivi "insegnati" al sistema con costi reali confermati
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Numeric, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class LearningExample(Base):
    __tablename__ = "learning_examples"

    id = Column(Integer, primary_key=True, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # File PDF originale
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)

    # Descrizione lavorazione (input utente)
    title = Column(String(255), nullable=False)  # Nome identificativo
    description = Column(Text, nullable=False)  # Descrizione dettagliata

    # Dettagli lavorazione
    machine_type = Column(String(100), nullable=True)  # Tipo macchina CNC
    material = Column(String(100), nullable=True)  # Materiale
    working_time_hours = Column(Numeric(6, 2), nullable=True)  # Ore lavoro
    complexity = Column(String(50), nullable=True)  # Complessità

    # Costo REALE (questo è il valore che il sistema impara)
    cost = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="EUR")

    # Metadata aggiuntivi
    notes = Column(Text, nullable=True)  # Note aggiuntive
    tags = Column(JSON, nullable=True)  # Tags per categorizzazione

    # ChromaDB - Vector embedding
    chroma_id = Column(String(100), nullable=True, unique=True)
    embedding_text = Column(Text, nullable=True)  # Testo usato per embedding

    # AI extracted data
    ai_extracted_features = Column(JSON, nullable=True)  # Features estratte da Gemini

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    created_by = relationship("User", back_populates="learning_examples")

    def __repr__(self):
        return f"<LearningExample {self.title} - {self.cost} {self.currency}>"

    def to_context_string(self) -> str:
        """Genera una stringa di contesto per il prompt RAG"""
        parts = [
            f"Titolo: {self.title}",
            f"Descrizione: {self.description}",
            f"Costo: {self.cost} {self.currency}",
        ]
        if self.machine_type:
            parts.append(f"Macchina: {self.machine_type}")
        if self.material:
            parts.append(f"Materiale: {self.material}")
        if self.working_time_hours:
            parts.append(f"Ore lavoro: {self.working_time_hours}")
        if self.complexity:
            parts.append(f"Complessità: {self.complexity}")
        if self.notes:
            parts.append(f"Note: {self.notes}")
        return "\n".join(parts)

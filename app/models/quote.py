"""
Quote model - Preventivi generati dal sistema
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Numeric, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    drawing_id = Column(Integer, ForeignKey("drawings.id"), nullable=False)

    # Preventivo generato
    estimated_cost = Column(Numeric(10, 2), nullable=True)  # Costo stimato
    currency = Column(String(3), default="EUR")

    # Dettagli lavorazione stimata
    machine_type = Column(String(100), nullable=True)  # Es: "Tornio CNC", "Fresatrice"
    material = Column(String(100), nullable=True)  # Es: "Alluminio 6061"
    working_time_hours = Column(Numeric(6, 2), nullable=True)  # Tempo stimato
    complexity = Column(String(50), nullable=True)  # Es: "bassa", "media", "alta"

    # Risposta completa AI
    ai_response = Column(Text, nullable=True)  # Risposta testuale completa di Gemini
    ai_reasoning = Column(Text, nullable=True)  # Ragionamento dell'AI

    # Esempi usati per RAG
    similar_examples = Column(JSON, nullable=True)  # IDs degli esempi simili usati
    similarity_scores = Column(JSON, nullable=True)  # Score di similarità

    # Feedback utente (per miglioramento)
    user_feedback = Column(Text, nullable=True)
    actual_cost = Column(Numeric(10, 2), nullable=True)  # Costo reale (se inserito)
    is_accurate = Column(Integer, nullable=True)  # 1=accurato, 0=non accurato

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="quotes")
    drawing = relationship("Drawing", back_populates="quotes")

    def __repr__(self):
        return f"<Quote {self.id} - {self.estimated_cost} {self.currency}>"

"""
Drawing model - Disegni tecnici caricati
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class Drawing(Base):
    __tablename__ = "drawings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # File info
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)  # Path relativo in storage
    file_size = Column(Integer)  # Bytes
    mime_type = Column(String(100))

    # Metadata estratti da Gemini
    description = Column(Text, nullable=True)  # Descrizione generata da AI
    extracted_data = Column(JSON, nullable=True)  # Dati strutturati estratti

    # ChromaDB reference
    chroma_id = Column(String(100), nullable=True)  # ID nel vector store

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="drawings")
    quotes = relationship("Quote", back_populates="drawing")

    def __repr__(self):
        return f"<Drawing {self.original_filename}>"

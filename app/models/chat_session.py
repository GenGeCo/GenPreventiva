"""
ChatSession model - Sessioni di chat persistenti
Ogni sessione rappresenta una conversazione/progetto con l'AI
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Identificazione sessione
    title = Column(String(255), nullable=False, default="Nuova sessione")
    description = Column(Text, nullable=True)

    # File associati alla sessione (può avere più disegni)
    # I file sono salvati in ChatSessionFile

    # Stato sessione
    is_active = Column(Boolean, default=True)  # Sessione corrente attiva
    is_archived = Column(Boolean, default=False)

    # Contatori per UI
    message_count = Column(Integer, default=0)
    knowledge_extracted = Column(Integer, default=0)  # Quante info estratte

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_message_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    files = relationship("ChatSessionFile", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ChatSession {self.id}: {self.title}>"


class ChatMessage(Base):
    """Singolo messaggio in una sessione di chat"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)

    # Contenuto messaggio
    role = Column(String(20), nullable=False)  # "user" o "assistant"
    content = Column(Text, nullable=False)

    # File allegato a questo messaggio (opzionale)
    attached_file_id = Column(Integer, ForeignKey("chat_session_files.id"), nullable=True)

    # Metadati per tracking apprendimento
    contains_correction = Column(Boolean, default=False)  # Contiene correzione utente
    knowledge_extracted = Column(Boolean, default=False)  # Conoscenza già estratta
    extracted_knowledge_ids = Column(JSON, nullable=True)  # IDs della conoscenza estratta

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("ChatSession", back_populates="messages")
    attached_file = relationship("ChatSessionFile", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage {self.id}: {self.role[:10]}...>"


class ChatSessionFile(Base):
    """File (disegni) associati a una sessione di chat"""
    __tablename__ = "chat_session_files"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)

    # Info file
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)

    # Analisi AI del file
    ai_analysis = Column(Text, nullable=True)  # Descrizione estratta
    ai_features = Column(JSON, nullable=True)  # Features strutturate

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("ChatSession", back_populates="files")
    messages = relationship("ChatMessage", back_populates="attached_file")

    def __repr__(self):
        return f"<ChatSessionFile {self.original_filename}>"

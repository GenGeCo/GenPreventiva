"""
Migrazione 002: Aggiunge tabelle per sessioni chat e conoscenza aziendale

Eseguire con: python -m migrations.002_add_sessions_knowledge

Tabelle create:
- chat_sessions: Sessioni di chat persistenti
- chat_messages: Messaggi delle sessioni
- chat_session_files: File associati alle sessioni
- knowledge_items: Conoscenza aziendale appresa
"""
import sys
from pathlib import Path

# Aggiungi la directory app al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from models.database import engine, Base

# Import dei nuovi modelli per registrarli in Base.metadata
from models.chat_session import ChatSession, ChatMessage, ChatSessionFile
from models.knowledge import KnowledgeItem


def run_migration():
    """Esegue la migrazione creando le nuove tabelle"""
    print("=== Migrazione 002: Sessions & Knowledge ===")

    # Lista delle nuove tabelle
    new_tables = [
        'chat_sessions',
        'chat_messages',
        'chat_session_files',
        'knowledge_items'
    ]

    with engine.connect() as conn:
        # Verifica quali tabelle esistono già
        existing = []
        for table in new_tables:
            result = conn.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = '{table}'
                )
            """))
            if result.scalar():
                existing.append(table)

        if existing:
            print(f"Tabelle già esistenti: {', '.join(existing)}")

        # Crea solo le tabelle mancanti
        tables_to_create = [t for t in new_tables if t not in existing]

        if not tables_to_create:
            print("Tutte le tabelle esistono già. Nessuna migrazione necessaria.")
            return

        print(f"Creando tabelle: {', '.join(tables_to_create)}")

    # Crea le tabelle usando SQLAlchemy
    # Questo creerà solo le tabelle che non esistono
    Base.metadata.create_all(bind=engine)

    print("Migrazione completata con successo!")

    # Verifica
    with engine.connect() as conn:
        for table in new_tables:
            result = conn.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = '{table}'
                )
            """))
            status = "OK" if result.scalar() else "ERRORE"
            print(f"  - {table}: {status}")


if __name__ == "__main__":
    run_migration()

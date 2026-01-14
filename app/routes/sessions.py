"""
Sessions Routes - Gestione sessioni di chat persistenti con apprendimento automatico

Ogni sessione:
- Può contenere più disegni
- Salva tutti i messaggi nel DB
- Estrae automaticamente conoscenza dalle correzioni
- Recupera contesto rilevante dal vector DB
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import logging

from models.database import get_db
from models.user import User
from models.chat_session import ChatSession, ChatMessage, ChatSessionFile
from models.knowledge import KnowledgeItem
from services.auth_service import get_current_user
from services.pdf_service import PDFService
from services.gemini_service import get_gemini_service, GeminiService
from services.chromadb_service import get_chromadb_service, ChromaDBService
from services.knowledge_extractor import get_knowledge_extractor, KnowledgeExtractor

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
pdf_service = PDFService()
logger = logging.getLogger(__name__)


# ===================== SCHEMAS =====================

class SessionCreate(BaseModel):
    title: Optional[str] = "Nuova sessione"
    description: Optional[str] = None


class SessionResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    is_active: bool
    message_count: int
    knowledge_extracted: int
    created_at: datetime
    last_message_at: Optional[datetime]
    files: List[dict]

    class Config:
        from_attributes = True


class MessageRequest(BaseModel):
    content: str
    session_id: int


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    attached_file: Optional[dict] = None
    knowledge_learned: Optional[List[dict]] = None


class ChatExchangeResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
    knowledge_learned: List[dict]
    used_knowledge: int
    used_examples: int


# ===================== SESSION ROUTES =====================

@router.post("/", response_model=SessionResponse)
async def create_session(
    request: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crea una nuova sessione di chat"""
    # Disattiva eventuali sessioni attive precedenti
    db.query(ChatSession).filter(
        ChatSession.user_id == current_user.id,
        ChatSession.is_active == True
    ).update({"is_active": False})

    session = ChatSession(
        user_id=current_user.id,
        title=request.title or "Nuova sessione",
        description=request.description,
        is_active=True
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return SessionResponse(
        id=session.id,
        title=session.title,
        description=session.description,
        is_active=session.is_active,
        message_count=0,
        knowledge_extracted=0,
        created_at=session.created_at,
        last_message_at=None,
        files=[]
    )


@router.get("/", response_model=List[SessionResponse])
async def list_sessions(
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista le sessioni dell'utente con ricerca opzionale"""
    query = db.query(ChatSession).filter(ChatSession.user_id == current_user.id)

    if not include_archived:
        query = query.filter(ChatSession.is_archived == False)

    # Ricerca per titolo o descrizione
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (ChatSession.title.ilike(search_filter)) |
            (ChatSession.description.ilike(search_filter))
        )

    sessions = query.order_by(desc(ChatSession.updated_at)).offset(skip).limit(limit).all()

    return [
        SessionResponse(
            id=s.id,
            title=s.title,
            description=s.description,
            is_active=s.is_active,
            message_count=s.message_count,
            knowledge_extracted=s.knowledge_extracted,
            created_at=s.created_at,
            last_message_at=s.last_message_at,
            files=[{
                "id": f.id,
                "filename": f.original_filename,
                "created_at": f.created_at.isoformat()
            } for f in s.files]
        )
        for s in sessions
    ]


@router.get("/active", response_model=Optional[SessionResponse])
async def get_active_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Ottiene la sessione attiva corrente (o ne crea una nuova)"""
    session = db.query(ChatSession).filter(
        ChatSession.user_id == current_user.id,
        ChatSession.is_active == True,
        ChatSession.is_archived == False
    ).first()

    if not session:
        # Crea nuova sessione
        session = ChatSession(
            user_id=current_user.id,
            title="Nuova sessione",
            is_active=True
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    return SessionResponse(
        id=session.id,
        title=session.title,
        description=session.description,
        is_active=session.is_active,
        message_count=session.message_count,
        knowledge_extracted=session.knowledge_extracted,
        created_at=session.created_at,
        last_message_at=session.last_message_at,
        files=[{
            "id": f.id,
            "filename": f.original_filename,
            "created_at": f.created_at.isoformat()
        } for f in session.files]
    )


@router.post("/new", response_model=SessionResponse)
async def create_new_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crea una nuova sessione (disattiva quella corrente)"""
    # Disattiva tutte le sessioni attive dell'utente
    db.query(ChatSession).filter(
        ChatSession.user_id == current_user.id,
        ChatSession.is_active == True
    ).update({"is_active": False})

    # Crea nuova sessione
    session = ChatSession(
        user_id=current_user.id,
        title="Nuova sessione",
        is_active=True
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return SessionResponse(
        id=session.id,
        title=session.title,
        description=session.description,
        is_active=session.is_active,
        message_count=session.message_count or 0,
        knowledge_extracted=session.knowledge_extracted or 0,
        created_at=session.created_at,
        last_message_at=session.last_message_at,
        files=[]
    )


@router.put("/{session_id}/activate", response_model=SessionResponse)
async def activate_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Attiva una sessione specifica (per caricarla nella chat)"""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Sessione non trovata")

    # Disattiva tutte le altre sessioni
    db.query(ChatSession).filter(
        ChatSession.user_id == current_user.id,
        ChatSession.is_active == True
    ).update({"is_active": False})

    # Attiva questa sessione
    session.is_active = True
    db.commit()
    db.refresh(session)

    return SessionResponse(
        id=session.id,
        title=session.title,
        description=session.description,
        is_active=session.is_active,
        message_count=session.message_count or 0,
        knowledge_extracted=session.knowledge_extracted or 0,
        created_at=session.created_at,
        last_message_at=session.last_message_at,
        files=[{
            "id": f.id,
            "filename": f.original_filename,
            "created_at": f.created_at.isoformat()
        } for f in session.files]
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Ottiene dettagli di una sessione specifica"""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Sessione non trovata")

    return SessionResponse(
        id=session.id,
        title=session.title,
        description=session.description,
        is_active=session.is_active,
        message_count=session.message_count,
        knowledge_extracted=session.knowledge_extracted,
        created_at=session.created_at,
        last_message_at=session.last_message_at,
        files=[{
            "id": f.id,
            "filename": f.original_filename,
            "created_at": f.created_at.isoformat()
        } for f in session.files]
    )


@router.get("/{session_id}/messages", response_model=List[MessageResponse])
async def get_session_messages(
    session_id: int,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Ottiene i messaggi di una sessione"""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Sessione non trovata")

    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at).offset(skip).limit(limit).all()

    return [
        MessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            attached_file={
                "id": m.attached_file.id,
                "filename": m.attached_file.original_filename
            } if m.attached_file else None
        )
        for m in messages
    ]


@router.put("/{session_id}")
async def update_session(
    session_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    is_archived: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aggiorna una sessione"""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Sessione non trovata")

    if title:
        session.title = title
    if description is not None:
        session.description = description
    if is_archived is not None:
        session.is_archived = is_archived
        if is_archived:
            session.is_active = False

    db.commit()
    return {"message": "Sessione aggiornata"}


@router.delete("/{session_id}")
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Elimina una sessione e tutti i suoi messaggi/file"""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Sessione non trovata")

    # Elimina file fisici
    for f in session.files:
        pdf_service.delete_file(f.file_path)

    db.delete(session)
    db.commit()
    return {"message": "Sessione eliminata"}


# ===================== MESSAGE ROUTES (con apprendimento) =====================

@router.post("/{session_id}/messages", response_model=ChatExchangeResponse)
async def send_message(
    session_id: int,
    content: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    gemini: GeminiService = Depends(get_gemini_service),
    chromadb: ChromaDBService = Depends(get_chromadb_service),
    extractor: KnowledgeExtractor = Depends(get_knowledge_extractor)
):
    """
    Invia un messaggio nella sessione con supporto multi-file (max 5).

    Questo endpoint:
    1. Salva il messaggio utente
    2. Salva tutti i file allegati (max 5)
    3. Recupera conoscenza rilevante dal vector DB
    4. Chiama Gemini con il contesto e tutti i file
    5. Salva la risposta
    6. Estrae automaticamente conoscenza dalla conversazione
    7. Ritorna tutto al client
    """
    # Verifica sessione
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Sessione non trovata")

    # Gestisci file multipli (max 5)
    file_records = []
    file_paths = []
    MAX_FILES = 5

    # Filtra file vuoti e limita a 5
    valid_files = [f for f in files if f.filename][:MAX_FILES]

    for file in valid_files:
        try:
            filename, saved_path, file_size = await pdf_service.save_drawing(
                file, current_user.id
            )
            file_record = ChatSessionFile(
                session_id=session_id,
                filename=filename,
                original_filename=file.filename,
                file_path=saved_path,
                file_size=file_size,
                mime_type=pdf_service.get_mime_type(file.filename)
            )
            db.add(file_record)
            db.flush()
            file_records.append(file_record)
            file_paths.append(str(pdf_service.get_absolute_path(saved_path)))
        except ValueError as e:
            logger.warning(f"Failed to save file {file.filename}: {e}")
            continue

    # Per retrocompatibilità con il vecchio codice
    file_record = file_records[0] if file_records else None

    # Salva messaggio utente
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=content,
        attached_file_id=file_record.id if file_record else None
    )
    db.add(user_msg)
    db.flush()

    # Recupera storico conversazione
    history_msgs = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at).limit(20).all()

    history = [{"role": m.role, "content": m.content} for m in history_msgs]

    # Recupera conoscenza e esempi rilevanti
    search_text = content
    if file_record and file_record.ai_analysis:
        search_text += " " + file_record.ai_analysis

    relevant = chromadb.search_all_relevant(
        query_text=search_text,
        user_id=current_user.id,
        n_examples=3,
        n_knowledge=5
    )

    # Se non ci sono nuovi file, cerca gli ultimi file della sessione per contesto
    if not file_paths:
        recent_files = db.query(ChatSessionFile).filter(
            ChatSessionFile.session_id == session_id
        ).order_by(desc(ChatSessionFile.created_at)).limit(5).all()
        for f in recent_files:
            file_paths.append(str(pdf_service.get_absolute_path(f.file_path)))

    # Chiama Gemini con tutti i file
    result = await gemini.chat(
        message=content,
        file_paths=file_paths,  # Lista di path invece di singolo
        history=history,
        knowledge_context=relevant.get('knowledge', []),
        examples_context=relevant.get('examples', [])
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Errore nella risposta AI")
        )

    # Salva risposta assistente
    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=result["response"]
    )
    db.add(assistant_msg)
    db.flush()

    # Aggiorna contatori sessione
    session.message_count = (session.message_count or 0) + 2
    session.last_message_at = datetime.utcnow()

    # ===== ESTRAZIONE CONOSCENZA DAI TAG [RICORDA: ...] =====
    knowledge_learned = []
    try:
        import re
        from decimal import Decimal
        from models.knowledge import KnowledgeItem

        ai_response = result["response"]
        logger.info(f"=== Parsing [RICORDA: ...] tags from AI response ===")

        # Pattern: [RICORDA: tipo | titolo | descrizione]
        pattern = r'\[RICORDA:\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^\]]+)\]'
        matches = re.findall(pattern, ai_response, re.IGNORECASE)

        logger.info(f"Found {len(matches)} [RICORDA: ...] tags")

        new_items_count = 0
        for match in matches:
            knowledge_type = match[0].strip().lower()
            title = match[1].strip()
            content = match[2].strip()
            embedding_text = f"[{knowledge_type.upper()}] {title}\n{content}"
            is_update = False

            # Cerca se esiste già una conoscenza con titolo simile (aggiornamento)
            existing = db.query(KnowledgeItem).filter(
                KnowledgeItem.user_id == current_user.id,
                KnowledgeItem.title.ilike(f"%{title[:30]}%")  # Cerca titoli simili
            ).first()

            if existing:
                logger.info(f"  → Updating existing: [{knowledge_type}] {title}")
                existing.knowledge_type = knowledge_type
                existing.content = content
                existing.embedding_text = embedding_text
                existing.source_session_id = session_id
                existing.source_message_id = assistant_msg.id
                knowledge = existing
                is_update = True

                # Aggiorna vector store
                if existing.chroma_id:
                    try:
                        chromadb.delete_knowledge_item(existing.chroma_id)
                    except:
                        pass
            else:
                logger.info(f"  → Saving new: [{knowledge_type}] {title}")
                new_items_count += 1

                # Salva nel database
                knowledge = KnowledgeItem(
                    user_id=current_user.id,
                    knowledge_type=knowledge_type,
                    title=title[:255],
                    content=content,
                    embedding_text=embedding_text,
                    source_session_id=session_id,
                    source_message_id=assistant_msg.id,
                    related_file_id=file_record.id if file_record else None,
                    confidence=Decimal("0.95")
                )
                db.add(knowledge)

            db.flush()

            # Salva anche nel vector store per ricerca semantica
            try:
                chroma_id = chromadb.add_knowledge_item(
                    knowledge_id=knowledge.id,
                    user_id=current_user.id,
                    embedding_text=embedding_text,
                    knowledge_type=knowledge_type,
                    metadata={"title": title}
                )
                knowledge.chroma_id = chroma_id
            except Exception as e:
                logger.warning(f"Failed to add to ChromaDB: {e}")

            knowledge_learned.append({
                "id": knowledge.id,
                "type": knowledge_type,
                "title": title,
                "content": content[:200],
                "updated": is_update
            })

        if knowledge_learned:
            # Incrementa contatore solo per nuovi elementi
            if new_items_count > 0:
                session.knowledge_extracted = (session.knowledge_extracted or 0) + new_items_count
            user_msg.knowledge_extracted = True
            logger.info(f"✅ Saved {len(knowledge_learned)} knowledge items from AI tags")

            # Rimuovi i tag [RICORDA: ...] dalla risposta mostrata all'utente
            clean_response = re.sub(pattern, '', ai_response, flags=re.IGNORECASE)
            # Rimuovi righe vuote multiple e spazi extra
            clean_response = re.sub(r'\n\s*\n\s*\n', '\n\n', clean_response)  # Max 2 newlines
            clean_response = clean_response.strip()
            assistant_msg.content = clean_response
        else:
            logger.info(f"No [RICORDA: ...] tags found in AI response")

    except Exception as e:
        logger.error(f"❌ Error parsing knowledge tags: {e}", exc_info=True)

    db.commit()

    # Prepara risposta (usa assistant_msg.content che è già pulito dai tag [RICORDA])
    return ChatExchangeResponse(
        user_message=MessageResponse(
            id=user_msg.id,
            role="user",
            content=content,
            created_at=user_msg.created_at,
            attached_file={
                "id": file_record.id,
                "filename": file_record.original_filename
            } if file_record else None
        ),
        assistant_message=MessageResponse(
            id=assistant_msg.id,
            role="assistant",
            content=assistant_msg.content,  # Pulito dai tag [RICORDA: ...]
            created_at=assistant_msg.created_at
        ),
        knowledge_learned=knowledge_learned,
        used_knowledge=result.get("used_knowledge", 0),
        used_examples=result.get("used_examples", 0)
    )


# ===================== FILE ROUTES =====================

@router.post("/{session_id}/files")
async def upload_file_to_session(
    session_id: int,
    file: UploadFile = File(...),
    analyze: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    gemini: GeminiService = Depends(get_gemini_service)
):
    """Carica un file in una sessione (senza messaggio)"""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Sessione non trovata")

    try:
        filename, saved_path, file_size = await pdf_service.save_drawing(
            file, current_user.id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    file_record = ChatSessionFile(
        session_id=session_id,
        filename=filename,
        original_filename=file.filename,
        file_path=saved_path,
        file_size=file_size,
        mime_type=pdf_service.get_mime_type(file.filename)
    )

    # Analizza con Gemini se richiesto
    if analyze:
        absolute_path = pdf_service.get_absolute_path(saved_path)
        analysis = await gemini.analyze_drawing(str(absolute_path))
        if analysis.get("success"):
            file_record.ai_analysis = analysis.get("analysis")

    db.add(file_record)
    db.commit()
    db.refresh(file_record)

    return {
        "id": file_record.id,
        "filename": file_record.original_filename,
        "analysis": file_record.ai_analysis
    }


@router.get("/{session_id}/files/{file_id}")
async def get_session_file(
    session_id: int,
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Ottiene dettagli di un file della sessione"""
    file_record = db.query(ChatSessionFile).filter(
        ChatSessionFile.id == file_id,
        ChatSessionFile.session_id == session_id
    ).first()

    if not file_record:
        raise HTTPException(status_code=404, detail="File non trovato")

    # Verifica che la sessione appartenga all'utente
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Sessione non trovata")

    return {
        "id": file_record.id,
        "filename": file_record.original_filename,
        "file_size": file_record.file_size,
        "mime_type": file_record.mime_type,
        "analysis": file_record.ai_analysis,
        "created_at": file_record.created_at.isoformat()
    }


# ===================== KNOWLEDGE STATS =====================

@router.get("/knowledge/stats")
async def get_knowledge_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """Statistiche sulla conoscenza appresa dall'utente"""
    # Stats da PostgreSQL
    total_items = db.query(KnowledgeItem).filter(
        KnowledgeItem.user_id == current_user.id
    ).count()

    # Stats da ChromaDB
    vector_stats = chromadb.get_knowledge_stats(user_id=current_user.id)

    # Ultimi elementi appresi
    recent = db.query(KnowledgeItem).filter(
        KnowledgeItem.user_id == current_user.id
    ).order_by(desc(KnowledgeItem.created_at)).limit(5).all()

    return {
        "total_knowledge_items": total_items,
        "vector_count": vector_stats.get("user_count", 0),
        "by_type": vector_stats.get("by_type", {}),
        "recent_items": [
            {
                "id": k.id,
                "type": k.knowledge_type,
                "title": k.title,
                "created_at": k.created_at.isoformat()
            }
            for k in recent
        ]
    }


@router.get("/knowledge/list")
async def list_knowledge(
    skip: int = 0,
    limit: int = 50,
    knowledge_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista completa delle conoscenze apprese dall'utente"""
    query = db.query(KnowledgeItem).filter(
        KnowledgeItem.user_id == current_user.id
    )

    if knowledge_type:
        query = query.filter(KnowledgeItem.knowledge_type == knowledge_type)

    total = query.count()
    items = query.order_by(desc(KnowledgeItem.created_at)).offset(skip).limit(limit).all()

    return {
        "total": total,
        "items": [
            {
                "id": k.id,
                "type": k.knowledge_type,
                "title": k.title,
                "content": k.content,
                "confidence": float(k.confidence) if k.confidence else 0.8,
                "extra_data": k.extra_data,
                "created_at": k.created_at.isoformat()
            }
            for k in items
        ]
    }


class KnowledgeCreate(BaseModel):
    title: str
    content: str
    knowledge_type: str = "generale"


@router.post("/knowledge/create")
async def create_knowledge(
    data: KnowledgeCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """Crea una nuova conoscenza manualmente"""
    from decimal import Decimal

    # Valida il tipo
    valid_types = ["costo", "tempo", "macchina", "materiale", "processo", "correzione", "generale"]
    knowledge_type = data.knowledge_type.lower()
    if knowledge_type not in valid_types:
        knowledge_type = "generale"

    embedding_text = f"[{knowledge_type.upper()}] {data.title}\n{data.content}"

    # Crea nel database
    knowledge = KnowledgeItem(
        user_id=current_user.id,
        knowledge_type=knowledge_type,
        title=data.title[:255],
        content=data.content,
        embedding_text=embedding_text,
        confidence=Decimal("1.0"),  # Massima confidenza per inserimento manuale
        source_session_id=None,
        source_message_id=None
    )
    db.add(knowledge)
    db.flush()

    # Salva nel vector store
    try:
        chroma_id = chromadb.add_knowledge_item(
            knowledge_id=knowledge.id,
            user_id=current_user.id,
            embedding_text=embedding_text,
            knowledge_type=knowledge_type,
            metadata={"title": data.title, "manual": True}
        )
        knowledge.chroma_id = chroma_id
    except Exception as e:
        logger.warning(f"Failed to add to ChromaDB: {e}")

    db.commit()

    return {
        "id": knowledge.id,
        "type": knowledge.knowledge_type,
        "title": knowledge.title,
        "content": knowledge.content,
        "created_at": knowledge.created_at.isoformat()
    }


@router.delete("/knowledge/{knowledge_id}")
async def delete_knowledge(
    knowledge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """Elimina una conoscenza specifica"""
    item = db.query(KnowledgeItem).filter(
        KnowledgeItem.id == knowledge_id,
        KnowledgeItem.user_id == current_user.id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Conoscenza non trovata")

    # Rimuovi da ChromaDB se presente
    if item.chroma_id:
        try:
            chromadb.delete_knowledge_item(item.chroma_id)
        except:
            pass

    db.delete(item)
    db.commit()

    return {"message": "Conoscenza eliminata"}


class KnowledgeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    knowledge_type: Optional[str] = None


@router.put("/knowledge/{knowledge_id}")
async def update_knowledge(
    knowledge_id: int,
    update: KnowledgeUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """Modifica una conoscenza esistente"""
    item = db.query(KnowledgeItem).filter(
        KnowledgeItem.id == knowledge_id,
        KnowledgeItem.user_id == current_user.id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Conoscenza non trovata")

    # Aggiorna i campi
    if update.title:
        item.title = update.title[:255]
    if update.content:
        item.content = update.content
    if update.knowledge_type:
        item.knowledge_type = update.knowledge_type

    # Aggiorna embedding text
    item.embedding_text = f"[{item.knowledge_type.upper()}] {item.title}\n{item.content}"

    # Aggiorna nel vector store (elimina e ricrea)
    if item.chroma_id:
        try:
            chromadb.delete_knowledge_item(item.chroma_id)
        except:
            pass

    try:
        new_chroma_id = chromadb.add_knowledge_item(
            knowledge_id=item.id,
            user_id=current_user.id,
            embedding_text=item.embedding_text,
            knowledge_type=item.knowledge_type,
            metadata={"title": item.title}
        )
        item.chroma_id = new_chroma_id
    except Exception as e:
        logger.warning(f"Failed to update ChromaDB: {e}")

    db.commit()

    return {
        "id": item.id,
        "type": item.knowledge_type,
        "title": item.title,
        "content": item.content
    }

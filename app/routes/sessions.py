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
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista le sessioni dell'utente"""
    query = db.query(ChatSession).filter(ChatSession.user_id == current_user.id)

    if not include_archived:
        query = query.filter(ChatSession.is_archived == False)

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
    file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    gemini: GeminiService = Depends(get_gemini_service),
    chromadb: ChromaDBService = Depends(get_chromadb_service),
    extractor: KnowledgeExtractor = Depends(get_knowledge_extractor)
):
    """
    Invia un messaggio nella sessione.

    Questo endpoint:
    1. Salva il messaggio utente
    2. Recupera conoscenza rilevante dal vector DB
    3. Chiama Gemini con il contesto
    4. Salva la risposta
    5. Estrae automaticamente conoscenza dalla conversazione
    6. Ritorna tutto al client
    """
    # Verifica sessione
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Sessione non trovata")

    # Gestisci file se presente
    file_record = None
    file_path = None
    if file:
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
            file_path = str(pdf_service.get_absolute_path(saved_path))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

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

    # Determina file path per Gemini
    # Se non c'è nuovo file, cerca l'ultimo file della sessione
    if not file_path:
        last_file = db.query(ChatSessionFile).filter(
            ChatSessionFile.session_id == session_id
        ).order_by(desc(ChatSessionFile.created_at)).first()
        if last_file:
            file_path = str(pdf_service.get_absolute_path(last_file.file_path))

    # Chiama Gemini
    result = await gemini.chat(
        message=content,
        file_path=file_path,
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

    # ===== ESTRAZIONE AUTOMATICA CONOSCENZA =====
    knowledge_learned = []
    try:
        # Prendi ultimi 4 messaggi per analisi
        recent_messages = [
            {"role": m.role, "content": m.content}
            for m in history_msgs[-3:]
        ] + [
            {"role": "user", "content": content},
            {"role": "assistant", "content": result["response"]}
        ]

        # Estrai conoscenza
        has_learned, items, summary = await extractor.process_chat_exchange(
            db=db,
            user_id=current_user.id,
            messages=recent_messages,
            session_id=session_id,
            message_id=user_msg.id,
            file_id=file_record.id if file_record else None
        )

        if has_learned:
            user_msg.contains_correction = True
            user_msg.knowledge_extracted = True
            user_msg.extracted_knowledge_ids = [k.id for k in items]
            session.knowledge_extracted = (session.knowledge_extracted or 0) + len(items)

            knowledge_learned = [
                {
                    "id": k.id,
                    "type": k.knowledge_type,
                    "title": k.title,
                    "content": k.content[:200]
                }
                for k in items
            ]

            logger.info(f"Extracted {len(items)} knowledge items from session {session_id}")

    except Exception as e:
        logger.error(f"Error in knowledge extraction: {e}")

    db.commit()

    # Prepara risposta
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
            content=result["response"],
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

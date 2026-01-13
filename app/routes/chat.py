"""
Chat Routes - Conversazione interattiva con l'AI
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import json

from models.database import get_db
from models.user import User
from models.drawing import Drawing
from services.auth_service import get_current_user
from services.pdf_service import PDFService
from services.gemini_service import get_gemini_service, GeminiService
from services.chromadb_service import get_chromadb_service, ChromaDBService

router = APIRouter(prefix="/api/chat", tags=["chat"])
pdf_service = PDFService()


# Schemas
class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    drawing_id: Optional[int] = None
    history: Optional[List[ChatMessage]] = None


class ChatResponse(BaseModel):
    response: str
    drawing_id: Optional[int] = None


class ChatWithFileRequest(BaseModel):
    message: str


# Routes
@router.post("/send", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    gemini: GeminiService = Depends(get_gemini_service),
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """
    Invia un messaggio nella chat.
    Può opzionalmente riferirsi a un disegno esistente.
    """
    file_path = None

    # Se c'è un drawing_id, recupera il file
    if request.drawing_id:
        drawing = db.query(Drawing).filter(
            Drawing.id == request.drawing_id,
            Drawing.user_id == current_user.id
        ).first()
        if drawing:
            file_path = str(pdf_service.get_absolute_path(drawing.file_path))

    # Converti history in formato dict
    history = None
    if request.history:
        history = [{"role": m.role, "content": m.content} for m in request.history]

    # Arricchisci il messaggio con contesto RAG se sembra una richiesta di preventivo
    enriched_message = request.message
    if any(word in request.message.lower() for word in ["costo", "prezzo", "preventivo", "quanto"]):
        # Cerca esempi simili
        try:
            similar = chromadb.search_similar(request.message, n_results=2)
            if similar:
                context = "\n\n[Contesto dai preventivi passati:\n"
                for ex in similar:
                    context += f"- {ex.get('document', '')[:200]}...\n"
                context += "]\n"
                enriched_message = context + "\n" + request.message
        except:
            pass

    # Chiama Gemini
    result = await gemini.chat(
        message=enriched_message,
        file_path=file_path,
        history=history
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Errore nella risposta AI")
        )

    return ChatResponse(
        response=result["response"],
        drawing_id=request.drawing_id
    )


@router.post("/send-with-file", response_model=ChatResponse)
async def send_message_with_file(
    file: UploadFile = File(...),
    message: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    gemini: GeminiService = Depends(get_gemini_service)
):
    """
    Invia un messaggio con un nuovo file allegato.
    Il file viene salvato e analizzato.
    """
    # Salva il file
    try:
        filename, file_path, file_size = await pdf_service.save_drawing(
            file, current_user.id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    absolute_path = pdf_service.get_absolute_path(file_path)

    # Crea record Drawing
    drawing = Drawing(
        user_id=current_user.id,
        filename=filename,
        original_filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        mime_type=pdf_service.get_mime_type(file.filename)
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)

    # Chat con il file
    result = await gemini.chat(
        message=message,
        file_path=str(absolute_path)
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Errore nella risposta AI")
        )

    # Salva la descrizione se estratta
    if "descrizione" in message.lower() or "analizza" in message.lower():
        drawing.description = result["response"][:1000]
        db.commit()

    return ChatResponse(
        response=result["response"],
        drawing_id=drawing.id
    )


@router.get("/drawings", response_model=List[dict])
async def list_user_drawings(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista i disegni dell'utente per selezione nella chat"""
    drawings = db.query(Drawing).filter(
        Drawing.user_id == current_user.id
    ).order_by(
        Drawing.created_at.desc()
    ).offset(skip).limit(limit).all()

    return [
        {
            "id": d.id,
            "filename": d.original_filename,
            "created_at": d.created_at.isoformat(),
            "has_description": bool(d.description)
        }
        for d in drawings
    ]


@router.delete("/drawings/{drawing_id}")
async def delete_drawing(
    drawing_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Elimina un disegno"""
    drawing = db.query(Drawing).filter(
        Drawing.id == drawing_id,
        Drawing.user_id == current_user.id
    ).first()

    if not drawing:
        raise HTTPException(status_code=404, detail="Disegno non trovato")

    # Elimina file fisico
    pdf_service.delete_file(drawing.file_path)

    # Elimina dal DB
    db.delete(drawing)
    db.commit()

    return {"message": "Disegno eliminato"}

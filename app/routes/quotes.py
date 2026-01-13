"""
Quotes Routes - Generazione preventivi con RAG
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal

from models.database import get_db
from models.user import User
from models.drawing import Drawing
from models.quote import Quote
from models.learning_example import LearningExample
from services.auth_service import get_current_user
from services.pdf_service import PDFService
from services.chromadb_service import get_chromadb_service, ChromaDBService
from services.gemini_service import get_gemini_service, GeminiService

router = APIRouter(prefix="/api/quotes", tags=["quotes"])
pdf_service = PDFService()


# Schemas
class QuoteResponse(BaseModel):
    id: int
    drawing_id: int
    estimated_cost: Optional[float]
    currency: str
    machine_type: Optional[str]
    material: Optional[str]
    working_time_hours: Optional[float]
    complexity: Optional[str]
    ai_response: Optional[str]
    similar_examples_count: int
    created_at: str

    class Config:
        from_attributes = True


class QuoteFeedback(BaseModel):
    is_accurate: bool
    actual_cost: Optional[float] = None
    feedback: Optional[str] = None


class QuoteListItem(BaseModel):
    id: int
    original_filename: str
    estimated_cost: Optional[float]
    currency: str
    created_at: str


# Routes
@router.post("/generate", response_model=QuoteResponse)
async def generate_quote(
    file: UploadFile = File(...),
    context: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    chromadb: ChromaDBService = Depends(get_chromadb_service),
    gemini: GeminiService = Depends(get_gemini_service)
):
    """
    Genera un preventivo per un nuovo disegno usando RAG:
    1. Analizza il disegno con Gemini
    2. Cerca esempi simili in ChromaDB
    3. Genera preventivo basandosi sugli esempi
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

    # Analizza il disegno per creare la query
    analysis = await gemini.analyze_drawing(str(absolute_path))
    query_text = analysis.get('analysis', '') + (f"\nContesto utente: {context}" if context else "")

    # Aggiorna drawing con l'analisi
    drawing.description = analysis.get('analysis')
    drawing.extracted_data = analysis
    db.commit()

    # Cerca esempi simili in ChromaDB
    similar_examples = []
    try:
        similar_examples = chromadb.search_similar(query_text)

        # Arricchisci con dati dal DB
        for ex in similar_examples:
            example_id = ex.get('metadata', {}).get('example_id')
            if example_id:
                db_example = db.query(LearningExample).filter(
                    LearningExample.id == example_id
                ).first()
                if db_example:
                    ex['metadata']['full_description'] = db_example.description
                    ex['document'] = db_example.to_context_string()
    except Exception as e:
        import logging
        logging.warning(f"ChromaDB search failed: {e}")

    # Genera preventivo con Gemini
    quote_result = await gemini.generate_quote(
        file_path=str(absolute_path),
        similar_examples=similar_examples,
        user_context=context
    )

    # Crea record Quote
    quote = Quote(
        user_id=current_user.id,
        drawing_id=drawing.id,
        estimated_cost=Decimal(str(quote_result.get('estimated_cost'))) if quote_result.get('estimated_cost') else None,
        currency="EUR",
        working_time_hours=Decimal(str(quote_result.get('estimated_hours'))) if quote_result.get('estimated_hours') else None,
        ai_response=quote_result.get('quote_text'),
        similar_examples=[ex.get('chroma_id') for ex in similar_examples],
        similarity_scores=[ex.get('similarity_score') for ex in similar_examples]
    )

    # Estrai machine_type e material dalla risposta se possibile
    response_text = quote_result.get('quote_text', '')
    import re
    machine_match = re.search(r'Macchina[:\s]*([^\n]+)', response_text, re.IGNORECASE)
    if machine_match:
        quote.machine_type = machine_match.group(1).strip()[:100]

    material_match = re.search(r'Materiale[:\s]*([^\n]+)', response_text, re.IGNORECASE)
    if material_match:
        quote.material = material_match.group(1).strip()[:100]

    complexity_match = re.search(r'Complessità[:\s]*(\w+)', response_text, re.IGNORECASE)
    if complexity_match:
        quote.complexity = complexity_match.group(1).strip()[:50]

    db.add(quote)
    db.commit()
    db.refresh(quote)

    return QuoteResponse(
        id=quote.id,
        drawing_id=quote.drawing_id,
        estimated_cost=float(quote.estimated_cost) if quote.estimated_cost else None,
        currency=quote.currency,
        machine_type=quote.machine_type,
        material=quote.material,
        working_time_hours=float(quote.working_time_hours) if quote.working_time_hours else None,
        complexity=quote.complexity,
        ai_response=quote.ai_response,
        similar_examples_count=len(similar_examples),
        created_at=quote.created_at.isoformat()
    )


@router.get("/", response_model=List[QuoteListItem])
async def list_quotes(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista preventivi dell'utente"""
    quotes = db.query(Quote, Drawing).join(
        Drawing, Quote.drawing_id == Drawing.id
    ).filter(
        Quote.user_id == current_user.id
    ).order_by(
        Quote.created_at.desc()
    ).offset(skip).limit(limit).all()

    return [
        QuoteListItem(
            id=q.id,
            original_filename=d.original_filename,
            estimated_cost=float(q.estimated_cost) if q.estimated_cost else None,
            currency=q.currency,
            created_at=q.created_at.isoformat()
        )
        for q, d in quotes
    ]


@router.get("/{quote_id}", response_model=QuoteResponse)
async def get_quote(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Dettagli di un preventivo"""
    quote = db.query(Quote).filter(
        Quote.id == quote_id,
        Quote.user_id == current_user.id
    ).first()

    if not quote:
        raise HTTPException(status_code=404, detail="Preventivo non trovato")

    similar_count = len(quote.similar_examples) if quote.similar_examples else 0

    return QuoteResponse(
        id=quote.id,
        drawing_id=quote.drawing_id,
        estimated_cost=float(quote.estimated_cost) if quote.estimated_cost else None,
        currency=quote.currency,
        machine_type=quote.machine_type,
        material=quote.material,
        working_time_hours=float(quote.working_time_hours) if quote.working_time_hours else None,
        complexity=quote.complexity,
        ai_response=quote.ai_response,
        similar_examples_count=similar_count,
        created_at=quote.created_at.isoformat()
    )


@router.post("/{quote_id}/feedback")
async def submit_feedback(
    quote_id: int,
    feedback: QuoteFeedback,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Invia feedback su un preventivo.
    Se il costo reale è molto diverso, considera di aggiungere come esempio di apprendimento.
    """
    quote = db.query(Quote).filter(
        Quote.id == quote_id,
        Quote.user_id == current_user.id
    ).first()

    if not quote:
        raise HTTPException(status_code=404, detail="Preventivo non trovato")

    quote.is_accurate = 1 if feedback.is_accurate else 0
    if feedback.actual_cost is not None:
        quote.actual_cost = Decimal(str(feedback.actual_cost))
    if feedback.feedback:
        quote.user_feedback = feedback.feedback

    db.commit()

    # Se non accurato e c'è costo reale, suggerisci di aggiungerlo come esempio
    suggestion = None
    if not feedback.is_accurate and feedback.actual_cost:
        suggestion = "Considera di aggiungere questo preventivo come esempio di apprendimento per migliorare le stime future."

    return {
        "message": "Feedback salvato",
        "suggestion": suggestion
    }


@router.post("/{quote_id}/convert-to-example")
async def convert_to_learning_example(
    quote_id: int,
    title: str,
    actual_cost: float,
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """
    Converte un preventivo in esempio di apprendimento usando il costo reale.
    Utile per migliorare il sistema con dati verificati.
    """
    quote = db.query(Quote).filter(
        Quote.id == quote_id,
        Quote.user_id == current_user.id
    ).first()

    if not quote:
        raise HTTPException(status_code=404, detail="Preventivo non trovato")

    drawing = db.query(Drawing).filter(Drawing.id == quote.drawing_id).first()
    if not drawing:
        raise HTTPException(status_code=404, detail="Disegno non trovato")

    # Crea embedding text
    embedding_text = f"""
Titolo: {title}
Descrizione: {drawing.description or 'Disegno tecnico CNC'}
Macchina: {quote.machine_type or 'non specificata'}
Materiale: {quote.material or 'non specificato'}
Complessità: {quote.complexity or 'non specificata'}
Costo reale: {actual_cost} EUR
Note: {notes or ''}
""".strip()

    # Crea learning example
    example = LearningExample(
        created_by_id=current_user.id,
        filename=drawing.filename,
        original_filename=drawing.original_filename,
        file_path=drawing.file_path,
        title=title,
        description=drawing.description or f"Preventivo convertito da quote #{quote_id}",
        machine_type=quote.machine_type,
        material=quote.material,
        working_time_hours=quote.working_time_hours,
        complexity=quote.complexity,
        cost=Decimal(str(actual_cost)),
        currency="EUR",
        notes=notes,
        embedding_text=embedding_text
    )
    db.add(example)
    db.commit()
    db.refresh(example)

    # Aggiungi a ChromaDB
    try:
        chroma_id = chromadb.add_learning_example(
            example_id=example.id,
            embedding_text=embedding_text,
            metadata={
                "title": title,
                "cost": actual_cost,
                "currency": "EUR",
                "machine_type": quote.machine_type,
                "material": quote.material,
                "complexity": quote.complexity,
                "converted_from_quote": quote_id
            }
        )
        example.chroma_id = chroma_id
        db.commit()
    except Exception as e:
        import logging
        logging.error(f"Failed to add converted example to ChromaDB: {e}")

    return {
        "message": "Preventivo convertito in esempio di apprendimento",
        "example_id": example.id
    }

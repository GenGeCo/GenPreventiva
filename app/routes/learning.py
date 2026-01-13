"""
Learning Routes - Insegnamento al sistema (carica preventivi passati)
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal

from models.database import get_db
from models.user import User
from models.learning_example import LearningExample
from services.auth_service import get_current_user
from services.pdf_service import PDFService
from services.chromadb_service import get_chromadb_service, ChromaDBService
from services.gemini_service import get_gemini_service, GeminiService

router = APIRouter(prefix="/api/learning", tags=["learning"])
pdf_service = PDFService()


# Schemas
class LearningExampleResponse(BaseModel):
    id: int
    title: str
    description: str
    cost: float
    currency: str
    machine_type: Optional[str]
    material: Optional[str]
    working_time_hours: Optional[float]
    complexity: Optional[str]
    original_filename: str
    notes: Optional[str]
    tags: Optional[List[str]]

    class Config:
        from_attributes = True


class LearningExampleCreate(BaseModel):
    title: str
    description: str
    cost: float
    currency: str = "EUR"
    machine_type: Optional[str] = None
    material: Optional[str] = None
    working_time_hours: Optional[float] = None
    complexity: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class StatsResponse(BaseModel):
    total_examples: int
    vector_count: int
    examples_by_machine: dict
    examples_by_complexity: dict


# Routes
@router.post("/upload", response_model=LearningExampleResponse)
async def upload_learning_example(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(...),
    cost: float = Form(...),
    currency: str = Form(default="EUR"),
    machine_type: Optional[str] = Form(default=None),
    material: Optional[str] = Form(default=None),
    working_time_hours: Optional[float] = Form(default=None),
    complexity: Optional[str] = Form(default=None),
    notes: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    chromadb: ChromaDBService = Depends(get_chromadb_service),
    gemini: GeminiService = Depends(get_gemini_service)
):
    """
    Carica un nuovo esempio di apprendimento (preventivo passato con costo reale)
    Il sistema lo usa per imparare a fare preventivi simili
    """
    # Salva il file
    try:
        filename, file_path, file_size = await pdf_service.save_learning_example(
            file, current_user.id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Analizza il disegno con Gemini per estrarre features
    absolute_path = pdf_service.get_absolute_path(file_path)
    ai_analysis = await gemini.analyze_drawing(str(absolute_path))

    # Crea il testo per l'embedding (combinazione di descrizione utente + analisi AI)
    embedding_text = f"""
Titolo: {title}
Descrizione: {description}
Macchina: {machine_type or 'non specificata'}
Materiale: {material or 'non specificato'}
Complessità: {complexity or 'non specificata'}
Costo: {cost} {currency}
Note: {notes or ''}
Analisi AI: {ai_analysis.get('analysis', '')}
""".strip()

    # Crea il record nel database
    example = LearningExample(
        created_by_id=current_user.id,
        filename=filename,
        original_filename=file.filename,
        file_path=file_path,
        title=title,
        description=description,
        machine_type=machine_type,
        material=material,
        working_time_hours=Decimal(str(working_time_hours)) if working_time_hours else None,
        complexity=complexity,
        cost=Decimal(str(cost)),
        currency=currency,
        notes=notes,
        tags=None,  # Tags come JSON
        embedding_text=embedding_text,
        ai_extracted_features=ai_analysis if ai_analysis.get('success') else None
    )
    db.add(example)
    db.commit()
    db.refresh(example)

    # Aggiungi al vector store
    try:
        chroma_id = chromadb.add_learning_example(
            example_id=example.id,
            embedding_text=embedding_text,
            metadata={
                "title": title,
                "cost": float(cost),
                "currency": currency,
                "machine_type": machine_type,
                "material": material,
                "working_time_hours": float(working_time_hours) if working_time_hours else None,
                "complexity": complexity
            }
        )
        example.chroma_id = chroma_id
        db.commit()
    except Exception as e:
        # Log error but don't fail - the example is saved in DB
        import logging
        logging.error(f"Failed to add to ChromaDB: {e}")

    return LearningExampleResponse(
        id=example.id,
        title=example.title,
        description=example.description,
        cost=float(example.cost),
        currency=example.currency,
        machine_type=example.machine_type,
        material=example.material,
        working_time_hours=float(example.working_time_hours) if example.working_time_hours else None,
        complexity=example.complexity,
        original_filename=example.original_filename,
        notes=example.notes,
        tags=example.tags
    )


@router.get("/examples", response_model=List[LearningExampleResponse])
async def list_examples(
    skip: int = 0,
    limit: int = 50,
    machine_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista tutti gli esempi di apprendimento"""
    query = db.query(LearningExample)
    if machine_type:
        query = query.filter(LearningExample.machine_type == machine_type)
    examples = query.order_by(LearningExample.created_at.desc()).offset(skip).limit(limit).all()
    return [
        LearningExampleResponse(
            id=ex.id,
            title=ex.title,
            description=ex.description,
            cost=float(ex.cost),
            currency=ex.currency,
            machine_type=ex.machine_type,
            material=ex.material,
            working_time_hours=float(ex.working_time_hours) if ex.working_time_hours else None,
            complexity=ex.complexity,
            original_filename=ex.original_filename,
            notes=ex.notes,
            tags=ex.tags
        )
        for ex in examples
    ]


@router.get("/examples/{example_id}", response_model=LearningExampleResponse)
async def get_example(
    example_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Ottieni dettagli di un esempio specifico"""
    example = db.query(LearningExample).filter(LearningExample.id == example_id).first()
    if not example:
        raise HTTPException(status_code=404, detail="Esempio non trovato")
    return LearningExampleResponse(
        id=example.id,
        title=example.title,
        description=example.description,
        cost=float(example.cost),
        currency=example.currency,
        machine_type=example.machine_type,
        material=example.material,
        working_time_hours=float(example.working_time_hours) if example.working_time_hours else None,
        complexity=example.complexity,
        original_filename=example.original_filename,
        notes=example.notes,
        tags=example.tags
    )


@router.delete("/examples/{example_id}")
async def delete_example(
    example_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """Elimina un esempio di apprendimento"""
    example = db.query(LearningExample).filter(LearningExample.id == example_id).first()
    if not example:
        raise HTTPException(status_code=404, detail="Esempio non trovato")

    # Elimina da ChromaDB
    if example.chroma_id:
        chromadb.delete_example(example.chroma_id)

    # Elimina il file
    pdf_service.delete_file(example.file_path)

    # Elimina dal DB
    db.delete(example)
    db.commit()

    return {"message": "Esempio eliminato con successo"}


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """Statistiche sugli esempi di apprendimento"""
    from sqlalchemy import func

    total = db.query(LearningExample).count()

    # Per macchina
    by_machine = db.query(
        LearningExample.machine_type,
        func.count(LearningExample.id)
    ).group_by(LearningExample.machine_type).all()

    # Per complessità
    by_complexity = db.query(
        LearningExample.complexity,
        func.count(LearningExample.id)
    ).group_by(LearningExample.complexity).all()

    # ChromaDB stats
    chroma_stats = chromadb.get_collection_stats()

    return StatsResponse(
        total_examples=total,
        vector_count=chroma_stats.get("count", 0),
        examples_by_machine={m or "non specificata": c for m, c in by_machine},
        examples_by_complexity={c or "non specificata": n for c, n in by_complexity}
    )

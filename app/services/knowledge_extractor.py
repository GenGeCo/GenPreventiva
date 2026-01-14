"""
Knowledge Extractor Service - Estrae automaticamente conoscenza dalle conversazioni

Questo servizio è il cuore del sistema di apprendimento:
1. Analizza i messaggi della chat
2. Identifica correzioni, informazioni nuove, conferme
3. Estrae e struttura la conoscenza
4. La salva nel database e nel vector store
"""
import google.generativeai as genai
from typing import List, Dict, Any, Optional, Tuple
import json
import logging
import re
from decimal import Decimal
from sqlalchemy.orm import Session

from config import settings
from models.knowledge import KnowledgeItem, KnowledgeType
from models.chat_session import ChatMessage, ChatSession
from services.chromadb_service import get_chromadb_service

logger = logging.getLogger(__name__)

# Prompt per l'estrazione della conoscenza
EXTRACTION_PROMPT = """Analizza questo scambio di messaggi tra utente e assistente in un sistema di preventivazione industriale.

CONVERSAZIONE:
{conversation}

Il tuo compito è identificare se l'utente sta fornendo QUALSIASI informazione utile per futuri preventivi:
1. COSTI: prezzi, costi orari, costi materiali, margini (es. "il laser costa 80€/ora", "l'alluminio costa 3€/kg")
2. TEMPI: tempi di lavorazione, setup, consegna (es. "ci vogliono 2 ore", "il setup richiede 30 minuti")
3. MACCHINARI: macchine disponibili, capacità (es. "abbiamo un laser da 3kW", "il tornio fa pezzi fino a 500mm")
4. MATERIALI: materiali usati, preferenze (es. "usiamo sempre acciaio inox 304", "preferisco alluminio 6082")
5. CORREZIONI: quando l'utente corregge una stima dell'AI (es. "no, costa 150 non 80")
6. PROCESSI: come vengono fatte le lavorazioni (es. "prima tagliamo poi pieghiamo")

Per ogni informazione utile trovata, estrai in formato JSON:

```json
{
  "extractions": [
    {
      "type": "cost_correction|machine_info|material_info|process_info|time_estimate|tool_info|general",
      "title": "Titolo breve (max 50 char)",
      "content": "Descrizione completa dell'informazione appresa",
      "confidence": 0.0-1.0,
      "metadata": {
        // campi specifici per tipo, es:
        // per cost_correction: "piece_type", "old_value", "new_value", "currency"
        // per machine_info: "machine_name", "hourly_rate", "capabilities"
        // per material_info: "material_name", "cost_per_kg", "supplier"
        // per time_estimate: "operation", "estimated_hours", "piece_type"
      }
    }
  ],
  "has_correction": true/false,
  "summary": "Breve riassunto di cosa è stato appreso"
}
```

Se NON ci sono informazioni utili da estrarre, rispondi:
```json
{
  "extractions": [],
  "has_correction": false,
  "summary": "Nessuna nuova informazione da apprendere"
}
```

IMPORTANTE:
- Estrai SOLO informazioni concrete e utili per futuri preventivi
- Ignora convenevoli, domande generiche, richieste di chiarimento
- La confidence deve riflettere quanto sei sicuro dell'informazione (1.0 = esplicito dall'utente, 0.7 = dedotto)
- Per correzioni di costo, cattura SEMPRE old_value e new_value se disponibili

Rispondi SOLO con il JSON, nessun testo aggiuntivo."""


class KnowledgeExtractor:
    def __init__(self):
        self._model = None
        self._configured = False

    def _configure(self):
        """Configura il client Gemini"""
        if not self._configured:
            if not settings.GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY non configurata")
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self._configured = True

    def _get_model(self):
        """Lazy initialization del modello"""
        if self._model is None:
            self._configure()
            self._model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",  # Usiamo flash per estrazione rapida
                generation_config={
                    "temperature": 0.1,  # Bassa per output consistente
                    "top_p": 0.95,
                    "max_output_tokens": 2048,
                }
            )
        return self._model

    def _format_conversation(
        self,
        messages: List[Dict[str, str]],
        max_messages: int = 6
    ) -> str:
        """Formatta gli ultimi messaggi per l'analisi"""
        recent = messages[-max_messages:] if len(messages) > max_messages else messages
        formatted = []
        for msg in recent:
            role = "UTENTE" if msg.get("role") == "user" else "ASSISTENTE"
            formatted.append(f"{role}: {msg.get('content', '')}")
        return "\n\n".join(formatted)

    async def analyze_for_knowledge(
        self,
        messages: List[Dict[str, str]],
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analizza i messaggi per estrarre conoscenza

        Args:
            messages: Lista di messaggi {role, content}
            context: Contesto aggiuntivo (es. descrizione del disegno)

        Returns:
            Dict con extractions, has_correction, summary
        """
        if len(messages) < 2:
            return {"extractions": [], "has_correction": False, "summary": "Conversazione troppo breve"}

        model = self._get_model()
        conversation = self._format_conversation(messages)

        if context:
            conversation = f"CONTESTO: {context}\n\n{conversation}"

        prompt = EXTRACTION_PROMPT.format(conversation=conversation)

        try:
            logger.info(f"=== KNOWLEDGE EXTRACTION START ===")
            logger.info(f"Conversation to analyze:\n{conversation[:500]}...")

            response = await model.generate_content_async(prompt)
            text = response.text.strip()

            logger.info(f"Raw Gemini response:\n{text[:500]}...")

            # Estrai JSON dalla risposta
            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if json_match:
                text = json_match.group(1)

            # Pulisci eventuali caratteri extra
            text = text.strip()
            if text.startswith('```'):
                text = text[3:]
            if text.endswith('```'):
                text = text[:-3]

            result = json.loads(text)

            logger.info(f"Parsed result: {len(result.get('extractions', []))} extractions found")
            if result.get('extractions'):
                for i, ext in enumerate(result['extractions']):
                    logger.info(f"  Extraction {i+1}: {ext.get('type')} - {ext.get('title')}")

            # Valida struttura
            if "extractions" not in result:
                result["extractions"] = []
            if "has_correction" not in result:
                result["has_correction"] = len(result["extractions"]) > 0
            if "summary" not in result:
                result["summary"] = ""

            logger.info(f"=== KNOWLEDGE EXTRACTION END: {len(result['extractions'])} items ===")
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse extraction JSON: {e}\nRaw text: {text[:200]}")
            return {"extractions": [], "has_correction": False, "summary": "Errore parsing"}
        except Exception as e:
            logger.error(f"Error in knowledge extraction: {e}", exc_info=True)
            return {"extractions": [], "has_correction": False, "summary": f"Errore: {str(e)}"}

    def save_extracted_knowledge(
        self,
        db: Session,
        user_id: int,
        extractions: List[Dict[str, Any]],
        session_id: Optional[int] = None,
        message_id: Optional[int] = None,
        file_id: Optional[int] = None
    ) -> List[KnowledgeItem]:
        """
        Salva le conoscenze estratte nel database e nel vector store

        Args:
            db: Database session
            user_id: ID dell'utente
            extractions: Lista di extractions dal modello
            session_id: ID della sessione di chat (opzionale)
            message_id: ID del messaggio sorgente (opzionale)
            file_id: ID del file correlato (opzionale)

        Returns:
            Lista di KnowledgeItem creati
        """
        chromadb = get_chromadb_service()
        created_items = []

        for ext in extractions:
            try:
                # Costruisci embedding text
                embedding_parts = [
                    f"[{ext.get('type', 'general').upper()}]",
                    ext.get('title', ''),
                    ext.get('content', '')
                ]
                if ext.get('metadata'):
                    for k, v in ext['metadata'].items():
                        if v is not None:
                            embedding_parts.append(f"{k}: {v}")
                embedding_text = "\n".join(embedding_parts)

                # Crea record nel database
                knowledge = KnowledgeItem(
                    user_id=user_id,
                    knowledge_type=ext.get('type', 'general'),
                    title=ext.get('title', 'Informazione')[:255],
                    content=ext.get('content', ''),
                    embedding_text=embedding_text,
                    extra_data=ext.get('metadata'),
                    source_session_id=session_id,
                    source_message_id=message_id,
                    related_file_id=file_id,
                    confidence=Decimal(str(ext.get('confidence', 0.8)))
                )
                db.add(knowledge)
                db.flush()  # Per ottenere l'ID

                # Aggiungi al vector store
                chroma_id = chromadb.add_knowledge_item(
                    knowledge_id=knowledge.id,
                    user_id=user_id,
                    embedding_text=embedding_text,
                    knowledge_type=ext.get('type', 'general'),
                    metadata={
                        "title": knowledge.title,
                        **(ext.get('metadata') or {})
                    }
                )
                knowledge.chroma_id = chroma_id
                created_items.append(knowledge)

                logger.info(f"Saved knowledge item: {knowledge.title}")

            except Exception as e:
                logger.error(f"Error saving knowledge item: {e}")
                continue

        db.commit()
        return created_items

    async def process_chat_exchange(
        self,
        db: Session,
        user_id: int,
        messages: List[Dict[str, str]],
        session_id: Optional[int] = None,
        message_id: Optional[int] = None,
        file_id: Optional[int] = None,
        context: Optional[str] = None
    ) -> Tuple[bool, List[KnowledgeItem], str]:
        """
        Processo completo: analizza e salva la conoscenza

        Args:
            db: Database session
            user_id: ID dell'utente
            messages: Messaggi da analizzare
            session_id: ID sessione
            message_id: ID messaggio
            file_id: ID file correlato
            context: Contesto aggiuntivo

        Returns:
            Tuple (has_learned, items_created, summary)
        """
        # Analizza
        result = await self.analyze_for_knowledge(messages, context)

        if not result.get('extractions'):
            return False, [], result.get('summary', '')

        # Salva
        items = self.save_extracted_knowledge(
            db=db,
            user_id=user_id,
            extractions=result['extractions'],
            session_id=session_id,
            message_id=message_id,
            file_id=file_id
        )

        return len(items) > 0, items, result.get('summary', '')


# Singleton instance
_knowledge_extractor: Optional[KnowledgeExtractor] = None


def get_knowledge_extractor() -> KnowledgeExtractor:
    """Dependency injection per KnowledgeExtractor"""
    global _knowledge_extractor
    if _knowledge_extractor is None:
        _knowledge_extractor = KnowledgeExtractor()
    return _knowledge_extractor

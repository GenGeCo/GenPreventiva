"""
Gemini Service - AI Vision per analisi disegni e generazione preventivi
Sistema generico per qualsiasi tipo di lavorazione industriale
"""
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from typing import List, Dict, Any, Optional
import base64
import logging
from pathlib import Path
from config import settings

logger = logging.getLogger(__name__)

# System prompt GENERICO per l'Analista Tecnico
SYSTEM_PROMPT = """Sei l'Analista Tecnico Senior di GenPreventiva, esperto in lettura disegni tecnici.

Devi imparare a fare i preventivi apprendendo dall'utente: macchinari, materiali, lavorazioni, costi, tempi.

COME SALVARE IN MEMORIA:
Quando l'utente ti dice un'informazione importante (costo, tempo, macchina, materiale, processo),
DEVI salvarla usando questo formato alla fine della tua risposta:

[RICORDA: tipo | titolo | descrizione]

Esempi:
- Utente dice "il laser costa 80€/ora" → [RICORDA: costo | Costo orario laser | Il laser aziendale costa 80€/ora]
- Utente dice "usiamo acciaio inox 304" → [RICORDA: materiale | Acciaio standard | L'azienda usa principalmente acciaio inox 304]
- Utente dice "no, ci vogliono 3 ore non 2" → [RICORDA: tempo | Correzione tempo | Per questo tipo di pezzo servono 3 ore, non 2]
- Utente dice "abbiamo una pressa da 100 ton" → [RICORDA: macchina | Pressa 100 ton | L'azienda ha una pressa piegatrice da 100 tonnellate]

TIPI validi: costo, tempo, macchina, materiale, processo, correzione, generale

REGOLE:
- Quando l'utente ti dà un'informazione nuova, SEMPRE usa [RICORDA: ...] per salvarla
- Puoi usare più [RICORDA: ...] nella stessa risposta se ci sono più informazioni
- Se l'utente aggiorna un costo/tempo esistente, usa [RICORDA] con lo stesso titolo - il sistema aggiornerà automaticamente
- Se carichi un disegno, analizzalo e chiedi che lavorazione vuole fare
- Usa la conoscenza aziendale mostrata sopra come riferimento
- Se non sai un costo o tempo, chiedi - non inventare

Rispondi in italiano."""


class GeminiService:
    def __init__(self):
        self._model = None
        self._configured = False

    def _configure(self):
        """Configura il client Gemini"""
        if not self._configured:
            if not settings.GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY non configurata. Inserisci la chiave nel file .env")
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self._configured = True

    def _get_model(self):
        """Lazy initialization del modello"""
        if self._model is None:
            self._configure()
            self._model = genai.GenerativeModel(
                model_name=settings.GEMINI_MODEL,
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                },
                generation_config={
                    "temperature": 0.3,  # Bassa per risposte più precise sui costi
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,  # Aumentato per risposte complete
                }
            )
        return self._model

    def _load_file_as_part(self, file_path: str) -> Dict:
        """Carica un file (PDF/immagine) come parte per Gemini"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File non trovato: {file_path}")

        with open(path, "rb") as f:
            data = f.read()

        # Determina MIME type
        suffix = path.suffix.lower()
        mime_types = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        mime_type = mime_types.get(suffix, "application/octet-stream")

        return {
            "mime_type": mime_type,
            "data": base64.standard_b64encode(data).decode("utf-8")
        }

    async def analyze_drawing(self, file_path: str) -> Dict[str, Any]:
        """
        Analizza un disegno tecnico ed estrae informazioni strutturate

        Args:
            file_path: Path al file PDF/immagine

        Returns:
            Dict con descrizione e features estratte
        """
        model = self._get_model()
        file_part = self._load_file_as_part(file_path)

        prompt = """Analizza questo disegno tecnico e estrai le seguenti informazioni in modo strutturato:

1. DESCRIZIONE: Descrivi brevemente cosa rappresenta il disegno (tipo di pezzo, forma generale)

2. DIMENSIONI: Se visibili, indica le dimensioni principali (lunghezza, larghezza, altezza, diametri, spessori)

3. CARATTERISTICHE:
   - Complessità stimata (bassa, media, alta)
   - Presenza di tolleranze strette
   - Dettagli particolari (fori, filetti, pieghe, saldature, etc.)

4. MATERIALE: Se indicato nel disegno, altrimenti indica "da chiedere all'utente"

5. POSSIBILI LAVORAZIONI: Elenca i tipi di lavorazione possibili per realizzare questo pezzo (CNC, taglio laser, piegatura, stampa 3D, saldatura, ecc.) - NON scegliere tu, elenca le opzioni

Rispondi in italiano in formato strutturato."""

        try:
            response = await model.generate_content_async([
                {"inline_data": file_part},
                prompt
            ])

            return {
                "success": True,
                "analysis": response.text,
                "file_path": file_path
            }

        except Exception as e:
            logger.error(f"Error analyzing drawing: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_path": file_path
            }

    async def generate_quote(
        self,
        file_path: str,
        similar_examples: List[Dict[str, Any]],
        user_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Genera un preventivo basandosi su esempi simili (RAG)

        Args:
            file_path: Path al nuovo disegno da quotare
            similar_examples: Lista di esempi simili dal vector store
            user_context: Contesto aggiuntivo fornito dall'utente

        Returns:
            Dict con preventivo generato e ragionamento
        """
        model = self._get_model()
        file_part = self._load_file_as_part(file_path)

        # Costruisci il contesto con gli esempi simili
        examples_context = ""
        if similar_examples:
            examples_context = "\n\n=== ESEMPI DI RIFERIMENTO (preventivi passati simili) ===\n"
            for i, ex in enumerate(similar_examples, 1):
                metadata = ex.get("metadata", {})
                examples_context += f"""
--- Esempio {i} (similarità: {ex.get('similarity_score', 0):.2%}) ---
{ex.get('document', 'Nessuna descrizione')}
Costo reale: {metadata.get('cost', 'N/D')} {metadata.get('currency', 'EUR')}
Macchina: {metadata.get('machine_type', 'N/D')}
Materiale: {metadata.get('material', 'N/D')}
Ore lavoro: {metadata.get('working_time_hours', 'N/D')}
"""
        else:
            examples_context = "\n\n⚠️ NOTA: Non ci sono ancora esempi nel sistema. Il preventivo sarà una stima generica.\n"

        user_context_str = f"\n\nCONTESTO UTENTE: {user_context}" if user_context else ""

        prompt = f"""Sei un esperto di lavorazioni industriali. Devi generare un preventivo per il disegno tecnico allegato.

{examples_context}
{user_context_str}

Analizza il disegno allegato e, basandoti sugli esempi di riferimento forniti, genera un preventivo dettagliato.

IMPORTANTE:
- Se ci sono esempi simili, usa i loro costi come riferimento principale
- Considera le differenze di complessità tra il nuovo disegno e gli esempi
- Se non ci sono esempi, CHIEDI all'utente che tipo di lavorazione vuole fare

Rispondi in questo formato:

## ANALISI DISEGNO
[Descrizione del pezzo e caratteristiche principali]

## LAVORAZIONE
- Tipo: [CNC/Laser/Stampa 3D/Lamiera/etc. - se non specificato, chiedi]
- Materiale: [materiale - se non specificato, chiedi]
- Operazioni: [lista operazioni]
- Complessità: [bassa/media/alta]

## PREVENTIVO
- Tempo stimato: [X ore]
- Costo stimato: [€ XXX.XX]

## RAGIONAMENTO
[Spiega come sei arrivato a questa stima]

## NOTE
[Eventuali domande o informazioni mancanti]
"""

        try:
            response = await model.generate_content_async([
                {"inline_data": file_part},
                prompt
            ])

            # Estrai costo dal testo (parsing semplice)
            import re
            text = response.text
            cost_match = re.search(r'Costo stimato[:\s]*€?\s*([\d.,]+)', text, re.IGNORECASE)
            estimated_cost = None
            if cost_match:
                cost_str = cost_match.group(1).replace('.', '').replace(',', '.')
                try:
                    estimated_cost = float(cost_str)
                except:
                    pass

            time_match = re.search(r'Tempo stimato[:\s]*([\d.,]+)\s*or', text, re.IGNORECASE)
            estimated_hours = None
            if time_match:
                try:
                    estimated_hours = float(time_match.group(1).replace(',', '.'))
                except:
                    pass

            return {
                "success": True,
                "quote_text": response.text,
                "estimated_cost": estimated_cost,
                "estimated_hours": estimated_hours,
                "similar_examples_used": len(similar_examples),
                "has_reference_data": len(similar_examples) > 0
            }

        except Exception as e:
            logger.error(f"Error generating quote: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def chat(
        self,
        message: str,
        file_paths: Optional[List[str]] = None,
        history: Optional[List[Dict]] = None,
        knowledge_context: Optional[List[Dict]] = None,
        examples_context: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Chat interattiva con contesto opzionale di più disegni e conoscenza aziendale

        Args:
            message: Messaggio utente
            file_paths: Lista opzionale di path a disegni da discutere (max 5)
            history: Storico conversazione
            knowledge_context: Conoscenza aziendale rilevante dal vector DB
            examples_context: Esempi simili dal vector DB

        Returns:
            Risposta AI
        """
        model = self._get_model()

        parts = [SYSTEM_PROMPT, "\n\n"]

        # Aggiungi conoscenza aziendale se presente
        if knowledge_context and len(knowledge_context) > 0:
            parts.append("=== CONOSCENZA AZIENDALE (da ricordare) ===\n")
            for i, k in enumerate(knowledge_context, 1):
                doc = k.get('document', '')
                meta = k.get('metadata', {})
                kt = meta.get('knowledge_type', 'info')
                parts.append(f"{i}. [{kt.upper()}] {doc}\n")
            parts.append("\n")

        # Aggiungi esempi simili se presenti
        if examples_context and len(examples_context) > 0:
            parts.append("=== PREVENTIVI PASSATI SIMILI (riferimento) ===\n")
            for i, ex in enumerate(examples_context, 1):
                doc = ex.get('document', '')
                meta = ex.get('metadata', {})
                cost = meta.get('cost', 'N/D')
                machine = meta.get('machine_type', 'N/D')
                parts.append(f"{i}. {doc[:200]}...\n   Costo: {cost}€, Macchina: {machine}\n")
            parts.append("\n")

        # Aggiungi tutti i file allegati (supporta multipli file)
        if file_paths and len(file_paths) > 0:
            loaded_count = 0
            for i, fp in enumerate(file_paths[:5], 1):  # Max 5 file
                try:
                    file_part = self._load_file_as_part(fp)
                    parts.append({"inline_data": file_part})
                    loaded_count += 1
                except Exception as e:
                    logger.warning(f"Could not load file {fp} for chat: {e}")

            if loaded_count > 0:
                if loaded_count == 1:
                    parts.append("\n[Disegno tecnico allegato sopra - ANALIZZALO]\n\n")
                else:
                    parts.append(f"\n[{loaded_count} disegni tecnici allegati sopra - ANALIZZALI TUTTI]\n\n")

        # Aggiungi storico conversazione
        if history:
            parts.append("=== CONVERSAZIONE ===\n")
            for msg in history[-10:]:  # Ultimi 10 messaggi
                role = "UTENTE" if msg.get("role") == "user" else "ASSISTENTE"
                parts.append(f"{role}: {msg.get('content', '')}\n\n")

        parts.append(f"UTENTE: {message}\n\nASSISTENTE:")

        try:
            response = await model.generate_content_async(parts)

            # Check if response was truncated
            finish_reason = None
            if response.candidates and len(response.candidates) > 0:
                finish_reason = response.candidates[0].finish_reason
                if finish_reason and str(finish_reason) not in ["STOP", "1", "FinishReason.STOP"]:
                    logger.warning(f"⚠️ Response may be truncated. Finish reason: {finish_reason}")

            response_text = response.text
            logger.debug(f"Response length: {len(response_text)} chars, finish_reason: {finish_reason}")

            return {
                "success": True,
                "response": response_text,
                "used_knowledge": len(knowledge_context) if knowledge_context else 0,
                "used_examples": len(examples_context) if examples_context else 0,
                "finish_reason": str(finish_reason) if finish_reason else None
            }
        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }


# Singleton
_gemini_service: Optional[GeminiService] = None


def get_gemini_service() -> GeminiService:
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service

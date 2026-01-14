"""
Gemini Service - AI Vision per analisi disegni e generazione preventivi
Usa Google Gemini 1.5 Pro per "vedere" i disegni tecnici come fa ChatGPT

L'AI si comporta come un "Analista Tecnico Senior" esperto di:
- Lettura disegni meccanici (ISO/ASME)
- Lavorazioni CNC (tornitura, fresatura, foratura, etc.)
- Preventivazione basata su esperienza
"""
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from typing import List, Dict, Any, Optional
import base64
import logging
from pathlib import Path
from config import settings

logger = logging.getLogger(__name__)

# System prompt per l'Analista Tecnico Senior
SYSTEM_PROMPT = """Sei l'Analista Tecnico Senior di GenPreventiva, esperto in:
- Lettura disegni meccanici secondo normative ISO e ASME
- Lavorazioni CNC: tornitura, fresatura, foratura, rettifica, EDM
- Materiali: acciai, alluminio, ottone, plastica tecnica, titanio
- Preventivazione precisa basata su esperienza reale

IL TUO OBIETTIVO è la PRECISIONE ASSOLUTA. Per raggiungere questo obiettivo:

1. ANALIZZA i disegni con attenzione metodica:
   - Dimensioni e tolleranze
   - Materiale e trattamenti
   - Complessità geometrica
   - Numero di setup necessari

2. USA LA CONOSCENZA AZIENDALE che ti viene fornita:
   - Costi orari specifici dei macchinari dell'officina
   - Tempi reali di lavorazioni passate
   - Preferenze su materiali e fornitori
   - Correzioni fatte dall'utente in passato

3. IMPARA CONTINUAMENTE dalle correzioni:
   - Quando l'utente ti corregge, il sistema memorizza
   - Nelle prossime stime userai questa esperienza
   - Più lavori insieme, più diventi preciso

4. RISPONDI in modo STRUTTURATO:
   - Lista operazioni in ordine
   - Tempi per operazione
   - Macchinario consigliato per ogni step
   - Costi dettagliati

REGOLE:
- Mai inventare dati: se non hai informazioni, chiedi
- Preferisci la conoscenza aziendale ai valori generici
- Sii conciso ma completo
- Indica sempre il livello di confidenza delle stime

Rispondi sempre in italiano."""


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

        prompt = """Analizza questo disegno tecnico CNC e estrai le seguenti informazioni in modo strutturato:

1. DESCRIZIONE: Descrivi brevemente cosa rappresenta il disegno (tipo di pezzo, forma generale)

2. DIMENSIONI: Se visibili, indica le dimensioni principali (lunghezza, larghezza, altezza, diametri)

3. CARATTERISTICHE:
   - Tipo di lavorazione probabile (tornitura, fresatura, foratura, etc.)
   - Complessità stimata (bassa, media, alta)
   - Presenza di tolleranze strette
   - Numero di operazioni/setup stimati

4. MATERIALE: Se indicato nel disegno, altrimenti suggerisci materiali tipici

5. MACCHINA: Tipo di macchina CNC più adatta (tornio, fresatrice 3 assi, 5 assi, etc.)

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

        prompt = f"""Sei un esperto di lavorazioni CNC. Devi generare un preventivo per il disegno tecnico allegato.

{examples_context}
{user_context_str}

Analizza il disegno allegato e, basandoti sugli esempi di riferimento forniti, genera un preventivo dettagliato.

IMPORTANTE:
- Se ci sono esempi simili, usa i loro costi come riferimento principale
- Considera le differenze di complessità tra il nuovo disegno e gli esempi
- Se non ci sono esempi, fornisci una stima generica indicando che è approssimativa

Rispondi in questo formato:

## ANALISI DISEGNO
[Descrizione del pezzo e caratteristiche principali]

## LAVORAZIONE CONSIGLIATA
- Macchina: [tipo]
- Materiale suggerito: [materiale]
- Operazioni: [lista operazioni]
- Complessità: [bassa/media/alta]

## PREVENTIVO
- Tempo stimato: [X ore]
- Costo stimato: [€ XXX.XX]

## RAGIONAMENTO
[Spiega come sei arrivato a questa stima, citando gli esempi di riferimento se disponibili]

## NOTE
[Eventuali osservazioni o incertezze]
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
        file_path: Optional[str] = None,
        history: Optional[List[Dict]] = None,
        knowledge_context: Optional[List[Dict]] = None,
        examples_context: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Chat interattiva con contesto opzionale di un disegno e conoscenza aziendale

        Args:
            message: Messaggio utente
            file_path: Path opzionale a un disegno da discutere
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

        # Aggiungi file se presente
        if file_path:
            try:
                file_part = self._load_file_as_part(file_path)
                parts.append({"inline_data": file_part})
                parts.append("\n[Disegno tecnico allegato sopra - ANALIZZALO]\n\n")
            except Exception as e:
                logger.warning(f"Could not load file for chat: {e}")

        # Aggiungi storico conversazione
        if history:
            parts.append("=== CONVERSAZIONE ===\n")
            for msg in history[-10:]:  # Ultimi 10 messaggi
                role = "UTENTE" if msg.get("role") == "user" else "ASSISTENTE"
                parts.append(f"{role}: {msg.get('content', '')}\n\n")

        parts.append(f"UTENTE: {message}\n\nASSISTENTE:")

        try:
            response = await model.generate_content_async(parts)
            return {
                "success": True,
                "response": response.text,
                "used_knowledge": len(knowledge_context) if knowledge_context else 0,
                "used_examples": len(examples_context) if examples_context else 0
            }
        except Exception as e:
            logger.error(f"Chat error: {e}")
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

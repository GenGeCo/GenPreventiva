"""
ChromaDB Service - Vector database per similarity search
Gestisce embeddings e ricerca semantica dei disegni tecnici
"""
import chromadb
from chromadb.config import Settings as ChromaSettings
import google.generativeai as genai
from typing import List, Dict, Any, Optional
import uuid
import logging
from config import settings

logger = logging.getLogger(__name__)


class ChromaDBService:
    def __init__(self):
        self._client = None
        self._collection = None
        self._embedding_model = None

    def _get_client(self) -> chromadb.PersistentClient:
        """Lazy initialization del client ChromaDB"""
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=str(settings.CHROMADB_PATH),
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
        return self._client

    def _get_collection(self):
        """Ottiene o crea la collection per i disegni CNC"""
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=settings.CHROMA_COLLECTION_NAME,
                metadata={"description": "CNC technical drawings embeddings"}
            )
        return self._collection

    def _get_embedding(self, text: str) -> List[float]:
        """Genera embedding usando Google text-embedding-004"""
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY non configurata")

        genai.configure(api_key=settings.GEMINI_API_KEY)

        result = genai.embed_content(
            model=f"models/{settings.EMBEDDING_MODEL}",
            content=text,
            task_type="retrieval_document"
        )
        return result['embedding']

    def _get_query_embedding(self, text: str) -> List[float]:
        """Genera embedding per query (task_type diverso)"""
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY non configurata")

        genai.configure(api_key=settings.GEMINI_API_KEY)

        result = genai.embed_content(
            model=f"models/{settings.EMBEDDING_MODEL}",
            content=text,
            task_type="retrieval_query"
        )
        return result['embedding']

    def add_learning_example(
        self,
        example_id: int,
        embedding_text: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        Aggiunge un esempio di apprendimento al vector store

        Args:
            example_id: ID del LearningExample nel DB
            embedding_text: Testo da cui generare l'embedding
            metadata: Metadati associati (costo, macchina, materiale, etc.)

        Returns:
            chroma_id: ID univoco nel vector store
        """
        collection = self._get_collection()
        chroma_id = f"example_{example_id}_{uuid.uuid4().hex[:8]}"

        try:
            embedding = self._get_embedding(embedding_text)

            # Prepara metadata (ChromaDB accetta solo tipi semplici)
            clean_metadata = {
                "example_id": example_id,
                "type": "learning_example"
            }
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    clean_metadata[key] = value
                elif value is not None:
                    clean_metadata[key] = str(value)

            collection.add(
                ids=[chroma_id],
                embeddings=[embedding],
                documents=[embedding_text],
                metadatas=[clean_metadata]
            )

            logger.info(f"Added learning example {example_id} to ChromaDB with id {chroma_id}")
            return chroma_id

        except Exception as e:
            logger.error(f"Error adding to ChromaDB: {e}")
            raise

    def search_similar(
        self,
        query_text: str,
        n_results: int = None
    ) -> List[Dict[str, Any]]:
        """
        Cerca gli esempi più simili alla query

        Args:
            query_text: Testo della query (descrizione del nuovo disegno)
            n_results: Numero di risultati (default da settings)

        Returns:
            Lista di risultati con metadata e score
        """
        if n_results is None:
            n_results = settings.TOP_K_SIMILAR

        collection = self._get_collection()

        try:
            query_embedding = self._get_query_embedding(query_text)

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )

            # Formatta i risultati
            formatted_results = []
            if results and results['ids'] and results['ids'][0]:
                for i, chroma_id in enumerate(results['ids'][0]):
                    formatted_results.append({
                        "chroma_id": chroma_id,
                        "document": results['documents'][0][i] if results['documents'] else None,
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                        "distance": results['distances'][0][i] if results['distances'] else None,
                        "similarity_score": 1 - results['distances'][0][i] if results['distances'] else None
                    })

            logger.info(f"Found {len(formatted_results)} similar examples")
            return formatted_results

        except Exception as e:
            logger.error(f"Error searching ChromaDB: {e}")
            raise

    def delete_example(self, chroma_id: str) -> bool:
        """Elimina un esempio dal vector store"""
        collection = self._get_collection()
        try:
            collection.delete(ids=[chroma_id])
            logger.info(f"Deleted example {chroma_id} from ChromaDB")
            return True
        except Exception as e:
            logger.error(f"Error deleting from ChromaDB: {e}")
            return False

    def get_collection_stats(self) -> Dict[str, Any]:
        """Ritorna statistiche sulla collection"""
        collection = self._get_collection()
        return {
            "name": collection.name,
            "count": collection.count(),
            "metadata": collection.metadata
        }

    def reset_collection(self) -> bool:
        """Reset completo della collection (ATTENZIONE: elimina tutto!)"""
        try:
            client = self._get_client()
            client.delete_collection(settings.CHROMA_COLLECTION_NAME)
            self._collection = None
            logger.warning("ChromaDB collection reset!")
            return True
        except Exception as e:
            logger.error(f"Error resetting collection: {e}")
            return False


# Singleton instance
_chromadb_service: Optional[ChromaDBService] = None


def get_chromadb_service() -> ChromaDBService:
    """Dependency injection per ChromaDB service"""
    global _chromadb_service
    if _chromadb_service is None:
        _chromadb_service = ChromaDBService()
    return _chromadb_service

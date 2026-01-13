"""
PDF Service - Gestione upload e storage dei file
"""
import os
import uuid
import shutil
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
import logging
from fastapi import UploadFile
from config import settings

logger = logging.getLogger(__name__)


class PDFService:
    def __init__(self):
        self.storage_path = Path(settings.STORAGE_PATH)
        self._ensure_storage_exists()

    def _ensure_storage_exists(self):
        """Crea le cartelle di storage se non esistono"""
        subdirs = ["drawings", "learning", "temp"]
        for subdir in subdirs:
            path = self.storage_path / subdir
            path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Storage directory ensured: {path}")

    def _generate_filename(self, original_filename: str) -> str:
        """Genera un nome file univoco mantenendo l'estensione"""
        ext = Path(original_filename).suffix.lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        return f"{timestamp}_{unique_id}{ext}"

    def _validate_file(self, file: UploadFile) -> Tuple[bool, Optional[str]]:
        """Valida il file caricato"""
        if not file.filename:
            return False, "Nome file mancante"

        ext = Path(file.filename).suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            return False, f"Estensione non permessa: {ext}. Permesse: {settings.ALLOWED_EXTENSIONS}"

        return True, None

    async def save_drawing(
        self,
        file: UploadFile,
        user_id: int
    ) -> Tuple[str, str, int]:
        """
        Salva un disegno caricato

        Args:
            file: File caricato
            user_id: ID utente

        Returns:
            Tuple (filename, relative_path, file_size)
        """
        valid, error = self._validate_file(file)
        if not valid:
            raise ValueError(error)

        filename = self._generate_filename(file.filename)
        user_dir = self.storage_path / "drawings" / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        file_path = user_dir / filename
        relative_path = f"drawings/{user_id}/{filename}"

        # Salva il file
        content = await file.read()
        file_size = len(content)

        if file_size > settings.MAX_UPLOAD_SIZE:
            raise ValueError(f"File troppo grande: {file_size} bytes. Max: {settings.MAX_UPLOAD_SIZE}")

        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Saved drawing: {relative_path} ({file_size} bytes)")
        return filename, relative_path, file_size

    async def save_learning_example(
        self,
        file: UploadFile,
        user_id: int
    ) -> Tuple[str, str, int]:
        """
        Salva un file per learning example

        Args:
            file: File caricato
            user_id: ID utente

        Returns:
            Tuple (filename, relative_path, file_size)
        """
        valid, error = self._validate_file(file)
        if not valid:
            raise ValueError(error)

        filename = self._generate_filename(file.filename)
        learning_dir = self.storage_path / "learning"
        learning_dir.mkdir(parents=True, exist_ok=True)

        file_path = learning_dir / filename
        relative_path = f"learning/{filename}"

        content = await file.read()
        file_size = len(content)

        if file_size > settings.MAX_UPLOAD_SIZE:
            raise ValueError(f"File troppo grande: {file_size} bytes. Max: {settings.MAX_UPLOAD_SIZE}")

        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Saved learning example: {relative_path} ({file_size} bytes)")
        return filename, relative_path, file_size

    def get_absolute_path(self, relative_path: str) -> Path:
        """Converte path relativo in assoluto"""
        return self.storage_path / relative_path

    def delete_file(self, relative_path: str) -> bool:
        """Elimina un file dallo storage"""
        try:
            file_path = self.get_absolute_path(relative_path)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted file: {relative_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting file {relative_path}: {e}")
            return False

    def file_exists(self, relative_path: str) -> bool:
        """Verifica se un file esiste"""
        return self.get_absolute_path(relative_path).exists()

    def get_mime_type(self, filename: str) -> str:
        """Ritorna il MIME type basato sull'estensione"""
        ext = Path(filename).suffix.lower()
        mime_types = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        return mime_types.get(ext, "application/octet-stream")

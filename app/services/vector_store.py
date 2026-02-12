"""Векторное хранилище для RAG-системы на FAISS."""
import json
from pathlib import Path
from typing import List, Tuple

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None  # type: ignore

from app.utils.logger import logger


class VectorStore:
    """Класс для работы с векторным хранилищем FAISS."""
    
    def __init__(self, index_path: Path | str = "data/vector_store.faiss", chunks_path: Path | str = "data/vector_store_chunks.json") -> None:
        """
        Инициализация векторного хранилища.
        
        Args:
            index_path: Путь к файлу FAISS индекса
            chunks_path: Путь к файлу с текстовыми чанками
        """
        self.index_path = Path(index_path)
        self.chunks_path = Path(chunks_path)
        self.index: faiss.Index | None = None
        self.dimension: int = 3072  # Размерность эмбеддингов gemini-embedding-001
        self.chunks: List[str] = []  # Хранилище текстовых чанков
        self.chunks_metadata: List[dict] = []  # Метаданные чанков (имя файла и т.д.)
        
    def _init_index(self) -> None:
        """Инициализирует FAISS индекс."""
        if faiss is None:
            raise ImportError("FAISS не установлен. Установите: pip install faiss-cpu")
        
        if self.index is None:
            # Используем L2 расстояние (Euclidean)
            self.index = faiss.IndexFlatL2(self.dimension)
            logger.info(f"Initialized FAISS index with dimension {self.dimension}")
    
    def load_index(self) -> bool:
        """
        Загружает индекс и чанки из файлов, если они существуют.
        
        Returns:
            True если индекс загружен, False если файл не найден
        """
        if not self.index_path.exists() or not self.chunks_path.exists():
            logger.info("FAISS index or chunks file not found, will create new index")
            return False
        
        try:
            if faiss is None:
                logger.warning("FAISS not available, cannot load index")
                return False
            
            self._init_index()
            self.index = faiss.read_index(str(self.index_path))
            
            # Загружаем чанки
            with open(self.chunks_path, "r", encoding="utf-8") as f:
                self.chunks = json.load(f)
            
            logger.info(f"Loaded FAISS index from {self.index_path} with {len(self.chunks)} chunks")
            return True
        except Exception as e:
            logger.error(f"Error loading FAISS index: {e}", exc_info=True)
            return False
    
    def save_index(self) -> None:
        """Сохраняет индекс и чанки в файлы."""
        if self.index is None:
            logger.warning("No index to save")
            return
        
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self.index, str(self.index_path))
            
            # Сохраняем чанки
            with open(self.chunks_path, "w", encoding="utf-8") as f:
                json.dump(self.chunks, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Saved FAISS index to {self.index_path} with {len(self.chunks)} chunks")
        except Exception as e:
            logger.error(f"Error saving FAISS index: {e}", exc_info=True)
    
    def clear(self) -> None:
        """Очищает индекс и чанки."""
        self.chunks = []
        self.chunks_metadata = []
        self.index = None
        logger.info("Vector store cleared")
    
    def add_embeddings(self, embeddings: np.ndarray, chunks: List[str], chunks_metadata: List[dict] | None = None) -> None:
        """
        Добавляет эмбеддинги и соответствующие чанки в индекс.
        
        Args:
            embeddings: Массив эмбеддингов (numpy array, shape: [n_chunks, dimension])
            chunks: Список текстовых чанков
            chunks_metadata: Список метаданных для каждого чанка (например, [{"filename": "file.txt"}, ...])
        """
        if faiss is None:
            raise ImportError("FAISS не установлен")
        
        if len(embeddings) != len(chunks):
            raise ValueError(f"Mismatch: {len(embeddings)} embeddings but {len(chunks)} chunks")
        
        if chunks_metadata is None:
            chunks_metadata = [{}] * len(chunks)
        
        if len(chunks_metadata) != len(chunks):
            raise ValueError(f"Mismatch: {len(chunks_metadata)} metadata but {len(chunks)} chunks")
        
        self._init_index()
        
        # Нормализуем эмбеддинги для лучшего поиска
        embeddings = embeddings.astype('float32')
        
        # Если индекс уже существует, добавляем к нему, иначе создаем новый
        if self.index is not None and self.index.ntotal > 0:
            # Добавляем к существующему индексу
            self.index.add(embeddings)
        else:
            # Создаем новый индекс
            self.index = faiss.IndexFlatL2(self.dimension)
            self.index.add(embeddings)
        
        # Сохраняем чанки и метаданные
        self.chunks.extend(chunks)
        self.chunks_metadata.extend(chunks_metadata)
        
        logger.info(f"Added {len(chunks)} chunks to vector store (total: {len(self.chunks)})")
    
    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> List[Tuple[str, float, dict]]:
        """
        Ищет наиболее похожие чанки по запросу.
        
        Args:
            query_embedding: Эмбеддинг запроса (1D array)
            top_k: Количество результатов для возврата
        
        Returns:
            Список кортежей (текст чанка, расстояние, метаданные)
        """
        if self.index is None or self.index.ntotal == 0:
            logger.warning("Vector store is empty, returning empty results")
            return []
        
        query_embedding = query_embedding.astype('float32').reshape(1, -1)
        
        # Ищем k ближайших соседей
        distances, indices = self.index.search(query_embedding, top_k)
        
        results: List[Tuple[str, float, dict]] = []
        for idx, distance in zip(indices[0], distances[0]):
            if 0 <= idx < len(self.chunks):
                metadata = self.chunks_metadata[idx] if idx < len(self.chunks_metadata) else {}
                results.append((self.chunks[idx], float(distance), metadata))
        
        logger.info(f"Found {len(results)} similar chunks for query")
        return results

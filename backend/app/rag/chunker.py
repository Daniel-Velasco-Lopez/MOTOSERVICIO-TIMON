import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Chunker:
    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str) -> list[str]:
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            if end >= len(text):
                chunks.append(text[start:])
                break
            split_at = text.rfind(" ", start, end)
            if split_at > start + self.chunk_size // 2:
                end = split_at
            chunks.append(text[start:end])
            start = end - self.overlap
        return chunks

    def chunk_messages(self, history: list[dict]) -> list[dict]:
        chunks = []
        for msg in history:
            text = f"{msg.get('mensaje', '')} {msg.get('respuesta', '')}"
            text_chunks = self.chunk_text(text)
            for i, chunk in enumerate(text_chunks):
                chunks.append({
                    "text": chunk,
                    "timestamp": msg.get("timestamp"),
                    "chunk_index": i,
                    "total_chunks": len(text_chunks),
                })
        return chunks

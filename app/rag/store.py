from __future__ import annotations
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from pypdf import PdfReader


class LocalRagStore:
    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.sources: list[str] = []
        self.vectorizer = TfidfVectorizer(stop_words="english", max_features=12000)
        self.matrix = None

    def ingest_text(self, text: str, source: str) -> int:
        parts = [text[i:i+1200] for i in range(0, len(text), 1000) if text[i:i+1200].strip()]
        self.chunks.extend(parts)
        self.sources.extend([source] * len(parts))
        self._fit()
        return len(parts)

    def ingest_pdf(self, path: str) -> int:
        reader = PdfReader(path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return self.ingest_text(text, Path(path).name)

    def _fit(self) -> None:
        self.matrix = self.vectorizer.fit_transform(self.chunks) if self.chunks else None

    def query(self, question: str, top_k: int = 4) -> list[dict]:
        if self.matrix is None:
            return []
        q = self.vectorizer.transform([question])
        scores = cosine_similarity(q, self.matrix)[0]
        idxs = scores.argsort()[::-1][:top_k]
        return [{"source": self.sources[i], "score": float(scores[i]), "text": self.chunks[i]} for i in idxs if scores[i] > 0]

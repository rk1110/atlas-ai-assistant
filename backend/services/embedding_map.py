"""The embedding map: every chunk's 384-number vector squashed into a 2D point to plot.

You can't look at 384 dimensions, but you can look at a scatter plot. t-SNE (t-distributed
Stochastic Neighbor Embedding) places points so that chunks which are NEIGHBOURS in the
384-D space stay neighbours in 2D. Clusters on the map are topics the embedding model
learned: Acme's HR policies in one island, GitLab's remote-work pages in another.

How to read it (and not over-read it): closeness within a cluster is meaningful; distances
BETWEEN clusters and the axes are not. t-SNE keeps local structure, not global geometry.
Alternatives: PCA (linear, keeps global spread, muddier clusters; can place new points like
a query) and UMAP (similar to t-SNE, faster at scale, one more dependency).

Computing it takes a few seconds, so the result is cached until the chunks change.
"""

import asyncio
from datetime import datetime

import anyio
import numpy as np
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models import ChunkRecord, DocumentRecord

PREVIEW_CHARS = 160


class MapPoint(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    source: str
    heading: str | None
    preview: str
    x: float  # roughly -1..1; only relative positions mean anything
    y: float


class EmbeddingMapService:
    method = "t-SNE"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self._cache: tuple[tuple[int, datetime | None], list[MapPoint]] | None = None
        self._lock = asyncio.Lock()  # two page loads at once compute it only once

    async def points(self) -> list[MapPoint]:
        async with self._lock:
            version = await self._version()
            if self._cache and self._cache[0] == version:
                return self._cache[1]
            points = await self._compute()
            self._cache = (version, points)
            return points

    async def _version(self) -> tuple[int, datetime | None]:
        """Changes whenever a chunk is added or removed (re-ingestion replaces chunks)."""
        async with self._session_factory() as session:
            count, newest = (
                await session.execute(select(func.count(), func.max(ChunkRecord.created_at)))
            ).one()
        return count, newest

    async def _compute(self) -> list[MapPoint]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(ChunkRecord, DocumentRecord)
                    .join(DocumentRecord, ChunkRecord.document_id == DocumentRecord.id)
                    .where(DocumentRecord.status == "ready")
                    .order_by(ChunkRecord.document_id, ChunkRecord.ordinal)
                )
            ).all()
        if len(rows) < 3:
            return []
        vectors = np.array([chunk.embedding for chunk, _ in rows], dtype=np.float32)
        coordinates = await anyio.to_thread.run_sync(project, vectors)
        return [
            MapPoint(
                chunk_id=str(chunk.id),
                document_id=document.id,
                title=document.title,
                source=document.source,
                heading=chunk.heading,
                preview=" ".join(chunk.text.split())[:PREVIEW_CHARS],
                x=round(float(x), 4),
                y=round(float(y), 4),
            )
            for (chunk, document), (x, y) in zip(rows, coordinates, strict=True)
        ]


def project(vectors: np.ndarray) -> np.ndarray:
    """384-D -> 2-D with t-SNE, scaled to -1..1. Fixed random_state: the same corpus always
    gives the same map, so it doesn't reshuffle on every page load."""
    from sklearn.manifold import TSNE  # heavy import, only when the map is first requested

    perplexity = min(30.0, (len(vectors) - 1) / 3)  # t-SNE needs perplexity < n points
    coordinates = TSNE(
        n_components=2, metric="cosine", init="pca", perplexity=perplexity, random_state=0
    ).fit_transform(vectors)
    coordinates -= coordinates.mean(axis=0)
    return coordinates / (np.abs(coordinates).max() or 1.0)

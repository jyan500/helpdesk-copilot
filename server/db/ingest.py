"""
Ingest the knowledge base (Phase 3) — SCAFFOLD. Fill in the TODOs.

This is the RAG "build the index" step, and it's the sibling of db/seed.py: where
seed.py loads customers/orders, this loads ARTICLES and their CHUNKS+EMBEDDINGS.
Run it from the server/ directory (after seed.py has created the DB):

    python -m db.ingest

The pipeline, end to end:
    1. LOAD    read every .md file in server/knowledge/ -> (title, body)
    2. CHUNK   slice each body into small overlapping pieces  <-- the quality knob
    3. EMBED   turn each chunk into a 384-float vector (utils.embeddings)
    4. STORE   write one Article row + its DocChunk rows (text + vector + index)

Re-runnable by design: we delete existing articles first (cascade clears their
chunks) so running it again gives a clean, predictable index — just like seed.py.

EXPERIMENT here (this is the Phase 3 learning checkpoint in practice): change
CHUNK_SIZE / CHUNK_OVERLAP, re-ingest, then ask the agent the same question and
watch retrieval quality change. Big chunks = more context but blurrier vectors;
tiny chunks = sharp vectors but answers can lose surrounding context.
"""
import asyncio
from pathlib import Path

from sqlalchemy import delete, select

from db.models import Article, Base, DocChunk
from db.session import AsyncSessionLocal, engine
from utils.embeddings import embed_texts

# server/knowledge/*.md  (this file is server/db/ingest.py -> parent.parent = server/)
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"

# ---- the quality knobs. Measured in WORDS here (simplest to reason about). ----
CHUNK_SIZE = 80      # words per chunk
CHUNK_OVERLAP = 20   # words shared between consecutive chunks (keeps sentences whole)


def load_articles() -> list[tuple[str, str, str]]:
    """Read every .md file -> list of (slug, title, body).

    slug  = filename without extension, e.g. "refunds-and-returns"
    title = the first markdown H1 line ("# Refunds & Returns" -> "Refunds & Returns")
    body  = everything after the title line
    """
    articles: list[tuple[str, str, str]] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        lines = text.splitlines()
        # First line is "# Title"; strip the leading '# ' for the citation title.
        title = lines[0].lstrip("# ").strip()
        body = "\n".join(lines[1:]).strip()
        articles.append((path.stem, title, body))
    return articles


def chunk_text(body: str) -> list[str]:
    """Split one article body into overlapping chunks of ~CHUNK_SIZE words.

    A sliding window: take CHUNK_SIZE words, then step forward by
    (CHUNK_SIZE - CHUNK_OVERLAP) words so each chunk re-includes the tail of the
    previous one. The overlap is what stops a sentence that straddles a boundary
    from being cut in half and losing its meaning.

    Pointers:
      - words = body.split()                       # whitespace tokenize
      - step = CHUNK_SIZE - CHUNK_OVERLAP           # how far the window advances
      - loop i = 0, step, 2*step, ...  while i < len(words):
            chunk_words = words[i : i + CHUNK_SIZE]
            chunks.append(" ".join(chunk_words))
      - stop once the window reaches the end (the last chunk may be shorter).
      - guard: if step <= 0 you'd loop forever — CHUNK_OVERLAP must be < CHUNK_SIZE.

    (This is deliberately naive — word windows, ignoring sentence/paragraph
    boundaries. Smarter chunking is a great thing to experiment with later.)
    """
    # TODO: implement the sliding window per the pointers above.
    words = body.split()
    step = CHUNK_SIZE - CHUNK_OVERLAP
    if step <= 0:
        raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i:i + CHUNK_SIZE]
        chunks.append(" ".join(chunk_words))
        i = i + step 
    return chunks

async def ingest() -> None:
    # Make sure the tables exist. create_all only creates what's missing, so this
    # won't touch the customers/orders seeded by seed.py.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    articles = load_articles()
    print(f"loaded {len(articles)} articles from {KNOWLEDGE_DIR}")

    async with AsyncSessionLocal() as session:
        # Clean slate so re-running is idempotent. Deleting Articles cascades to
        # their DocChunks via the relationship's cascade="all, delete-orphan".
        existing = (await session.execute(select(Article))).scalars().all()
        for art in existing:
            await session.delete(art)
        await session.commit()

        total_chunks = 0
        for slug, title, body in articles:
            # TODO: build the index for ONE article:
            #   1. chunks = chunk_text(body)
            #   2. vectors = embed_texts(chunks)        # batched: one call per article
            #   3. create the Article with its DocChunks attached, e.g.:
            #        article = Article(
            #            slug=slug, title=title, body=body,
            #            chunks=[
            #                DocChunk(chunk_index=i, content=c, embedding=v)
            #                for i, (c, v) in enumerate(zip(chunks, vectors))
            #            ],
            #        )
            #        session.add(article)
            #   4. total_chunks += len(chunks); print a per-article line so you can
            #      see how many chunks each article produced (your quality knob).
            chunks = chunk_text(body)
            vectors = embed_texts(chunks)
            article = Article(
                slug=slug, title=title, body=body,
                chunks=[
                    DocChunk(chunk_index=i, content=c, embedding=v) for i, (c,v) in enumerate(zip(chunks, vectors))
                ]
            )
            session.add(article)
            total_chunks += len(chunks)
        await session.commit()
        print(f"ingested {len(articles)} articles, {total_chunks} chunks")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(ingest())

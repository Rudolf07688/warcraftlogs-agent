# Contract: embedder (contract 2, shipped with the sc-111 milestone)

Module `backend/app/kb/embedder.py`. 044 codes against the protocol with its own fake.

```python
EmbedTask = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]
DIMENSIONS = 768

class Embedder(Protocol):
    model: str
    async def embed(self, texts: Sequence[str], *, task: EmbedTask) -> list[list[float]]: ...
        # one unit-norm 768-d vector per text, same order; raises on failure

def get_embedder() -> Embedder | None   # None when embeddings are unavailable; never raises
def set_embedder(embedder: Embedder | None) -> None   # test injection (None clears it)
def normalise(vector: Sequence[float]) -> list[float]  # L2; a zero vector is returned as is
```

- `get_embedder()` order: the injected embedder, else `None` when `kb_embed_enabled` is off or
  the genai client can't be built, else one cached `VertexEmbedder(settings.kb_embed_model)`.
  Until `config.py` is granted (sc-112) the model defaults to `gemini-embedding-001` and
  "enabled" means "a genai client can be built".
- `VertexEmbedder.embed` sends at most `kb_embed_request_batch` texts per request with
  `output_dimensionality=768`, `auto_truncate=True` and the task type, through the shared
  rate-limit loop; raises `ModelRateLimited` or the SDK error when it gives up. It checks each
  returned vector has 768 values.
- Callers never pass an empty list (returns `[]` without a call).

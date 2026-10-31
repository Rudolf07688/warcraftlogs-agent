# Research: 033

- **Decision**: build the Models API listing in `models.py` from `provider.anthropic_client().models.list()`. **Rationale**: the SDK auto-pages; no provider.py function needed (scrum master preference). **Alternative**: a `provider.list_models()`; rejected, extra surface.
- **Decision**: second id regex for the API form, chosen by active provider. **Rationale**: `claude-haiku-4-5-20251001` does not match the Vertex regex, so sibling/class logic would silently return None. **Alternative**: normalise everything to Vertex form; rejected, ids must stay callable as served.
- **Decision**: zero entries means `CatalogUnavailable`, in `_list_catalog` for both providers. **Rationale**: sc-159; one place.
- **Decision**: cache key `ext:models:v2:{provider}:{project}:{location}:{sig}`. **Rationale**: provider split without migration; old keys expire.
- **Decision**: no edits to `model_retry.py`; test it with Anthropic 429/529 fakes. **Rationale**: it is provider-agnostic already.

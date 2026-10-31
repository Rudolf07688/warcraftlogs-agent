# Data model: 033

No new entities. `CatalogEntry` is reused for Anthropic API rows (`publisher="anthropic"`, `name` base id, `version_id` date or "default", `stage=None`). `ModelCatalog` is unchanged and stored per provider. `ModelsResponse` gains `provider: "vertex" | "anthropic"` (default "vertex").

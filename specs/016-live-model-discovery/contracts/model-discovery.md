# Contract: Model Discovery (internal Python interface)

The only external interface, `GET /api/models`, is **unchanged**:

```json
{ "models": ["gemini-3.1-pro-preview", "gemini-2.5-pro", "gemini-3.8-flash", "…"],
  "default": "gemini-3.8-flash",
  "degraded": false }
```

Session auth, the response model (`ModelsResponse`) and the frontend dropdown stay as
they are. Below are the internal contracts that the tasks build and the tests pin down.

## `wcl_agent/vertex.py` (new)

```python
def model_location() -> str: ...
    # WCL_MODEL_LOCATION, default "global". The only place that knows where models run.

def project_id() -> str | None: ...
    # GOOGLE_CLOUD_PROJECT, else the ADC default project.

def genai_client() -> "genai.Client": ...
    # genai.Client(vertexai=True, project=project_id(), location=model_location())

def anthropic_client(**kwargs) -> "AnthropicVertex": ...       # probes pass max_retries=0
def async_anthropic_client(**kwargs) -> "AsyncAnthropicVertex": ...
    # region=model_location(), project_id=project_id()

def adk_client_kwargs() -> dict: ...
    # {"vertexai": True, "location": model_location()} for ADK Gemini models

class CatalogUnavailable(Exception): ...

def list_publisher_models(publisher: Literal["google", "anthropic"]) -> list[CatalogEntry]: ...
    # GET https://aiplatform.googleapis.com/v1beta1/publishers/{publisher}/models
    # pageSize=100, follows nextPageToken, 10 s per request, x-goog-user-project header.
    # Raises CatalogUnavailable on any transport, auth, HTTP or parse failure.
```

**Guarantee**: after this feature, no module outside `vertex.py` constructs
`genai.Client`, `AnthropicVertex` or `AsyncAnthropicVertex`, or reads
`GOOGLE_CLOUD_LOCATION`, for a model call. `RetryingGemini` and the web-search sub-agent
pass `client_kwargs={"location": model_location()}` to ADK. A test asserts every
factory's location (FR-017).

## `wcl_agent/models.py`

Pure helpers (no I/O):

```python
def classify(entry: CatalogEntry, classes: Sequence[ClassSetting]) -> Candidate | None: ...
def candidates_by_class(entries: Iterable[CatalogEntry], classes: Sequence[ClassSetting]
                        ) -> dict[tuple[str, str], list[Candidate]]: ...
    # newest first; GA before preview on a tie; experimental dropped
def pick_per_class(setting: ClassSetting, candidates: Sequence[Candidate],
                   outcomes: Mapping[str, ProbeOutcome]) -> ClassResult: ...
    # keep = setting.keep; the setting also names the class when it has no candidates
    # walk in order: passed → keep; not_enabled/failed → next; no_quota → stop
def choose_default(models: Sequence[str], configured: str,
                   classes: Sequence[ClassResult]) -> str: ...
    # configured if served, else newest flash, else models[0]
```

Probe layer (blocking, run in threads):

```python
def check_model(call: Callable[[], object]) -> ProbeOutcome: ...
    # 404/403 → not_enabled; 429 → sleep 2 s, retry once → no_quota; other → failed
def _probe_gemini(client, model_id) -> bool: ...      # unchanged signature (static path)
def _probe_anthropic(client, model_id) -> bool: ...   # unchanged signature (static path)
```

Both probe paths send one dummy function declaration with a one-token limit and a 10 s
timeout.

Entry point (still blocking; the backend runs it under `asyncio.to_thread`):

```python
def discover_models(
    *,
    mode: Literal["catalog", "static"] = "static",
    gemini_ids: list[str],
    anthropic_ids: list[str],
    configured_default: str,
    fallback_models: list[str],
    gemini_classes: Sequence[ClassSetting] = (),
    anthropic_classes: Sequence[ClassSetting] = (),
) -> ModelCatalog: ...
```

| Situation | `source` | `degraded` | `models` |
|---|---|---|---|
| `mode="static"`, something passes | `static` | False | the static ids that passed, in configured order |
| `mode="catalog"`, listing OK, something kept | `catalog` | False | kept ids in class order |
| `mode="catalog"`, either listing fails | `fallback` | False | the static ids that passed (one WARNING logged) |
| nothing passes in any mode, or no client can be built | `degraded` | True | `fallback_models or [configured_default]` |

If one publisher's listing fails while the other succeeds, the listing counts as failed
(`fallback`). A half-catalog dropdown would hide models with no visible reason.

## `wcl_agent/cache.py` / `cache_models.py`

```python
class CacheFamily(StrEnum):
    MODEL_CATALOG = "model_catalog"          # FamilyConfig(21600, 0.50)

class keys:
    @staticmethod
    def model_catalog(project: str, location: str, sig: str) -> str: ...
        # "ext:models:v1:{project}:{location}:{sig}"

class ClassResult(BaseModel): ...
class ModelCatalog(BaseModel): ...           # see data-model.md
```

## `backend/app/main.py`: `_models` boot step

```python
catalog = await get_or_load(
    CacheFamily.MODEL_CATALOG, key, ModelCatalog,
    lambda: asyncio.to_thread(discover_models, ...),
    ttl=lambda v: family_ttl(CacheFamily.MODEL_CATALOG)
                  if v.source == "catalog" and not v.degraded else 0,
)
```

- In `static` mode the cache is skipped: `discover_models` is called directly, as today.
- `app.state.models`, `app.state.default_model` and `app.state.models_degraded` are set
  from `catalog`.
- On a hit, the per-class lines are logged from `catalog.classes`, and the warning for
  each fixed-purpose model missing from `catalog.listed` is logged too.
- Step detail: `"{n} models ({source})"` with `", cached"` on a hit.

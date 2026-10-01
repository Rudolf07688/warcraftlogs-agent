---
name: pydantic-v2-reference
description: |
  Use this skill when working with Pydantic v2 and pydantic-settings. Very short reference for choosing the right model/config pattern and quickly locating the important library modules to inspect.
---

# Pydantic v2 Reference

## Use When

Use this skill for:
- request/response schemas,
- internal typed data contracts,
- app configuration,
- env-based settings,
- validation and serialization behavior,
- custom validators or serializers.

## Pattern Guide

- **`BaseModel`**: default for API schemas, internal contracts, nested typed payloads.
- **`BaseSettings`** from `pydantic_settings`: app config loaded from env, `.env`, secrets files.
- **`RootModel`**: model wraps one top-level value.
- **`TypeAdapter`**: validate/serialize arbitrary types without creating a full model.
- **`ConfigDict` / `model_config`**: model behavior, e.g. strictness, extra handling, frozen, populate rules.
- **`Field(...)`**: constraints, descriptions, defaults, aliases.
- **`@field_validator`**: single-field logic.
- **`@model_validator`**: cross-field or whole-model logic.
- **`@field_serializer` / `@model_serializer`**: output shaping.
- **`SecretStr` / `SecretBytes`**: sensitive config values.

## Project Defaults

- Use `BaseModel` for all API contracts.
- Use `BaseSettings` for config, not ad hoc env parsing.
- Use nested settings/models for domain grouping.
- Prefer `model_validate()` / `model_dump()` over legacy v1 mental models.
- Keep `model_config` explicit on shared models.
- Use `TypeAdapter` for lightweight validation helpers.

## Important Import Paths

Inspect these first when you need repo-level capability awareness:

```python
pydantic.BaseModel
pydantic.RootModel
pydantic.TypeAdapter
pydantic.Field
pydantic.ConfigDict
pydantic.field_validator
pydantic.model_validator
pydantic.field_serializer
pydantic.model_serializer
pydantic.SecretStr
pydantic.SecretBytes
pydantic.types
pydantic.networks
pydantic_settings.BaseSettings
pydantic_settings.SettingsConfigDict
```

## Useful Repo / Module Paths

When inspecting installed library code or headers, start here conceptually:

```text
pydantic/main.py              # BaseModel core behavior
pydantic/root_model.py        # RootModel
pydantic/type_adapter.py      # TypeAdapter
pydantic/fields.py            # Field definitions
pydantic/config.py            # ConfigDict and config behavior
pydantic/functional_validators.py
pydantic/functional_serializers.py
pydantic/types.py             # constrained and helper types
pydantic/networks.py          # URLs, DSNs, email-like/network types
pydantic_settings/main.py     # BaseSettings
pydantic_settings/sources.py  # settings source resolution
```

## Decision Hints

- Need API/body schema -> `BaseModel`
- Need env/config loading -> `BaseSettings`
- Need validate `list[MyType]` or `dict[str, X]` directly -> `TypeAdapter`
- Need one wrapped root value -> `RootModel`
- Need strict/shared model behavior -> `model_config = ConfigDict(...)`
- Need cross-field invariant -> `@model_validator`
- Need custom output -> serializer decorators

## Avoid

- Old v1 `Config` mental model when `model_config` is clearer.
- Manual `os.getenv()` sprawl instead of `BaseSettings`.
- Raw dict contracts where a shared `BaseModel` should exist.
- Overusing validators when types/Field constraints already solve it.

"""Force-build google-genai Pydantic serializers (deferred-build compatibility shim).

``google.genai.types`` models set ``model_config['defer_build'] = True`` (an import-speed
optimization), so each model's serializer is built lazily on first direct (de)serialization
rather than at class definition. That lazy trigger never fires for a model instance that is
created and then nested inside *another* model's ``dict`` field without ever being dumped on
its own. When google-adk nests such a model inside ``EventActions.state_delta`` and calls
``model_dump()`` — e.g. while merging parallel function-call responses — pydantic hits the
still-unbuilt ("mock") serializer and raises::

    PydanticSerializationError: Error calling function `_serialize_state_delta`:
      TypeError: 'MockValSer' object is not an instance of 'SchemaSerializer'

which aborts the agent turn. This is **not** Python-version-specific (reproduced identically
on 3.13 and 3.14) and is not fixed by bumping google-adk/google-genai/pydantic — it's
inherent to the deferred-build config. Forcing ``model_rebuild()`` on the affected classes
builds real serializers and resolves it. The shim is idempotent and cheap after the first
pass (models whose serializer is already built are skipped), and best-effort (never raises).
"""

from __future__ import annotations

import inspect
import logging

logger = logging.getLogger(__name__)

_done = False


def ensure_genai_serializers_built() -> int:
    """Build any unbuilt ``google.genai.types`` model serializers. Returns how many were fixed.

    Safe to call repeatedly; does its work once per process. Any failure is swallowed so the
    shim can never block agent startup.
    """
    global _done
    if _done:
        return 0
    try:
        from google.genai import types as genai_types
        from pydantic import BaseModel
        from pydantic_core import SchemaSerializer
    except Exception:  # noqa: BLE001 - never block startup over a compatibility shim
        return 0

    fixed = 0
    for obj in vars(genai_types).values():
        if not (inspect.isclass(obj) and issubclass(obj, BaseModel)):
            continue
        ser = obj.__dict__.get("__pydantic_serializer__")
        # A built model has a real pydantic_core.SchemaSerializer; a deferred one has a mock.
        if ser is not None and not isinstance(ser, SchemaSerializer):
            try:
                obj.model_rebuild(force=True)
                fixed += 1
            except Exception:  # noqa: BLE001 - skip any model that can't rebuild
                continue

    _done = True
    if fixed:
        logger.info("genai_compat: rebuilt %d google-genai model serializers", fixed)
    return fixed

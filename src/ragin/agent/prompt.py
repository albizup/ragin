"""Auto-generate system prompts from model schemas."""
from __future__ import annotations

from ragin.core.fields import get_ragin_meta


def generate_system_prompt(models: list[type], description: str = "") -> str:
    """
    Build a system prompt describing the available models and their fields.
    The prompt is deterministic and based solely on the Pydantic schema.
    """
    parts: list[str] = [
        "You are an AI assistant that manages the following data models.",
        "",
    ]

    if description:
        parts.append(description)
        parts.append("")

    for model_cls in models:
        parts.append(f"## {model_cls.__name__}")
        parts.append(f"Table: {model_cls.ragin_table_name()}")
        parts.append("Fields:")

        for name, field_info in model_cls.model_fields.items():
            meta = get_ragin_meta(model_cls, name)
            type_label = _type_label(field_info)
            pk = " (primary key)" if meta.get("primary_key") else ""
            desc = f" — {field_info.description}" if field_info.description else ""
            parts.append(f"  - {name}: {type_label}{pk}{desc}")

        parts.append("")

    parts.append("Use the available tools to perform operations on these models.")
    parts.append("Always confirm actions with a clear response to the user.")

    return "\n".join(parts)


def _type_label(field_info) -> str:
    ann = field_info.annotation
    return getattr(ann, "__name__", str(ann))

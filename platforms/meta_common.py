import logging

logger = logging.getLogger(__name__)

def extract_meta_entries(payload: dict):
    return payload.get("entry", []) if isinstance(payload, dict) else []

def detect_meta_platform(payload: dict) -> str | None:
    obj = payload.get("object") if isinstance(payload, dict) else None
    if obj == "instagram":
        return "instagram"
    if obj == "page":
        return "messenger"
    return None

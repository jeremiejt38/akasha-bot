import os
import json
import re
import logging
from datetime import datetime
from rapidfuzz import fuzz
from integrations.health_checker import CONNECTION_CHECK_MARKER

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = int(os.getenv("AUTO_RESPONDER_THRESHOLD", "80"))
DEFAULT_DATA_PATH = os.getenv("AUTO_RESPONDER_DATA_PATH", "./config/auto_responses_v3.json")

DATE_FIELDS = ("expires", "activity")
ACCESS_LEVELS = {"everyone": 1, "expired": 2, "testing": 3, "subscriber": 4}


def _normalize(text: str) -> str:
    return (text or "").lower().strip()


def _format_date(date_str: str) -> str:
    if not date_str:
        return "date inconnue"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return date_str


def _format_field(name: str, value) -> str:
    if value is None:
        return ""
    if isinstance(value, str) and any(fragment in name.lower() for fragment in DATE_FIELDS):
        return _format_date(value)
    return str(value)


def _get_access_level(user_data: dict | None) -> int:
    user_data = user_data or {}
    if not user_data:
        return ACCESS_LEVELS["everyone"]

    expires = user_data.get("wizarr_invite_expires")
    if expires:
        try:
            expires_at = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.astimezone()
            if expires_at <= datetime.now(expires_at.tzinfo):
                return ACCESS_LEVELS["expired"]
        except (TypeError, ValueError):
            pass

    access_type = str(user_data.get("access_type") or "").lower()
    if access_type in {"trial", "testing"}:
        return ACCESS_LEVELS["testing"]
    if access_type in {"subscriber", "subscribed"}:
        return ACCESS_LEVELS["subscriber"]
    return ACCESS_LEVELS["expired"]


def _expiration_relative(expires: str | None) -> str | None:
    if not expires:
        return None
    try:
        expires_at = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.astimezone()
        seconds = int((expires_at - datetime.now(expires_at.tzinfo)).total_seconds())
        if seconds <= 0:
            return "expiré"
        days = seconds // 86400
        if days >= 14:
            return f"dans {days // 7} semaine{'s' if days // 7 > 1 else ''}"
        if days >= 1:
            return f"dans {days} jour{'s' if days > 1 else ''}"
        hours = max(1, seconds // 3600)
        return f"dans {hours} heure{'s' if hours > 1 else ''}"
    except (TypeError, ValueError):
        return None


def _template_has_missing_value(template: str, user_data: dict | None) -> bool:
    user_data = user_data or {}
    for match in re.finditer(r"\{([^}]+)\}", template):
        full = match.group(1)
        key, separator, default = full.partition(":")
        if separator and default:
            continue
        value = _expiration_relative(user_data.get("wizarr_invite_expires")) if key == "wizarr_invite_expires_relative" else user_data.get(key, os.getenv(key))
        if value is None or value == "":
            return True
    return False


def _render_template(template: str, user_data: dict | None) -> str:
    user_data = user_data or {}

    def _replacer(match: re.Match) -> str:
        full = match.group(1)
        if ":" in full:
            key, default = full.split(":", 1)
        else:
            key, default = full, ""
        value = _expiration_relative(user_data.get("wizarr_invite_expires")) if key == "wizarr_invite_expires_relative" else user_data.get(key, os.getenv(key))
        if value is None or value == "":
            return default
        return _format_field(key, value)

    return re.sub(r"\{([^}]+)\}", _replacer, template)


def _load_knowledge_base(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = data.get("entries")
        if not isinstance(data, list):
            logger.warning("Auto-responder data file %s has no entries list; using empty knowledge base", path)
            return []
        return data
    except FileNotFoundError:
        logger.warning("Auto-responder data file %s not found; using empty knowledge base", path)
        return []
    except Exception:
        logger.exception("Failed to load auto-responder data from %s", path)
        return []


class AutoResponder:
    """Auto-responder that loads its Q&A from a JSON file.

    The JSON file can contain static answers, templates with placeholders, and
    special markers (like the connection-check marker).
    """

    def __init__(self, threshold: int = None, data_path: str = None):
        self.threshold = threshold if threshold is not None else DEFAULT_THRESHOLD
        self.data_path = data_path if data_path is not None else DEFAULT_DATA_PATH
        self.knowledge = _load_knowledge_base(self.data_path)

    def reload(self):
        """Reload the knowledge base from disk. Useful for hot-updates."""
        self.knowledge = _load_knowledge_base(self.data_path)
        logger.info("Reloaded auto-responder knowledge base from %s", self.data_path)

    def list_questions(self, limit: int = 20) -> list:
        """Return a list of (question, answer) tuples for FAQ display."""
        items = []
        for entry in self.knowledge:
            question = entry.get("question") or (entry.get("patterns", [None])[0])
            answer = entry.get("answer") or entry.get("template") or entry.get("fallback") or "..."
            if question:
                items.append((question, answer))
        return items[:limit]

    def match(self, message: str) -> tuple[dict | None, int]:
        text = _normalize(message)
        if not text:
            return None, 0

        best_entry = None
        best_score = 0
        best_priority = 0
        for entry in self.knowledge:
            priority = int(entry.get("priority", 0))
            if entry.get("marker"):
                priority = max(priority, 5)
            for pattern in entry.get("patterns", []):
                normalized_pattern = _normalize(pattern)
                score = fuzz.partial_ratio(text, normalized_pattern)
                if (score, priority) > (best_score, best_priority):
                    best_score = score
                    best_priority = priority
                    best_entry = entry
        return best_entry, best_score

    def respond(self, message: str, user_data: dict | None = None) -> str | dict | None:
        best_entry, best_score = self.match(message)
        if best_score < self.threshold or not best_entry:
            return None

        required_access = best_entry.get("min_access")
        if required_access:
            required_level = ACCESS_LEVELS.get(required_access)
            if required_level is None:
                logger.warning("Auto-responder rule has an unknown min_access value: %s", required_access)
                return best_entry.get("fallback")
            if _get_access_level(user_data) < required_level:
                return best_entry.get("fallback")

        # Special markers handled by the caller
        if best_entry.get("marker") == "connection_check":
            return CONNECTION_CHECK_MARKER
        if best_entry.get("marker"):
            return {
                "marker": best_entry["marker"],
                "answer": best_entry.get("answer"),
                "fallback": best_entry.get("fallback"),
            }

        # Static answer
        if "answer" in best_entry:
            return best_entry["answer"]

        # Templated answer requiring user data
        if "template" in best_entry:
            if _template_has_missing_value(best_entry["template"], user_data):
                return best_entry.get("fallback")
            rendered = _render_template(best_entry["template"], user_data)
            if not rendered:
                return best_entry.get("fallback")
            return rendered

        return None

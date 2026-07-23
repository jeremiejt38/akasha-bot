import os
import json
import re
import logging
from datetime import datetime
from rapidfuzz import fuzz
from integrations.health_checker import CONNECTION_CHECK_MARKER

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = int(os.getenv("AUTO_RESPONDER_THRESHOLD", "80"))
DEFAULT_DATA_PATH = os.getenv("AUTO_RESPONDER_DATA_PATH", "./config/auto_responses.json")

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


def _render_template(template: str, user_data: dict | None) -> str:
    user_data = user_data or {}

    def _replacer(match: re.Match) -> str:
        full = match.group(1)
        if ":" in full:
            key, default = full.split(":", 1)
        else:
            key, default = full, ""
        value = user_data.get(key)
        if value is None or value == "":
            return default
        return _format_field(key, value)

    return re.sub(r"\{([^}]+)\}", _replacer, template)


def _load_knowledge_base(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.warning("Auto-responder data file %s is not a list; using empty knowledge base", path)
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

    def respond(self, message: str, user_data: dict | None = None) -> str | None:
        text = _normalize(message)
        if not text:
            return None

        best_entry = None
        best_score = 0
        for entry in self.knowledge:
            for pattern in entry.get("patterns", []):
                score = fuzz.partial_ratio(text, _normalize(pattern))
                if score > best_score:
                    best_score = score
                    best_entry = entry

        if best_score < self.threshold:
            return None

        if not best_entry:
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

        # Static answer
        if "answer" in best_entry:
            return best_entry["answer"]

        # Templated answer requiring user data
        if "template" in best_entry:
            rendered = _render_template(best_entry["template"], user_data)
            if not rendered:
                return best_entry.get("fallback")
            return rendered

        return None

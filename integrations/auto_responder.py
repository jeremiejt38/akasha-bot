import os
import logging
from datetime import datetime
from rapidfuzz import fuzz
from integrations.health_checker import CONNECTION_CHECK_MARKER

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = int(os.getenv("AUTO_RESPONDER_THRESHOLD", "80"))


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


def _build_knowledge_base():
    return [
        {
            "patterns": ["salut", "bonjour", "hey", "hello", "coucou", "bonsoir", "yo"],
            "answer": "Salut ! Je suis le bot assistant d'Akasha. Comment puis-je t'aider ?",
        },
        {
            "patterns": [
                "comment s'inscrire",
                "comment rejoindre",
                "comment créer un compte",
                "je veux un compte",
                "demander une invitation",
                "invitation",
                "rejoindre akasha",
            ],
            "answer": "Pour rejoindre Akasha, demande une invitation à l'admin ou rends-toi sur https://akasha.ing et clique sur 'Frappez aux portes'.",
        },
        {
            "patterns": [
                "mon compte expire quand",
                "date d'expiration",
                "expiration",
                "mon abonnement expire",
                "jusqu'à quand",
                "jusquà quand",
                "quand expire",
            ],
            "answer": lambda u: (
                f"Ton compte est actif jusqu'au {_format_date(u.get('wizarr_invite_expires'))}."
                if u and u.get("wizarr_invite_expires")
                else "Je n'ai pas trouvé d'invitation liée à ton compte. Contacte l'admin pour vérifier."
            ),
            "needs_user": True,
        },
        {
            "patterns": ["trust score", "mon score", "score de confiance", "tracearr", "mon trust score"],
            "answer": lambda u: (
                f"Ton trust score actuel est de {u.get('tracearr_trust_score', 'N/A')}."
                if u and u.get("tracearr_trust_score") is not None
                else "Je n'ai pas de données de trust score pour ton compte. Assure-toi d'avoir lié ton compte avec /link."
            ),
            "needs_user": True,
        },
        {
            "patterns": ["comment contacter l'admin", "qui est l'admin", "contact", "aide admin", "support"],
            "answer": "Contacte l'admin directement sur Discord. Il est le seul à pouvoir gérer les invitations et les comptes.",
        },
        {
            "patterns": ["lien compte", "lier mon compte", "link", "/link", "lier discord", "lier overseerr"],
            "answer": "Utilise la commande `/link <email>` avec l'email de ton compte Akasha pour lier ton Discord et recevoir des réponses personnalisées.",
        },
        {
            "patterns": ["c'est quoi akasha", "akasha", "présentation", "quel est ce serveur", "info"],
            "answer": "Akasha est une plateforme de streaming privée. Tu peux y accéder via Plex ou Jellyfin avec une invitation.",
        },
        {
            "patterns": ["prix", "abonnement", "combien ça coûte", "tarif", "payer", "subscription"],
            "answer": "Pour les tarifs et modalités d'abonnement, contacte l'admin. Il te donnera les infos actuelles.",
        },
        {
            "patterns": ["problème connexion", "je ne peux pas me connecter", "connexion", "login", "mot de passe", "ça ne marche pas"],
            "answer": CONNECTION_CHECK_MARKER,
        },
        {
            "patterns": ["merci", "super", "ok", "ça marche", "bien reçu"],
            "answer": "Avec plaisir ! N'hésite pas si tu as d'autres questions.",
        },
    ]


class AutoResponder:
    """Lightweight auto-responder using fuzzy string matching.

    Responds to generic questions with static answers. If ``needs_user`` is True,
    the answer callable receives the user data dict loaded from the database.
    """

    def __init__(self, threshold: int = None):
        self.threshold = threshold if threshold is not None else DEFAULT_THRESHOLD
        self.knowledge = _build_knowledge_base()

    def respond(self, message: str, user_data: dict | None = None) -> str | None:
        text = _normalize(message)
        if not text:
            return None
        best_entry = None
        best_score = 0
        for entry in self.knowledge:
            for pattern in entry["patterns"]:
                score = fuzz.partial_ratio(text, _normalize(pattern))
                if score > best_score:
                    best_score = score
                    best_entry = entry
        if best_score < self.threshold:
            return None
        answer = best_entry["answer"]
        if callable(answer) and best_entry.get("needs_user"):
            return answer(user_data)
        return answer

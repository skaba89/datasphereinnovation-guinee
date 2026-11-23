"""Contact-request validation shared by the REC application and the PROD contact service."""
import re

NEEDS = {"Demande de démonstration", "Mission en régie", "Projet au forfait",
         "Plateforme Analytics / BI", "Transformation numérique", "Data & IA", "Partenariat",
         "Conseil & expertise", "Contrôle de gestion & finance", "Audit & contrôle interne",
         "Avant-vente & appels d’offres", "Candidature spontanée", "Cybersécurité & résilience",
         "Demande de devis", "Formation", "Autre demande"}
SIZES = {"nom": 120, "org": 180, "email": 254, "besoin": 80, "solution": 160, "message": 4000}
OPTIONAL = {"solution", "telephone"}
PHONE = re.compile(r"\+?[0-9][0-9 ().-]{5,28}")
# Request types offered on the public website (issue #156). REC keeps the full internal list.
PUBLIC_NEEDS = {"Demande de devis", "Demande de démonstration", "Partenariat", "Conseil & expertise", "Formation", "Autre demande"}


def validate(payload, needs=None, demo_requires_solution=True):
    if not isinstance(payload, dict) or payload.get("website"):
        raise ValueError("Demande invalide.")
    allowed = set(SIZES) | {"website", "consent", "language", "telephone"}
    if set(payload) - allowed or payload.get("consent") is not True:
        raise ValueError("Veuillez confirmer la notice de confidentialité.")
    if payload.get('language','fr') not in ('fr','en'):
        raise ValueError('Langue invalide.')
    values = {}
    for key, maximum in SIZES.items():
        value = payload.get(key, "")
        if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
            raise ValueError("Champ invalide : " + key)
        values[key] = value.strip()
        if key not in OPTIONAL and not values[key]:
            raise ValueError("Champ obligatoire : " + key)
    phone = payload.get("telephone", "")
    if not isinstance(phone, str) or len(phone) > 30 or (phone.strip() and not PHONE.fullmatch(phone.strip())):
        raise ValueError("Numéro de téléphone invalide.")
    values["telephone"] = phone.strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", values["email"]):
        raise ValueError("Adresse e-mail invalide.")
    if values["besoin"] not in (NEEDS if needs is None else needs):
        raise ValueError("Type de demande invalide.")
    if demo_requires_solution and values["besoin"] == "Demande de démonstration" and not values["solution"]:
        raise ValueError("Sélectionnez une solution.")
    if values["besoin"] != "Demande de démonstration":
        values["solution"] = ""
    return values

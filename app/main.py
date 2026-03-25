from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
from pydantic import BaseModel, Field
from typing import Optional
import datetime

from .database import engine
from .models import Livre, Utilisateur, Emprunt, Reservation, Penalite, Notification
from .crud import (
    creer_livre, lister_livres, obtenir_livre, modifier_livre, ajouter_exemplaires, supprimer_livre,
    creer_utilisateur, lister_utilisateurs, obtenir_utilisateur_par_email,
    authentifier_utilisateur, modifier_utilisateur, supprimer_utilisateur,
    creer_emprunt, lister_emprunts, marquer_retourne, confirmer_retrait_emprunt,
    creer_reservation, lister_reservations, modifier_statut_reservation,
    lister_penalites, payer_penalite,
    lister_notifications, compter_non_lues, marquer_lue, tout_marquer_lues,
    obtenir_statistiques,
    generer_codes_acces, lister_codes_acces, verifier_et_consommer_code,
    obtenir_tous_parametres, definir_parametre,
    diffuser_notification_admin,
    obtenir_parametre,
)


# ══════════════════════════════════════════════════════════════════════════════
#  MODÈLES PYDANTIC (payloads)
# ══════════════════════════════════════════════════════════════════════════════

class ConnexionPayload(BaseModel):
    email: str
    mot_de_passe: str

class InscriptionPayload(BaseModel):
    nom: str
    email: str
    mot_de_passe: str
    type_utilisateur: str
    code_acces: str

class CreerLivrePayload(BaseModel):
    titre: str
    auteur: Optional[str] = None
    isbn: Optional[str] = None
    annee_publication: Optional[int] = None
    genre: Optional[str] = None
    note: Optional[float] = None
    total_exemplaires: int = 1
    couverture: Optional[str] = None
    description: Optional[str] = None

class ModifierLivrePayload(BaseModel):
    titre: Optional[str] = None
    auteur: Optional[str] = None
    genre: Optional[str] = None
    note: Optional[float] = None
    description: Optional[str] = None
    couverture: Optional[str] = None

class AjouterExemplairesPayload(BaseModel):
    nombre: int

class CreerEmpruntPayload(BaseModel):
    utilisateur_id: int
    livre_id: int
    date_emprunt: Optional[str] = None
    date_retour_prevu: Optional[str] = None
    en_ligne: bool = False  # True = emprunt initié en ligne, délai 24h pour récupérer

class CreerReservationPayload(BaseModel):
    utilisateur_id: int
    livre_id: int

class ModifierStatutReservationPayload(BaseModel):
    statut: str  # attente | pret | annule

class GenererCodesPayload(BaseModel):
    nombre: int = Field(..., ge=1, le=50)

class ModifierParametresPayload(BaseModel):
    nom_bibliotheque: Optional[str] = None
    adresse: Optional[str] = None
    telephone: Optional[str] = None
    horaires: Optional[str] = None
    email_contact: Optional[str] = None
    site_web: Optional[str] = None
    logo: Optional[str] = None
    duree_emprunt_jours: Optional[str] = None
    max_emprunts_par_membre: Optional[str] = None
    max_reservations_par_membre: Optional[str] = None
    penalite_par_jour: Optional[str] = None
    penalite_maximum: Optional[str] = None
    delai_retrait_heures: Optional[str] = None
    regles: Optional[str] = None

class ModifierUtilisateurPayload(BaseModel):
    nom: Optional[str] = None
    email: Optional[str] = None
    mot_de_passe: Optional[str] = None
    photo_profil: Optional[str] = None

class MarquerToutesLuesPayload(BaseModel):
    utilisateur_id: int

class DiffuserNotificationPayload(BaseModel):
    titre: str
    message: str
    type_notif: str = "info"


# ══════════════════════════════════════════════════════════════════════════════
#  LIFESPAN + SCHEDULER
# ══════════════════════════════════════════════════════════════════════════════

scheduler = None

@asynccontextmanager
async def lifespan(app):
    global scheduler
    SQLModel.metadata.create_all(engine)

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from seed import seed
    seed()

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from .crud import (
            verifier_retards_et_notifier, verifier_echeances_proches,
            verifier_reservations_expirees, annuler_emprunts_expires
        )

        scheduler = BackgroundScheduler()
        # Annuler les emprunts en ligne non récupérés — toutes les heures
        scheduler.add_job(annuler_emprunts_expires, "interval", hours=1, id="emprunts_expires")
        # Vérifier les réservations expirées — toutes les heures
        scheduler.add_job(verifier_reservations_expirees, "interval", hours=1, id="reservations_expirees")
        # Vérifier les retards — tous les jours à 8h
        scheduler.add_job(verifier_retards_et_notifier, "cron", hour=8, minute=0, id="verifier_retards")
        # Rappeler les échéances proches — tous les jours à 9h
        scheduler.add_job(verifier_echeances_proches, "cron", hour=9, minute=0, id="echeances_proches")
        scheduler.start()
    except ImportError:
        print("APScheduler non installé — tâches planifiées désactivées")

    yield

    if scheduler:
        scheduler.shutdown()


# ══════════════════════════════════════════════════════════════════════════════
#  APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="BiblioTech — API",
    description="""
## API de gestion de bibliothèque universitaire

### Comptes de démonstration
| Rôle | Email | Mot de passe |
|------|-------|--------------|
| **Admin** | `admin@esgis.com` | `admin123` |
| **Étudiant** | `yaovi@esgis.com` | `pass123` |
| **Enseignant** | `bruce@esgis.com` | `pass123` |

### Codes d'accès inscription
`ESGIS00001` · `ESGIS00002` · `ESGIS00003` · `ESGIS00004` · `ESGIS00005`
    """,
    version="3.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Général ───────────────────────────────────────────────────────────────────

@app.get("/sante", tags=["Général"], summary="Vérifier que l'API fonctionne")
def sante():
    return {"statut": "ok", "message": "BiblioTech API opérationnelle"}

@app.get("/stats", tags=["Général"], summary="Statistiques générales")
def api_statistiques():
    return obtenir_statistiques()

@app.get("/info-bibliotheque", tags=["Général"], summary="Informations publiques de la bibliothèque")
def api_info_bibliotheque():
    parametres = obtenir_tous_parametres()
    return {
        "nom": parametres.get("nom_bibliotheque", ""),
        "adresse": parametres.get("adresse", ""),
        "telephone": parametres.get("telephone", ""),
        "horaires": parametres.get("horaires", ""),
        "email_contact": parametres.get("email_contact", ""),
        "site_web": parametres.get("site_web", ""),
        "logo": parametres.get("logo", ""),
        "regles": parametres.get("regles", ""),
        "duree_emprunt_jours": int(parametres.get("duree_emprunt_jours", "14")),
        "max_emprunts_par_membre": int(parametres.get("max_emprunts_par_membre", "3")),
        "max_reservations_par_membre": int(parametres.get("max_reservations_par_membre", "3")),
        "penalite_par_jour": float(parametres.get("penalite_par_jour", "500")),
        "penalite_maximum": float(parametres.get("penalite_maximum", "10000")),
        "delai_retrait_heures": int(parametres.get("delai_retrait_heures", "48")),
    }


# ── Authentification ──────────────────────────────────────────────────────────

@app.post("/auth/connexion", tags=["Authentification"], summary="Se connecter")
def api_connexion(payload: ConnexionPayload):
    utilisateur = authentifier_utilisateur(payload.email, payload.mot_de_passe)
    if not utilisateur:
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    return {
        "id": utilisateur.id,
        "role": utilisateur.role,
        "nom": utilisateur.nom,
        "email": utilisateur.email,
        "photo_profil": utilisateur.photo_profil,
        "type_utilisateur": utilisateur.type_utilisateur,
        "suspendu": utilisateur.suspendu,
    }

@app.post("/auth/inscription", tags=["Authentification"], summary="Créer un compte membre")
def api_inscription(payload: InscriptionPayload):
    if obtenir_utilisateur_par_email(payload.email):
        raise HTTPException(status_code=409, detail="Cet email est déjà utilisé")
    if not verifier_et_consommer_code(payload.code_acces.upper(), payload.email):
        raise HTTPException(status_code=403, detail="Code d'accès invalide ou déjà utilisé")
    u = Utilisateur(
        nom=payload.nom,
        email=payload.email,
        mot_de_passe=payload.mot_de_passe,
        role="membre",
        type_utilisateur=payload.type_utilisateur
    )
    u = creer_utilisateur(u)
    return {"id": u.id, "role": u.role, "nom": u.nom, "email": u.email}


# ── Livres ────────────────────────────────────────────────────────────────────

@app.get("/livres", tags=["Livres"], summary="Lister tous les livres")
def api_lister_livres():
    return [{
        "id": l.id, "titre": l.titre, "auteur": l.auteur, "isbn": l.isbn,
        "annee_publication": l.annee_publication, "genre": l.genre, "note": l.note,
        "description": l.description, "couverture": l.couverture,
        "total_exemplaires": l.total_exemplaires,
        "exemplaires_disponibles": l.exemplaires_disponibles,
    } for l in lister_livres()]

@app.get("/livres/{livre_id}", tags=["Livres"], summary="Obtenir un livre par son ID")
def api_obtenir_livre(livre_id: int):
    l = obtenir_livre(livre_id)
    if not l:
        raise HTTPException(status_code=404, detail=f"Aucun livre avec l'ID {livre_id}")
    return l

@app.post("/livres", tags=["Livres"], summary="Ajouter un livre")
def api_creer_livre(payload: CreerLivrePayload):
    livre = Livre(
        titre=payload.titre, auteur=payload.auteur, isbn=payload.isbn,
        annee_publication=payload.annee_publication,
        total_exemplaires=payload.total_exemplaires,
        exemplaires_disponibles=payload.total_exemplaires,
        couverture=payload.couverture, genre=payload.genre,
        note=payload.note, description=payload.description
    )
    return creer_livre(livre)

@app.put("/livres/{livre_id}", tags=["Livres"], summary="Modifier un livre")
def api_modifier_livre(livre_id: int, payload: ModifierLivrePayload):
    l = modifier_livre(livre_id, payload.dict(exclude_none=True))
    if not l:
        raise HTTPException(status_code=404, detail=f"Aucun livre avec l'ID {livre_id}")
    return l

@app.delete("/livres/{livre_id}", tags=["Livres"], summary="Supprimer un livre")
def api_supprimer_livre(livre_id: int):
    try:
        ok = supprimer_livre(livre_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Aucun livre avec l'ID {livre_id}")
        return {"ok": True, "message": "Livre supprimé avec succès"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/livres/{livre_id}/exemplaires", tags=["Livres"], summary="Ajouter des exemplaires")
def api_ajouter_exemplaires(livre_id: int, payload: AjouterExemplairesPayload):
    l = ajouter_exemplaires(livre_id, payload.nombre)
    if not l:
        raise HTTPException(status_code=404, detail=f"Aucun livre avec l'ID {livre_id}")
    return l


# ── Utilisateurs ──────────────────────────────────────────────────────────────

@app.get("/utilisateurs", tags=["Utilisateurs"], summary="Lister tous les membres")
def api_lister_utilisateurs():
    return [{
        "id": u.id, "nom": u.nom, "email": u.email,
        "role": u.role, "type_utilisateur": u.type_utilisateur,
        "suspendu": u.suspendu,
        "date_inscription": u.date_inscription.isoformat() if u.date_inscription else None,
    } for u in lister_utilisateurs()]

@app.put("/utilisateurs/{utilisateur_id}", tags=["Utilisateurs"], summary="Modifier un utilisateur")
def api_modifier_utilisateur(utilisateur_id: int, payload: ModifierUtilisateurPayload):
    u = modifier_utilisateur(utilisateur_id, payload.dict(exclude_none=True))
    if not u:
        raise HTTPException(status_code=404, detail=f"Aucun utilisateur avec l'ID {utilisateur_id}")
    return {"id": u.id, "nom": u.nom, "email": u.email, "role": u.role, "photo_profil": u.photo_profil}

@app.delete("/utilisateurs/{utilisateur_id}", tags=["Utilisateurs"], summary="Supprimer un utilisateur")
def api_supprimer_utilisateur(utilisateur_id: int):
    try:
        ok = supprimer_utilisateur(utilisateur_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Aucun utilisateur avec l'ID {utilisateur_id}")
        return {"ok": True, "message": "Utilisateur supprimé avec succès"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Emprunts ──────────────────────────────────────────────────────────────────

@app.get("/emprunts", tags=["Emprunts"], summary="Lister tous les emprunts")
def api_lister_emprunts(
    date_debut: Optional[str] = Query(None, description="Date début YYYY-MM-DD"),
    date_fin: Optional[str] = Query(None, description="Date fin YYYY-MM-DD"),
):
    debut = None
    fin = None
    try:
        if date_debut:
            debut = datetime.datetime.fromisoformat(date_debut)
        if date_fin:
            fin = datetime.datetime.fromisoformat(date_fin) + datetime.timedelta(days=1)
    except Exception:
        pass
    return lister_emprunts(date_debut=debut, date_fin=fin)

@app.post("/emprunts", tags=["Emprunts"], summary="Créer un emprunt")
def api_creer_emprunt(payload: CreerEmpruntPayload):
    try:
        date_emprunt = (
            datetime.datetime.fromisoformat(payload.date_emprunt.replace("Z", "+00:00")).replace(tzinfo=None)
            if payload.date_emprunt else datetime.datetime.utcnow()
        )
    except Exception:
        date_emprunt = datetime.datetime.utcnow()

    if payload.date_retour_prevu:
        try:
            date_retour = datetime.date.fromisoformat(payload.date_retour_prevu[:10])
        except Exception:
            date_retour = None
    else:
        jours = int(obtenir_parametre("duree_emprunt_jours", "14"))
        date_retour = datetime.date.today() + datetime.timedelta(days=jours)

    emprunt = Emprunt(
        utilisateur_id=payload.utilisateur_id,
        livre_id=payload.livre_id,
        date_emprunt=date_emprunt,
        date_retour_prevu=date_retour,
        retourne=False
    )
    try:
        return creer_emprunt(emprunt, en_ligne=payload.en_ligne)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/emprunts/{emprunt_id}/retourner", tags=["Emprunts"], summary="Enregistrer le retour d'un livre")
def api_retourner_emprunt(emprunt_id: int):
    e = marquer_retourne(emprunt_id)
    if not e:
        raise HTTPException(status_code=404, detail=f"Aucun emprunt avec l'ID {emprunt_id}")
    return {"ok": True, "message": "Retour enregistré avec succès"}

@app.put("/emprunts/{emprunt_id}/confirmer-retrait", tags=["Emprunts"], summary="Confirmer la récupération physique du livre")
def api_confirmer_retrait(emprunt_id: int):
    """Confirmer que l'adhérent est venu physiquement récupérer le livre (emprunt en ligne)."""
    e = confirmer_retrait_emprunt(emprunt_id)
    if not e:
        raise HTTPException(status_code=404, detail=f"Aucun emprunt avec l'ID {emprunt_id}")
    return {"ok": True, "message": "Récupération confirmée"}


# ── Réservations ──────────────────────────────────────────────────────────────

@app.get("/reservations", tags=["Réservations"], summary="Lister toutes les réservations")
def api_lister_reservations():
    return lister_reservations()

@app.post("/reservations", tags=["Réservations"], summary="Créer une réservation")
def api_creer_reservation(payload: CreerReservationPayload):
    resa = Reservation(utilisateur_id=payload.utilisateur_id, livre_id=payload.livre_id)
    try:
        return creer_reservation(resa)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/reservations/{reservation_id}/statut", tags=["Réservations"], summary="Changer le statut")
def api_modifier_statut(reservation_id: int, payload: ModifierStatutReservationPayload):
    if payload.statut not in ("attente", "pret", "annule", "expire"):
        raise HTTPException(status_code=400, detail="Statut invalide")
    r = modifier_statut_reservation(reservation_id, payload.statut)
    if not r:
        raise HTTPException(status_code=404, detail=f"Aucune réservation avec l'ID {reservation_id}")
    return r


# ── Pénalités ─────────────────────────────────────────────────────────────────

@app.get("/penalites", tags=["Pénalités"], summary="Lister toutes les pénalités")
def api_lister_penalites(utilisateur_id: Optional[int] = None):
    return lister_penalites(utilisateur_id=utilisateur_id)

@app.put("/penalites/{penalite_id}/payer", tags=["Pénalités"], summary="Marquer une pénalité payée")
def api_payer_penalite(penalite_id: int):
    p = payer_penalite(penalite_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"Aucune pénalité avec l'ID {penalite_id}")
    return p


# ── Notifications ─────────────────────────────────────────────────────────────

@app.get("/notifications", tags=["Notifications"], summary="Notifications d'un utilisateur")
def api_lister_notifications(utilisateur_id: int):
    return lister_notifications(utilisateur_id)

@app.get("/notifications/non-lues", tags=["Notifications"], summary="Nombre de notifications non lues")
def api_compter_non_lues(utilisateur_id: int):
    return {"utilisateur_id": utilisateur_id, "total": compter_non_lues(utilisateur_id)}

@app.put("/notifications/{notification_id}/lire", tags=["Notifications"], summary="Marquer une notification lue")
def api_marquer_lue(notification_id: int):
    n = marquer_lue(notification_id)
    if not n:
        raise HTTPException(status_code=404, detail=f"Aucune notification avec l'ID {notification_id}")
    return n

@app.put("/notifications/tout-lire", tags=["Notifications"], summary="Marquer toutes les notifications lues")
def api_tout_marquer_lues(payload: MarquerToutesLuesPayload):
    tout_marquer_lues(payload.utilisateur_id)
    return {"ok": True}


# ── Administration ────────────────────────────────────────────────────────────

@app.post("/admin/codes-acces/generer", tags=["Administration"], summary="Générer des codes d'accès")
def api_generer_codes(payload: GenererCodesPayload):
    codes = generer_codes_acces(payload.nombre)
    return {"codes": codes, "total": len(codes)}

@app.get("/admin/codes-acces", tags=["Administration"], summary="Lister les codes d'accès")
def api_lister_codes():
    return lister_codes_acces()

@app.get("/admin/parametres", tags=["Administration"], summary="Voir les paramètres")
def api_obtenir_parametres():
    return obtenir_tous_parametres()

@app.post("/admin/parametres", tags=["Administration"], summary="Modifier les paramètres")
def api_modifier_parametres(payload: ModifierParametresPayload):
    donnees = payload.dict(exclude_none=True)
    for cle, valeur in donnees.items():
        definir_parametre(cle, str(valeur))
    return {"ok": True, "message": "Paramètres mis à jour", "modifies": list(donnees.keys())}

@app.post("/admin/notifications/diffuser", tags=["Administration"], summary="Envoyer une notification à tous les membres")
def api_diffuser_notification(payload: DiffuserNotificationPayload):
    total = diffuser_notification_admin(payload.titre, payload.message, payload.type_notif)
    return {"ok": True, "message": f"Notification envoyée à {total} membre(s)"}

@app.post("/admin/scheduler/verifier-retards", tags=["Administration"], summary="Déclencher manuellement les vérifications")
def api_verifier_retards():
    from .crud import (
        verifier_retards_et_notifier, verifier_echeances_proches,
        verifier_reservations_expirees, annuler_emprunts_expires
    )
    annuler_emprunts_expires()
    verifier_retards_et_notifier()
    verifier_echeances_proches()
    verifier_reservations_expirees()
    return {"ok": True, "message": "Vérification effectuée"}

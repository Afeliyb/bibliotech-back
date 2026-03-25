import secrets
import string
import datetime
from sqlmodel import Session, select
from .models import (
    Livre, Utilisateur, Emprunt, Reservation,
    Penalite, Notification, CodeAcces, Parametre
)
from .database import engine
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


# ─── Utilitaires mot de passe ─────────────────────────────────────────────────

def hacher_mot_de_passe(mot_de_passe: str) -> str:
    return pwd_context.hash(mot_de_passe)

def verifier_mot_de_passe(plain: str, hache: str) -> bool:
    return pwd_context.verify(plain, hache)


# ─── Paramètres ───────────────────────────────────────────────────────────────

def obtenir_parametre(cle: str, defaut: str = "") -> str:
    with Session(engine) as session:
        p = session.exec(select(Parametre).where(Parametre.cle == cle)).first()
        return p.valeur if p else defaut

def definir_parametre(cle: str, valeur: str):
    with Session(engine) as session:
        p = session.exec(select(Parametre).where(Parametre.cle == cle)).first()
        if p:
            p.valeur = valeur
            session.add(p)
        else:
            session.add(Parametre(cle=cle, valeur=valeur))
        session.commit()

def obtenir_tous_parametres() -> dict:
    defauts = {
        "nom_bibliotheque": "BiblioTech",
        "adresse": "", "telephone": "", "horaires": "",
        "email_contact": "", "site_web": "", "logo": "",
        "duree_emprunt_jours": "14",
        "max_emprunts_par_membre": "3",
        "max_reservations_par_membre": "3",
        "penalite_par_jour": "500",
        "penalite_maximum": "10000",
        "delai_retrait_heures": "48",
        "regles": "",
    }
    with Session(engine) as session:
        stockes = session.exec(select(Parametre)).all()
        result = dict(defauts)
        for p in stockes:
            result[p.cle] = p.valeur
        return result


# ─── Utilitaire interne : convertir la 1ère réservation en attente → emprunt ──

def _convertir_reservation_en_emprunt(session: Session, livre: Livre):
    """
    Quand un exemplaire devient disponible, cherche la première réservation
    en attente pour ce livre et la convertit automatiquement en emprunt
    (en_attente_retrait=True, délai 24h). Notifie le membre concerné.
    Décrémente exemplaires_disponibles.
    Retourne True si une conversion a eu lieu.
    """
    resa = session.exec(
        select(Reservation).where(
            Reservation.livre_id == livre.id,
            Reservation.statut == "attente"
        ).order_by(Reservation.date_creation)
    ).first()

    if not resa:
        return False

    jours = int(obtenir_parametre("duree_emprunt_jours", "14"))
    date_retour = datetime.date.today() + datetime.timedelta(days=jours)
    now = datetime.datetime.utcnow()

    emprunt = Emprunt(
        utilisateur_id=resa.utilisateur_id,
        livre_id=livre.id,
        date_emprunt=now,
        date_retour_prevu=date_retour,
        retourne=False,
        en_attente_retrait=True,
        date_limite_retrait=now + datetime.timedelta(hours=24),
        annule=False,
    )
    session.add(emprunt)

    # Marquer la réservation comme convertie (on réutilise "annule" avec le sens "traitée")
    resa.statut = "annule"
    session.add(resa)

    # Décrémenter les exemplaires disponibles
    livre.exemplaires_disponibles = max(livre.exemplaires_disponibles - 1, 0)
    session.add(livre)

    session.flush()  # pour avoir l'id de l'emprunt

    utilisateur = session.get(Utilisateur, resa.utilisateur_id)
    nom = utilisateur.nom if utilisateur else f"Utilisateur #{resa.utilisateur_id}"
    limite_str = emprunt.date_limite_retrait.strftime('%d/%m/%Y à %Hh%M')

    session.add(Notification(
        utilisateur_id=resa.utilisateur_id,
        titre="📖 Votre réservation est prête — Emprunt activé !",
        message=(
            f"Bonjour {nom}, bonne nouvelle ! Un exemplaire de « {livre.titre} » vient de se libérer. "
            f"Votre réservation a été automatiquement convertie en emprunt. "
            f"Le compte à rebours de 24h est lancé : vous devez vous présenter à la bibliothèque "
            f"avant le {limite_str} pour récupérer votre livre. "
            f"Passé ce délai, l'emprunt sera automatiquement annulé."
        ),
        type="emprunt"
    ))

    return True


# ─── Livres ───────────────────────────────────────────────────────────────────

def creer_livre(livre: Livre) -> Livre:
    with Session(engine) as session:
        if not livre.exemplaires_disponibles or livre.exemplaires_disponibles <= 0:
            livre.exemplaires_disponibles = livre.total_exemplaires or 1
        session.add(livre)
        session.commit()
        session.refresh(livre)
        utilisateurs = session.exec(select(Utilisateur)).all()
        for u in utilisateurs:
            session.add(Notification(
                utilisateur_id=u.id,
                titre="📚 Nouveau livre disponible",
                message=f"Un nouveau livre vient d'être ajouté au catalogue : « {livre.titre} »"
                        + (f" par {livre.auteur}" if livre.auteur else ""),
                type="info"
            ))
        session.commit()
        return livre

def lister_livres():
    with Session(engine) as session:
        return session.exec(select(Livre)).all()

def obtenir_livre(livre_id: int):
    with Session(engine) as session:
        return session.get(Livre, livre_id)

def modifier_livre(livre_id: int, donnees: dict):
    with Session(engine) as session:
        livre = session.get(Livre, livre_id)
        if not livre:
            return None
        for k, v in donnees.items():
            if hasattr(livre, k) and k != "id":
                setattr(livre, k, v)
        session.add(livre)
        session.commit()
        session.refresh(livre)
        return livre

def ajouter_exemplaires(livre_id: int, nombre: int):
    """
    Ajoute des exemplaires. Pour chaque exemplaire ajouté, tente de convertir
    une réservation en attente en emprunt automatique (FIFO).
    """
    with Session(engine) as session:
        livre = session.get(Livre, livre_id)
        if not livre:
            return None
        livre.total_exemplaires += nombre
        livre.exemplaires_disponibles += nombre
        session.add(livre)
        session.commit()
        session.refresh(livre)

        # Pour chaque nouvel exemplaire, convertir une réservation si elle existe
        conversions = 0
        for _ in range(nombre):
            livre_recharge = session.get(Livre, livre_id)
            if livre_recharge and livre_recharge.exemplaires_disponibles > 0:
                if _convertir_reservation_en_emprunt(session, livre_recharge):
                    conversions += 1
                    session.commit()
                else:
                    break
            else:
                break

        return session.get(Livre, livre_id)

def supprimer_livre(livre_id: int) -> bool:
    with Session(engine) as session:
        livre = session.get(Livre, livre_id)
        if not livre:
            return False
        emprunts_actifs = session.exec(
            select(Emprunt).where(Emprunt.livre_id == livre_id, Emprunt.retourne == False, Emprunt.annule == False)
        ).first()
        if emprunts_actifs:
            raise ValueError("Impossible de supprimer un livre avec des emprunts actifs")
        session.delete(livre)
        session.commit()
        return True


# ─── Utilisateurs ─────────────────────────────────────────────────────────────

def creer_utilisateur(utilisateur: Utilisateur) -> Utilisateur:
    with Session(engine) as session:
        try:
            utilisateur.mot_de_passe = hacher_mot_de_passe(utilisateur.mot_de_passe)
        except Exception:
            pass
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)
        return utilisateur

def obtenir_utilisateur_par_email(email: str):
    with Session(engine) as session:
        return session.exec(select(Utilisateur).where(Utilisateur.email == email)).first()

def obtenir_utilisateur_par_id(utilisateur_id: int):
    with Session(engine) as session:
        return session.get(Utilisateur, utilisateur_id)

def authentifier_utilisateur(email: str, mot_de_passe: str):
    utilisateur = obtenir_utilisateur_par_email(email)
    if not utilisateur:
        return None
    try:
        if not verifier_mot_de_passe(mot_de_passe, utilisateur.mot_de_passe):
            return None
    except Exception:
        if utilisateur.mot_de_passe != mot_de_passe:
            return None
    return utilisateur

def lister_utilisateurs():
    with Session(engine) as session:
        return session.exec(select(Utilisateur)).all()

def modifier_utilisateur(utilisateur_id: int, donnees: dict):
    with Session(engine) as session:
        utilisateur = session.get(Utilisateur, utilisateur_id)
        if not utilisateur:
            return None
        for k, v in donnees.items():
            if k == "mot_de_passe" and v:
                utilisateur.mot_de_passe = hacher_mot_de_passe(v)
            elif hasattr(utilisateur, k) and k not in ("id", "mot_de_passe"):
                setattr(utilisateur, k, v)
        session.add(utilisateur)
        session.commit()
        session.refresh(utilisateur)
        return utilisateur

def supprimer_utilisateur(utilisateur_id: int) -> bool:
    with Session(engine) as session:
        utilisateur = session.get(Utilisateur, utilisateur_id)
        if not utilisateur:
            return False
        if utilisateur.role == "admin":
            raise ValueError("Impossible de supprimer un compte administrateur")
        emprunts_actifs = session.exec(
            select(Emprunt).where(
                Emprunt.utilisateur_id == utilisateur_id,
                Emprunt.retourne == False,
                Emprunt.annule == False,
            )
        ).first()
        if emprunts_actifs:
            raise ValueError("Impossible de supprimer un membre avec des emprunts en cours")
        session.delete(utilisateur)
        session.commit()
        return True


# ─── Emprunts ─────────────────────────────────────────────────────────────────

def creer_emprunt(emprunt: Emprunt, en_ligne: bool = False) -> Emprunt:
    with Session(engine) as session:
        livre = session.get(Livre, emprunt.livre_id)
        if not livre:
            raise ValueError("Livre introuvable")
        if livre.exemplaires_disponibles <= 0:
            raise ValueError("Aucun exemplaire disponible pour ce livre")

        max_emprunts = int(obtenir_parametre("max_emprunts_par_membre", "3"))
        nb_actifs = len(session.exec(
            select(Emprunt).where(
                Emprunt.utilisateur_id == emprunt.utilisateur_id,
                Emprunt.retourne == False,
                Emprunt.annule == False,
            )
        ).all())
        if nb_actifs >= max_emprunts:
            raise ValueError(f"Limite atteinte : vous ne pouvez pas avoir plus de {max_emprunts} emprunt(s) simultané(s)")

        deja_emprunte = session.exec(
            select(Emprunt).where(
                Emprunt.utilisateur_id == emprunt.utilisateur_id,
                Emprunt.livre_id == emprunt.livre_id,
                Emprunt.retourne == False,
                Emprunt.annule == False,
            )
        ).first()
        if deja_emprunte:
            raise ValueError(f"Vous avez déjà un exemplaire de « {livre.titre} » en cours d'emprunt")

        # Annuler la réservation "attente" si elle existe (l'utilisateur emprunte directement)
        resa = session.exec(
            select(Reservation).where(
                Reservation.utilisateur_id == emprunt.utilisateur_id,
                Reservation.livre_id == emprunt.livre_id,
                Reservation.statut.in_(["attente", "pret"])
            )
        ).first()
        if resa:
            resa.statut = "annule"
            session.add(resa)

        livre.exemplaires_disponibles -= 1
        session.add(livre)

        if en_ligne:
            emprunt.en_attente_retrait = True
            emprunt.date_limite_retrait = datetime.datetime.utcnow() + datetime.timedelta(hours=24)

        session.add(emprunt)
        session.commit()
        session.refresh(emprunt)

        utilisateur = session.get(Utilisateur, emprunt.utilisateur_id)
        nom_utilisateur = utilisateur.nom if utilisateur else f"Utilisateur #{emprunt.utilisateur_id}"

        try:
            if en_ligne:
                limite_str = emprunt.date_limite_retrait.strftime('%d/%m/%Y à %Hh%M')
                msg = (
                    f"Bonjour {nom_utilisateur}, votre demande d'emprunt pour « {livre.titre} » a été enregistrée. "
                    f"Vous devez vous présenter à la bibliothèque avant le {limite_str} pour récupérer votre livre. "
                    f"Passé ce délai de 24h, votre emprunt sera automatiquement annulé."
                )
                titre_notif = "📖 Emprunt en attente de récupération"
            else:
                msg = (
                    f"Bonjour {nom_utilisateur}, votre emprunt de « {livre.titre} » a été confirmé. "
                    f"Date de retour prévue : {emprunt.date_retour_prevu}. "
                    f"Merci de respecter ce délai afin d'éviter toute pénalité."
                )
                titre_notif = "✅ Emprunt confirmé"

            session.add(Notification(utilisateur_id=emprunt.utilisateur_id, titre=titre_notif, message=msg, type="emprunt"))
            session.commit()
        except Exception:
            pass
        return emprunt

def confirmer_retrait_emprunt(emprunt_id: int):
    """Admin confirme que l'adhérent est venu récupérer physiquement le livre."""
    with Session(engine) as session:
        e = session.get(Emprunt, emprunt_id)
        if not e:
            return None
        e.en_attente_retrait = False
        e.date_limite_retrait = None
        session.add(e)
        session.commit()
        session.refresh(e)
        utilisateur = session.get(Utilisateur, e.utilisateur_id)
        livre = session.get(Livre, e.livre_id)
        nom = utilisateur.nom if utilisateur else f"Utilisateur #{e.utilisateur_id}"
        titre_livre = livre.titre if livre else "votre livre"
        try:
            session.add(Notification(
                utilisateur_id=e.utilisateur_id,
                titre="✅ Emprunt confirmé — Livre récupéré",
                message=(
                    f"Bonjour {nom}, la récupération de « {titre_livre} » a été confirmée. "
                    f"Date de retour prévue : {e.date_retour_prevu}. Bonne lecture !"
                ),
                type="emprunt"
            ))
            session.commit()
        except Exception:
            pass
        return e

def lister_emprunts(date_debut=None, date_fin=None):
    with Session(engine) as session:
        stmt = select(Emprunt)
        if date_debut:
            stmt = stmt.where(Emprunt.date_emprunt >= date_debut)
        if date_fin:
            stmt = stmt.where(Emprunt.date_emprunt <= date_fin)
        results = session.exec(stmt).all()
        enrichis = []
        today = datetime.date.today()
        for e in results:
            livre = session.get(Livre, e.livre_id)
            utilisateur = session.get(Utilisateur, e.utilisateur_id)
            if e.annule:
                statut = "annule"
            elif e.retourne:
                statut = "retourne"
            elif e.en_attente_retrait:
                statut = "attente_retrait"
            elif e.date_retour_prevu and e.date_retour_prevu < today:
                statut = "retard"
            else:
                statut = "actif"
            enrichis.append({
                "id": e.id,
                "utilisateur_id": e.utilisateur_id,
                "nom_utilisateur": utilisateur.nom if utilisateur else f"Utilisateur #{e.utilisateur_id}",
                "email_utilisateur": utilisateur.email if utilisateur else None,
                "type_utilisateur": utilisateur.type_utilisateur if utilisateur else None,
                "livre_id": e.livre_id,
                "titre_livre": livre.titre if livre else None,
                "auteur_livre": livre.auteur if livre else None,
                "couverture_livre": livre.couverture if livre else None,
                "date_emprunt": e.date_emprunt.isoformat() if e.date_emprunt else None,
                "date_retour_prevu": e.date_retour_prevu.isoformat() if e.date_retour_prevu else None,
                "date_retour_effectif": e.date_retour_effectif.isoformat() if e.date_retour_effectif else None,
                "retourne": e.retourne,
                "annule": e.annule,
                "en_attente_retrait": e.en_attente_retrait,
                "date_limite_retrait": e.date_limite_retrait.isoformat() if e.date_limite_retrait else None,
                "statut": statut,
            })
        return enrichis

def marquer_retourne(emprunt_id: int):
    with Session(engine) as session:
        e = session.get(Emprunt, emprunt_id)
        if not e:
            return None
        e.retourne = True
        e.en_attente_retrait = False
        e.date_retour_effectif = datetime.datetime.utcnow()
        session.add(e)

        livre = session.get(Livre, e.livre_id)
        if livre:
            # Rendre l'exemplaire disponible d'abord
            livre.exemplaires_disponibles = min(livre.exemplaires_disponibles + 1, livre.total_exemplaires)
            session.add(livre)
            session.commit()

            # Tenter de convertir la 1ère réservation en attente → emprunt automatique
            livre_recharge = session.get(Livre, livre.id)
            if livre_recharge:
                _convertir_reservation_en_emprunt(session, livre_recharge)
                session.commit()

        # Notification retour + pénalité si retard
        try:
            utilisateur = session.get(Utilisateur, e.utilisateur_id)
            nom = utilisateur.nom if utilisateur else f"Utilisateur #{e.utilisateur_id}"
            livre2 = session.get(Livre, e.livre_id)
            titre_livre = livre2.titre if livre2 else "votre livre"
            penalite_par_jour = float(obtenir_parametre("penalite_par_jour", "500"))
            penalite_max = float(obtenir_parametre("penalite_maximum", "10000"))

            session.add(Notification(
                utilisateur_id=e.utilisateur_id,
                titre="📕 Retour enregistré",
                message=f"Bonjour {nom}, le retour de « {titre_livre} » a bien été enregistré. Merci !",
                type="retour"
            ))

            today = datetime.date.today()
            if e.date_retour_prevu and e.date_retour_prevu < today:
                jours = (today - e.date_retour_prevu).days
                montant = min(round(jours * penalite_par_jour, 0), penalite_max)
                session.add(Penalite(
                    utilisateur_id=e.utilisateur_id, emprunt_id=e.id,
                    montant=montant,
                    motif=f"Retard de {jours} jour(s) × {int(penalite_par_jour)} FCFA/jour",
                    payee=False
                ))
                session.add(Notification(
                    utilisateur_id=e.utilisateur_id,
                    titre="⚠️ Pénalité de retard",
                    message=(
                        f"Bonjour {nom}, une pénalité de {int(montant):,} FCFA a été appliquée "
                        f"pour {jours} jour(s) de retard sur « {titre_livre} ». "
                        f"Veuillez vous acquitter de cette pénalité auprès de la bibliothèque."
                    ).replace(",", " "),
                    type="penalite"
                ))
            session.commit()
        except Exception:
            session.rollback()

        return session.get(Emprunt, emprunt_id)


# ─── Réservations ─────────────────────────────────────────────────────────────

def creer_reservation(reservation: Reservation) -> Reservation:
    with Session(engine) as session:
        max_resa = int(obtenir_parametre("max_reservations_par_membre", "3"))
        nb_actives = len(session.exec(
            select(Reservation).where(
                Reservation.utilisateur_id == reservation.utilisateur_id,
                Reservation.statut.in_(["attente", "pret"])
            )
        ).all())
        if nb_actives >= max_resa:
            raise ValueError(f"Limite de {max_resa} réservation(s) active(s) atteinte")

        # Vérifier si l'utilisateur n'a pas déjà ce livre en cours d'emprunt ou réservation
        deja_emprunt = session.exec(
            select(Emprunt).where(
                Emprunt.utilisateur_id == reservation.utilisateur_id,
                Emprunt.livre_id == reservation.livre_id,
                Emprunt.retourne == False,
                Emprunt.annule == False,
            )
        ).first()
        if deja_emprunt:
            raise ValueError("Vous avez déjà ce livre en cours d'emprunt")

        deja_resa = session.exec(
            select(Reservation).where(
                Reservation.utilisateur_id == reservation.utilisateur_id,
                Reservation.livre_id == reservation.livre_id,
                Reservation.statut.in_(["attente", "pret"])
            )
        ).first()
        if deja_resa:
            raise ValueError("Vous avez déjà une réservation active pour ce livre")

        livre = session.get(Livre, reservation.livre_id)
        utilisateur = session.get(Utilisateur, reservation.utilisateur_id)
        nom = utilisateur.nom if utilisateur else f"Utilisateur #{reservation.utilisateur_id}"
        titre_livre = livre.titre if livre else f"livre #{reservation.livre_id}"

        # Si un exemplaire est disponible → conversion directe en emprunt
        if livre and livre.exemplaires_disponibles > 0:
            # Créer directement l'emprunt
            jours = int(obtenir_parametre("duree_emprunt_jours", "14"))
            now = datetime.datetime.utcnow()
            emprunt = Emprunt(
                utilisateur_id=reservation.utilisateur_id,
                livre_id=reservation.livre_id,
                date_emprunt=now,
                date_retour_prevu=datetime.date.today() + datetime.timedelta(days=jours),
                retourne=False,
                en_attente_retrait=True,
                date_limite_retrait=now + datetime.timedelta(hours=24),
                annule=False,
            )
            livre.exemplaires_disponibles -= 1
            session.add(livre)
            session.add(emprunt)

            # La réservation est créée comme "annule" (directement convertie)
            reservation.statut = "annule"
            session.add(reservation)
            session.commit()
            session.refresh(reservation)

            limite_str = emprunt.date_limite_retrait.strftime('%d/%m/%Y à %Hh%M')
            session.add(Notification(
                utilisateur_id=reservation.utilisateur_id,
                titre="📖 Réservation convertie en emprunt — Disponible maintenant !",
                message=(
                    f"Bonjour {nom}, un exemplaire de « {titre_livre} » est disponible immédiatement ! "
                    f"Votre réservation a été automatiquement convertie en emprunt. "
                    f"Présentez-vous à la bibliothèque avant le {limite_str} pour récupérer votre livre. "
                    f"Passé ce délai de 24h, l'emprunt sera automatiquement annulé."
                ),
                type="emprunt"
            ))
            session.commit()
            return reservation

        # Sinon → réservation en file d'attente
        reservation.statut = "attente"
        session.add(reservation)
        session.commit()
        session.refresh(reservation)

        session.add(Notification(
            utilisateur_id=reservation.utilisateur_id,
            titre="📅 Réservation enregistrée — En file d'attente",
            message=(
                f"Bonjour {nom}, votre réservation pour « {titre_livre} » a bien été enregistrée. "
                f"Vous serez automatiquement notifié(e) dès qu'un exemplaire se libère, "
                f"et votre réservation sera convertie en emprunt avec un délai de 24h pour venir récupérer le livre."
            ),
            type="reservation"
        ))
        session.commit()
        return reservation

def lister_reservations():
    with Session(engine) as session:
        reservations = session.exec(select(Reservation)).all()
        enrichies = []
        for r in reservations:
            livre = session.get(Livre, r.livre_id)
            utilisateur = session.get(Utilisateur, r.utilisateur_id)
            enrichies.append({
                "id": r.id,
                "utilisateur_id": r.utilisateur_id,
                "nom_utilisateur": utilisateur.nom if utilisateur else f"Utilisateur #{r.utilisateur_id}",
                "email_utilisateur": utilisateur.email if utilisateur else None,
                "livre_id": r.livre_id,
                "titre_livre": livre.titre if livre else f"Livre #{r.livre_id}",
                "auteur_livre": livre.auteur if livre else None,
                "couverture_livre": livre.couverture if livre else None,
                "date_creation": r.date_creation.isoformat() if r.date_creation else None,
                "statut": r.statut,
                "date_limite_retrait": r.date_limite_retrait.isoformat() if r.date_limite_retrait else None,
            })
        return enrichies

def modifier_statut_reservation(reservation_id: int, statut: str):
    with Session(engine) as session:
        r = session.get(Reservation, reservation_id)
        if not r:
            return None
        ancien_statut = r.statut
        r.statut = statut
        if statut == "pret" and not r.date_limite_retrait:
            delai_h = int(obtenir_parametre("delai_retrait_heures", "48"))
            r.date_limite_retrait = datetime.datetime.utcnow() + datetime.timedelta(hours=delai_h)
        session.add(r)
        session.commit()
        session.refresh(r)
        if statut == "pret" and ancien_statut != "pret":
            try:
                livre = session.get(Livre, r.livre_id)
                utilisateur = session.get(Utilisateur, r.utilisateur_id)
                nom = utilisateur.nom if utilisateur else f"Utilisateur #{r.utilisateur_id}"
                titre_livre = livre.titre if livre else f"Livre #{r.livre_id}"
                delai_h = int(obtenir_parametre("delai_retrait_heures", "48"))
                limite_str = r.date_limite_retrait.strftime('%d/%m/%Y à %Hh%M') if r.date_limite_retrait else "bientôt"
                session.add(Notification(
                    utilisateur_id=r.utilisateur_id,
                    titre="📗 Réservation prête à récupérer",
                    message=(
                        f"Bonjour {nom}, votre réservation pour « {titre_livre} » est disponible ! "
                        f"Vous avez {delai_h}h pour venir la récupérer, soit jusqu'au {limite_str}. "
                        f"Passé ce délai, votre réservation sera automatiquement annulée."
                    ),
                    type="reservation"
                ))
                session.commit()
            except Exception:
                pass
        return r


# ─── Pénalités ────────────────────────────────────────────────────────────────

def lister_penalites(utilisateur_id: int = None):
    with Session(engine) as session:
        stmt = select(Penalite)
        if utilisateur_id:
            stmt = stmt.where(Penalite.utilisateur_id == utilisateur_id)
        penalites = session.exec(stmt).all()
        enrichies = []
        for p in penalites:
            utilisateur = session.get(Utilisateur, p.utilisateur_id)
            emprunt = session.get(Emprunt, p.emprunt_id) if p.emprunt_id else None
            livre = session.get(Livre, emprunt.livre_id) if emprunt else None
            enrichies.append({
                "id": p.id,
                "utilisateur_id": p.utilisateur_id,
                "nom_utilisateur": utilisateur.nom if utilisateur else f"Utilisateur #{p.utilisateur_id}",
                "email_utilisateur": utilisateur.email if utilisateur else None,
                "emprunt_id": p.emprunt_id,
                "titre_livre": livre.titre if livre else None,
                "montant": p.montant,
                "motif": p.motif,
                "payee": p.payee,
                "date_creation": p.date_creation.isoformat() if p.date_creation else None,
            })
        return enrichies

def payer_penalite(penalite_id: int):
    with Session(engine) as session:
        p = session.get(Penalite, penalite_id)
        if not p:
            return None
        p.payee = True
        session.add(p)
        session.commit()
        session.refresh(p)
        utilisateur = session.get(Utilisateur, p.utilisateur_id)
        nom = utilisateur.nom if utilisateur else f"Utilisateur #{p.utilisateur_id}"
        try:
            session.add(Notification(
                utilisateur_id=p.utilisateur_id,
                titre="✅ Pénalité réglée",
                message=f"Bonjour {nom}, votre pénalité de {int(p.montant):,} FCFA a été marquée comme payée. Merci !".replace(",", " "),
                type="penalite"
            ))
            session.commit()
        except Exception:
            pass
        return p


# ─── Notifications ────────────────────────────────────────────────────────────

def lister_notifications(utilisateur_id: int):
    with Session(engine) as session:
        stmt = select(Notification).where(Notification.utilisateur_id == utilisateur_id)
        return session.exec(stmt.order_by(Notification.date_creation.desc())).all()

def compter_non_lues(utilisateur_id: int) -> int:
    with Session(engine) as session:
        return len(session.exec(
            select(Notification).where(
                Notification.utilisateur_id == utilisateur_id,
                Notification.lue == False
            )
        ).all())

def marquer_lue(notification_id: int):
    with Session(engine) as session:
        n = session.get(Notification, notification_id)
        if not n:
            return None
        n.lue = True
        session.add(n)
        session.commit()
        session.refresh(n)
        return n

def tout_marquer_lues(utilisateur_id: int):
    with Session(engine) as session:
        notes = session.exec(
            select(Notification).where(
                Notification.utilisateur_id == utilisateur_id,
                Notification.lue == False
            )
        ).all()
        for n in notes:
            n.lue = True
            session.add(n)
        session.commit()


# ─── Codes d'accès ────────────────────────────────────────────────────────────

def generer_codes_acces(nombre: int = 1):
    codes = []
    with Session(engine) as session:
        for _ in range(nombre):
            code = "ESGIS" + "".join(secrets.choice(string.digits) for _ in range(5))
            while session.exec(select(CodeAcces).where(CodeAcces.code == code)).first():
                code = "ESGIS" + "".join(secrets.choice(string.digits) for _ in range(5))
            session.add(CodeAcces(code=code))
            codes.append(code)
        session.commit()
    return codes

def verifier_et_consommer_code(code: str, email: str) -> bool:
    with Session(engine) as session:
        ca = session.exec(
            select(CodeAcces).where(CodeAcces.code == code, CodeAcces.utilise == False)
        ).first()
        if not ca:
            return False
        ca.utilise = True
        ca.utilise_par = email
        session.add(ca)
        session.commit()
        return True

def lister_codes_acces():
    with Session(engine) as session:
        return session.exec(select(CodeAcces)).all()


# ─── Statistiques ─────────────────────────────────────────────────────────────

def obtenir_statistiques():
    today = datetime.date.today()
    with Session(engine) as session:
        total_livres = len(session.exec(select(Livre)).all())
        total_membres = len(session.exec(select(Utilisateur).where(Utilisateur.role == "membre")).all())
        emprunts = session.exec(select(Emprunt)).all()
        actifs = sum(1 for e in emprunts if not e.retourne and not e.annule)
        retards = sum(1 for e in emprunts if not e.retourne and not e.annule and not e.en_attente_retrait and e.date_retour_prevu and e.date_retour_prevu < today)
        penalites_impayees = len(session.exec(select(Penalite).where(Penalite.payee == False)).all())
        reservations_attente = len(session.exec(
            select(Reservation).where(Reservation.statut == "attente")
        ).all())
        return {
            "total_livres": total_livres,
            "total_membres": total_membres,
            "emprunts_actifs": actifs,
            "retards": retards,
            "penalites_impayees": penalites_impayees,
            "reservations_en_attente": reservations_attente,
        }


# ─── Tâches planifiées ────────────────────────────────────────────────────────

def annuler_emprunts_expires():
    """Annuler automatiquement les emprunts en ligne dont le délai 24h est dépassé."""
    now = datetime.datetime.utcnow()
    with Session(engine) as session:
        emprunts_expires = session.exec(
            select(Emprunt).where(
                Emprunt.en_attente_retrait == True,
                Emprunt.annule == False,
                Emprunt.retourne == False,
            )
        ).all()
        for e in emprunts_expires:
            if not e.date_limite_retrait or e.date_limite_retrait > now:
                continue
            e.annule = True
            e.en_attente_retrait = False
            session.add(e)
            livre = session.get(Livre, e.livre_id)
            if livre:
                livre.exemplaires_disponibles = min(livre.exemplaires_disponibles + 1, livre.total_exemplaires)
                session.add(livre)
            utilisateur = session.get(Utilisateur, e.utilisateur_id)
            nom = utilisateur.nom if utilisateur else f"Utilisateur #{e.utilisateur_id}"
            titre_livre = livre.titre if livre else f"Livre #{e.livre_id}"
            session.add(Notification(
                utilisateur_id=e.utilisateur_id,
                titre="❌ Emprunt annulé — délai dépassé",
                message=(
                    f"Bonjour {nom}, votre emprunt de « {titre_livre} » a été automatiquement annulé "
                    f"car vous ne vous êtes pas présenté(e) à la bibliothèque dans le délai de 24h. "
                    f"Vous pouvez effectuer une nouvelle demande si vous le souhaitez."
                ),
                type="avertissement"
            ))
            session.commit()

            # Après annulation, tenter de servir la prochaine réservation
            livre_recharge = session.get(Livre, e.livre_id)
            if livre_recharge:
                _convertir_reservation_en_emprunt(session, livre_recharge)
                session.commit()

def verifier_retards_et_notifier():
    today = datetime.date.today()
    with Session(engine) as session:
        emprunts_retard = session.exec(
            select(Emprunt).where(
                Emprunt.retourne == False,
                Emprunt.annule == False,
                Emprunt.en_attente_retrait == False,
                Emprunt.date_retour_prevu != None
            )
        ).all()
        for e in emprunts_retard:
            if not e.date_retour_prevu or e.date_retour_prevu >= today:
                continue
            jours_retard = (today - e.date_retour_prevu).days
            penalite_par_jour = float(obtenir_parametre("penalite_par_jour", "500"))
            penalite_max = float(obtenir_parametre("penalite_maximum", "10000"))
            montant_estime = min(jours_retard * penalite_par_jour, penalite_max)
            utilisateur = session.get(Utilisateur, e.utilisateur_id)
            livre = session.get(Livre, e.livre_id)
            if not utilisateur:
                continue
            session.add(Notification(
                utilisateur_id=e.utilisateur_id,
                titre="🚨 Retard de retour — Action requise",
                message=(
                    f"Bonjour {utilisateur.nom}, votre emprunt de « {livre.titre if livre else 'votre livre'} » "
                    f"est en retard de {jours_retard} jour(s). "
                    f"Pénalité en cours : {int(montant_estime):,} FCFA. "
                    f"Veuillez retourner ce livre dès que possible."
                ).replace(",", " "),
                type="avertissement"
            ))
        session.commit()

def verifier_echeances_proches():
    today = datetime.date.today()
    dans_3_jours = today + datetime.timedelta(days=3)
    with Session(engine) as session:
        emprunts_bientot = session.exec(
            select(Emprunt).where(
                Emprunt.retourne == False,
                Emprunt.annule == False,
                Emprunt.en_attente_retrait == False,
                Emprunt.date_retour_prevu == dans_3_jours
            )
        ).all()
        for e in emprunts_bientot:
            utilisateur = session.get(Utilisateur, e.utilisateur_id)
            livre = session.get(Livre, e.livre_id)
            if not utilisateur:
                continue
            session.add(Notification(
                utilisateur_id=e.utilisateur_id,
                titre="📅 Rappel de retour dans 3 jours",
                message=(
                    f"Bonjour {utilisateur.nom}, votre emprunt de « {livre.titre if livre else 'votre livre'} » "
                    f"arrive à échéance dans 3 jours (le {e.date_retour_prevu.strftime('%d/%m/%Y')}). "
                    f"Pensez à le retourner à temps pour éviter toute pénalité."
                ),
                type="rappel"
            ))
        session.commit()

def verifier_reservations_expirees():
    """Annuler les anciennes réservations 'pret' expirées (cas legacy)."""
    now = datetime.datetime.utcnow()
    with Session(engine) as session:
        reservations_expirees = session.exec(
            select(Reservation).where(
                Reservation.statut == "pret",
                Reservation.date_limite_retrait != None
            )
        ).all()
        for r in reservations_expirees:
            if not r.date_limite_retrait or r.date_limite_retrait > now:
                continue
            r.statut = "expire"
            session.add(r)
            utilisateur = session.get(Utilisateur, r.utilisateur_id)
            livre = session.get(Livre, r.livre_id)
            nom = utilisateur.nom if utilisateur else f"Utilisateur #{r.utilisateur_id}"
            titre_livre = livre.titre if livre else f"Livre #{r.livre_id}"
            if livre:
                livre.exemplaires_disponibles = min(livre.exemplaires_disponibles + 1, livre.total_exemplaires)
                session.add(livre)
            session.add(Notification(
                utilisateur_id=r.utilisateur_id,
                titre="❌ Réservation annulée — délai dépassé",
                message=(
                    f"Bonjour {nom}, votre réservation pour « {titre_livre} » a été automatiquement annulée "
                    f"car le délai de retrait est dépassé. "
                    f"Vous pouvez effectuer une nouvelle réservation si vous le souhaitez."
                ),
                type="avertissement"
            ))
        session.commit()


def diffuser_notification_admin(titre: str, message: str, type_notif: str = "info"):
    with Session(engine) as session:
        membres = session.exec(select(Utilisateur).where(Utilisateur.role == "membre")).all()
        for u in membres:
            session.add(Notification(utilisateur_id=u.id, titre=titre, message=message, type=type_notif))
        session.commit()
        return len(membres)

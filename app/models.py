from sqlmodel import SQLModel, Field
from typing import Optional
import datetime


class Livre(SQLModel, table=True):
    """Table des livres du catalogue."""
    id: Optional[int] = Field(default=None, primary_key=True)
    titre: str
    auteur: Optional[str] = None
    isbn: Optional[str] = None
    annee_publication: Optional[int] = None
    total_exemplaires: int = Field(default=1)
    exemplaires_disponibles: int = Field(default=1)
    couverture: Optional[str] = None  # URL ou base64
    genre: Optional[str] = None
    note: Optional[float] = None
    description: Optional[str] = None


class Utilisateur(SQLModel, table=True):
    """Table des utilisateurs (membres et admins)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str
    email: str
    mot_de_passe: str
    role: str = "membre"           # admin | membre
    type_utilisateur: Optional[str] = None  # etudiant | enseignant
    photo_profil: Optional[str] = None      # base64
    suspendu: bool = False
    date_inscription: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


class Emprunt(SQLModel, table=True):
    """Table des emprunts de livres."""
    id: Optional[int] = Field(default=None, primary_key=True)
    utilisateur_id: int
    livre_id: int
    date_emprunt: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    date_retour_prevu: Optional[datetime.date] = None
    retourne: bool = False
    date_retour_effectif: Optional[datetime.datetime] = None
    # Gestion des emprunts en ligne (via l'application)
    en_attente_retrait: bool = False
    date_limite_retrait: Optional[datetime.datetime] = None
    annule: bool = False


class Reservation(SQLModel, table=True):
    """Table des réservations de livres."""
    id: Optional[int] = Field(default=None, primary_key=True)
    utilisateur_id: int
    livre_id: int
    date_creation: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    statut: str = "attente"  # attente | pret | annule | expire
    date_limite_retrait: Optional[datetime.datetime] = None


class Penalite(SQLModel, table=True):
    """Table des pénalités de retard."""
    id: Optional[int] = Field(default=None, primary_key=True)
    utilisateur_id: int
    emprunt_id: Optional[int] = None
    montant: float
    motif: Optional[str] = None
    payee: bool = False
    date_creation: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


class Notification(SQLModel, table=True):
    """Table des notifications utilisateurs."""
    id: Optional[int] = Field(default=None, primary_key=True)
    utilisateur_id: int
    titre: str = "Notification"
    message: str
    lue: bool = False
    date_creation: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    type: str = "info"  # info | emprunt | retour | reservation | penalite | avertissement | rappel


class CodeAcces(SQLModel, table=True):
    """Table des codes d'accès pour l'inscription."""
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str
    utilise: bool = False
    utilise_par: Optional[str] = None
    date_creation: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


class Parametre(SQLModel, table=True):
    """Table des paramètres de la bibliothèque (clé-valeur)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    cle: str = Field(unique=True)
    valeur: str

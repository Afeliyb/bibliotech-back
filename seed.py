import datetime
from sqlmodel import Session, select
from app.models import Livre, Utilisateur, Emprunt, Reservation, Penalite, Notification, CodeAcces, Parametre
from app.database import engine
from app.crud import hacher_mot_de_passe


def seed():
    with Session(engine) as session:

        # ── Paramètres par défaut ──────────────────────────────────────────────
        parametres_defaut = {
            "nom_bibliotheque": "BiblioTech",
            "adresse": "Université de Lomé, Bâtiment des Sciences",
            "telephone": "+228 22 21 73 48",
            "horaires": "Lun-Ven : 8h00 - 18h00 | Sam : 9h00 - 13h00",
            "email_contact": "bibliotheque@esgis.com",
            "site_web": "https://esgis.com",
            "duree_emprunt_jours": "14",
            "max_emprunts_par_membre": "3",
            "max_reservations_par_membre": "3",
            "penalite_par_jour": "500",
            "penalite_maximum": "10000",
            "delai_retrait_heures": "48",
            "regles": (
                "• Chaque membre peut emprunter jusqu'à 3 livres simultanément.\n"
                "• La durée maximale d'emprunt est de 14 jours.\n"
                "• Tout retard est sanctionné par une pénalité de 500 FCFA/jour (max 10 000 FCFA).\n"
                "• Les réservations doivent être récupérées dans les 48h après notification.\n"
                "• Les livres doivent être retournés en bon état. Toute dégradation sera facturée.\n"
                "• La carte de membre doit être présentée à chaque emprunt.\n"
                "• Le silence doit être respecté dans les espaces de lecture."
            ),
        }
        for cle, valeur in parametres_defaut.items():
            if not session.exec(select(Parametre).where(Parametre.cle == cle)).first():
                session.add(Parametre(cle=cle, valeur=valeur))
        session.commit()

        # ── Administrateur ─────────────────────────────────────────────────────
        if not session.exec(select(Utilisateur).where(Utilisateur.email == "admin@esgis.com")).first():
            session.add(Utilisateur(
                nom="Administrateur ESGIS",
                email="admin@esgis.com",
                mot_de_passe=hacher_mot_de_passe("admin123"),
                role="admin",
            ))
            session.commit()

        # ── Codes d'accès ──────────────────────────────────────────────────────
        for code in ["ESGIS00001", "ESGIS00002", "ESGIS00003", "ESGIS00004", "ESGIS00005"]:
            if not session.exec(select(CodeAcces).where(CodeAcces.code == code)).first():
                session.add(CodeAcces(code=code))
        session.commit()

        # ── Livres ─────────────────────────────────────────────────────────────
        if not session.exec(select(Livre)).first():
            livres = [
                Livre(titre="Le Petit Prince", auteur="Antoine de Saint-Exupéry", genre="Conte",
                      annee_publication=1943, total_exemplaires=3, exemplaires_disponibles=2,
                      couverture="https://m.media-amazon.com/images/I/914RHT4YJaL._SX500_.jpg", note=4.8,
                      description="Un aviateur tombe en panne dans le désert du Sahara et rencontre un mystérieux petit garçon venu d'une autre planète. Un conte poétique et philosophique sur l'amitié, l'amour et le sens de la vie."),
                Livre(titre="1984", auteur="George Orwell", genre="Dystopie",
                      annee_publication=1949, total_exemplaires=2, exemplaires_disponibles=1,
                      couverture="https://images.epagine.fr/100/9782070248100_1_75.jpg", note=4.7,
                      description="Dans un futur dystopique, Winston Smith vit sous la surveillance permanente de Big Brother. Un roman visionnaire sur le totalitarisme, la manipulation et la résistance de l'individu face au pouvoir."),
                Livre(titre="L'Étranger", auteur="Albert Camus", genre="Roman",
                      annee_publication=1942, total_exemplaires=2, exemplaires_disponibles=2,
                      couverture="https://i.pinimg.com/564x/6f/fa/4e/6ffa4ecd1931e36640110d801f4e8483.jpg", note=4.5,
                      description="Meursault, un homme indifférent au monde qui l'entoure, tue un Arabe sur une plage algérienne. Roman fondateur de la philosophie de l'absurde."),
                Livre(titre="Les Misérables", auteur="Victor Hugo", genre="Roman",
                      annee_publication=1862, total_exemplaires=4, exemplaires_disponibles=3,
                      couverture="https://products-images.di-static.com/image/hugo-victor-les-miserables/9782017261438-475x500-1.webp", note=4.9,
                      description="L'épopée de Jean Valjean, ancien forçat qui cherche à se racheter dans la France du XIXe siècle. Une fresque monumentale sur la justice, la miséricorde et la dignité humaine."),
                Livre(titre="Le Comte de Monte-Cristo", auteur="Alexandre Dumas", genre="Roman",
                      annee_publication=1844, total_exemplaires=3, exemplaires_disponibles=3,
                      couverture="https://m.media-amazon.com/images/I/71ZcP22phyL._SX500_.jpg", note=4.8,
                      description="Edmond Dantès, injustement emprisonné, s'évade et revient sous le nom du Comte de Monte-Cristo pour se venger. Un roman d'aventures inoubliable sur la vengeance et la rédemption."),
                Livre(titre="Madame Bovary", auteur="Gustave Flaubert", genre="Roman",
                      annee_publication=1857, total_exemplaires=2, exemplaires_disponibles=2,
                      couverture="https://images.leslibraires.ca/books/9782210765689/front/9782210765689_large.jpg", note=4.3,
                      description="Emma Bovary, femme d'un médecin de province, rêve d'une vie romanesque. Un chef-d'œuvre du réalisme qui décrit la condition féminine et les illusions romantiques."),
                Livre(titre="Candide", auteur="Voltaire", genre="Philosophie",
                      annee_publication=1759, total_exemplaires=3, exemplaires_disponibles=3,
                      couverture="https://images.epagine.fr/851/9782210760851_1_75.jpg", note=4.4,
                      description="Candide traverse une série de catastrophes qui remettent en question l'optimisme naïf de son maître Pangloss. Conte philosophique satirique sur la condition humaine."),
                Livre(titre="Germinal", auteur="Émile Zola", genre="Roman",
                      annee_publication=1885, total_exemplaires=2, exemplaires_disponibles=2,
                      couverture="https://images.epagine.fr/142/9782253094142_1_75.jpg", note=4.6,
                      description="Étienne Lantier découvre les conditions de vie misérables des mineurs. Roman naturaliste puissant sur la lutte des classes et la solidarité ouvrière."),
                Livre(titre="Dune", auteur="Frank Herbert", genre="Science-Fiction",
                      annee_publication=1965, total_exemplaires=2, exemplaires_disponibles=2,
                      couverture="https://actualitte.com/uploads/images/duune-8e8c19e2-30d3-47c5-b624-c0849c2008c5.jpg", note=4.8,
                      description="Sur la planète désertique Arrakis, Paul Atréides affronte son destin légendaire au milieu des intrigues galactiques. Un chef-d'œuvre de la science-fiction mondiale."),
            ]
            for l in livres:
                session.add(l)
            session.commit()

        # ── Membres fictifs ────────────────────────────────────────────────────
        membres_data = [
            ("ADANDJI Yaovi",    "yaovi@esgis.com",   "pass123", "etudiant"),
            ("DOE-BRUCE Folly",  "bruce@esgis.com",   "pass123", "enseignant"),
            ("DIALLO Mariam",    "mariam@esgis.com",  "pass123", "etudiant"),
            ("VOSSA Junior",     "junior@esgis.com",  "pass123", "etudiant"),
            ("MAGLO Osborn",     "osborn@esgis.com",  "pass123", "etudiant"),
        ]
        for nom, email, pw, utype in membres_data:
            if not session.exec(select(Utilisateur).where(Utilisateur.email == email)).first():
                session.add(Utilisateur(nom=nom, email=email,
                                        mot_de_passe=hacher_mot_de_passe(pw),
                                        role="membre", type_utilisateur=utype))
        session.commit()

        # Arrêt si des emprunts existent déjà
        if session.exec(select(Emprunt)).first():
            return

        # ── Récupère les entités ───────────────────────────────────────────────
        def uid(email): return session.exec(select(Utilisateur).where(Utilisateur.email == email)).first()
        def bid(titre): return session.exec(select(Livre).where(Livre.titre == titre)).first()

        yaovi  = uid("yaovi@esgis.com")
        bruce  = uid("bruce@esgis.com")
        mariam = uid("mariam@esgis.com")
        junior = uid("junior@esgis.com")
        osborn = uid("osborn@esgis.com")

        petit_prince = bid("Le Petit Prince")
        orwell       = bid("1984")
        etranger     = bid("L'Étranger")
        miserables   = bid("Les Misérables")
        monte_cristo = bid("Le Comte de Monte-Cristo")

        today = datetime.date.today()

        # ── Emprunts fictifs ───────────────────────────────────────────────────
        emprunts = [
            # yaovi : retourné
            Emprunt(utilisateur_id=yaovi.id, livre_id=petit_prince.id,
                    date_emprunt=datetime.datetime(2025, 12, 1, 9, 0),
                    date_retour_prevu=datetime.date(2025, 12, 15),
                    retourne=True,
                    date_retour_effectif=datetime.datetime(2025, 12, 14, 10, 0)),
            # yaovi : actif (expire dans 3 jours)
            Emprunt(utilisateur_id=yaovi.id, livre_id=orwell.id,
                    date_emprunt=datetime.datetime.utcnow() - datetime.timedelta(days=11),
                    date_retour_prevu=today + datetime.timedelta(days=3),
                    retourne=False),
            # bruce : EN RETARD de 5 jours
            Emprunt(utilisateur_id=bruce.id, livre_id=miserables.id,
                    date_emprunt=datetime.datetime.utcnow() - datetime.timedelta(days=19),
                    date_retour_prevu=today - datetime.timedelta(days=5),
                    retourne=False),
            # mariam : actif
            Emprunt(utilisateur_id=mariam.id, livre_id=etranger.id,
                    date_emprunt=datetime.datetime.utcnow() - datetime.timedelta(days=5),
                    date_retour_prevu=today + datetime.timedelta(days=9),
                    retourne=False),
            # junior : retourné
            Emprunt(utilisateur_id=junior.id, livre_id=monte_cristo.id,
                    date_emprunt=datetime.datetime(2025, 11, 10, 10, 0),
                    date_retour_prevu=datetime.date(2025, 11, 24),
                    retourne=True,
                    date_retour_effectif=datetime.datetime(2025, 11, 25, 9, 0)),
            # osborn : EN RETARD de 2 jours
            Emprunt(utilisateur_id=osborn.id, livre_id=petit_prince.id,
                    date_emprunt=datetime.datetime.utcnow() - datetime.timedelta(days=16),
                    date_retour_prevu=today - datetime.timedelta(days=2),
                    retourne=False),
        ]
        for e in emprunts:
            session.add(e)
        session.commit()

        # Mettre à jour les exemplaires disponibles
        for livre, delta in [
            (orwell,       -1),
            (miserables,   -1),
            (etranger,     -1),
            (petit_prince, -1),
        ]:
            l = session.get(Livre, livre.id)
            l.exemplaires_disponibles = max(0, l.exemplaires_disponibles + delta)
            session.add(l)
        session.commit()

        # ── Pénalités fictives ─────────────────────────────────────────────────
        e_bruce = session.exec(select(Emprunt).where(Emprunt.utilisateur_id == bruce.id)).first()
        session.add(Penalite(
            utilisateur_id=bruce.id, emprunt_id=e_bruce.id,
            montant=2500, motif="Retard de 5 jours (500 FCFA/jour)", payee=False
        ))
        e_osborn = session.exec(select(Emprunt).where(Emprunt.utilisateur_id == osborn.id)).first()
        session.add(Penalite(
            utilisateur_id=osborn.id, emprunt_id=e_osborn.id,
            montant=1000, motif="Retard de 2 jours (500 FCFA/jour)", payee=False
        ))
        e_junior = session.exec(select(Emprunt).where(Emprunt.utilisateur_id == junior.id)).first()
        session.add(Penalite(
            utilisateur_id=junior.id, emprunt_id=e_junior.id,
            amount=500, motif="Retard de 1 jour (500 FCFA/jour)", payee=True
        ) if False else Penalite(
            utilisateur_id=junior.id, emprunt_id=e_junior.id,
            montant=500, motif="Retard de 1 jour (500 FCFA/jour)", payee=True
        ))
        session.commit()

        # ── Notifications fictives ─────────────────────────────────────────────
        notifs = [
            Notification(utilisateur_id=yaovi.id, titre="✅ Emprunt confirmé",
                         message="Bonjour ADANDJI Yaovi, votre emprunt de « 1984 » a été confirmé. Retour prévu le " + (today + datetime.timedelta(days=3)).strftime('%d/%m/%Y') + ".",
                         type="emprunt"),
            Notification(utilisateur_id=bruce.id, titre="🚨 Retard de retour",
                         message="Bonjour DOE-BRUCE Folly, votre emprunt de « Les Misérables » est en retard de 5 jours. Pénalité : 2 500 FCFA.",
                         type="penalite"),
            Notification(utilisateur_id=osborn.id, titre="🚨 Retard de retour",
                         message="Bonjour MAGLO Osborn, votre emprunt de « Le Petit Prince » est en retard de 2 jours. Pénalité : 1 000 FCFA.",
                         type="penalite"),
            Notification(utilisateur_id=mariam.id, titre="✅ Emprunt confirmé",
                         message="Bonjour DIALLO Mariam, votre emprunt de « L'Étranger » a été confirmé. Retour prévu le " + (today + datetime.timedelta(days=9)).strftime('%d/%m/%Y') + ".",
                         type="emprunt"),
            Notification(utilisateur_id=junior.id, titre="📕 Retour enregistré",
                         message="Bonjour VOSSA Junior, le retour de « Le Comte de Monte-Cristo » a bien été enregistré. Merci !",
                         type="retour"),
        ]
        for n in notifs:
            session.add(n)
        session.commit()

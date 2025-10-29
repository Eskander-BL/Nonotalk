#!/usr/bin/env python3
"""
Script autonome et allégé pour réinitialiser la base de données de NonoTalk.

Objectif:
- NE PAS importer src.main, ni les routes Flask, ni LangChain
- Lire la configuration depuis .env (DATABASE_URL)
- Initialiser uniquement Flask et SQLAlchemy (via src.models.user)
- drop_all + create_all
- Afficher un message de succès
"""

import os
import sys

# S'assurer que le répertoire projet (celui contenant 'src/') est dans sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
from flask import Flask

# Importer le db et les modèles pour que SQLAlchemy voie toutes les tables
# (Pas d'import de src.main ni de routes ici)
from src.models.user import db, User, Conversation, Message, CrisisAlert, Invitation  # noqa: F401


def create_app() -> Flask:
    """Crée une application Flask minimale, configurée uniquement pour SQLAlchemy."""
    # Charger le .env depuis la racine du projet
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL est manquante. Ajoutez-la dans le fichier .env à la racine du projet."
        )

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Forcer SSL pour Neon (cohérent avec src/main.py)
    if database_url.startswith("postgresql"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"sslmode": "require"}}

    # Initialiser l'extension avec cette app
    db.init_app(app)
    return app


def reset_database() -> None:
    """Supprime toutes les tables et les recrée."""
    app = create_app()
    try:
        with app.app_context():
            db.drop_all()
            print("✓ Anciennes tables supprimées")

            db.create_all()
            print("✓ Nouvelles tables créées")

        print("✓ Base de données réinitialisée avec succès !")
    except Exception as e:
        print(f"✗ Erreur lors de la réinitialisation de la base: {e}")
        sys.exit(1)


if __name__ == "__main__":
    reset_database()

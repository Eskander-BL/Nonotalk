import os
from dotenv import load_dotenv
from flask import Flask
from src.models.user import db, User

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Forcer SSL pour Neon
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"sslmode": "require"}
    }

db.init_app(app)

# Ajouter un utilisateur de test
with app.app_context():
    try:
        test_user = User(
            username="test_user",
            email="test@example.com",
            pin_hash="1234"
        )
        db.session.add(test_user)
        db.session.commit()
        print("✅ Utilisateur de test ajouté avec succès à la base Neon !")
    except Exception as e:
        print("❌ Erreur :", e)

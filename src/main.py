import os
import sys
import re
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
project_root = os.path.dirname(os.path.dirname(__file__))
load_dotenv(os.path.join(project_root, '.env'))

from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_session import Session
from src.models.user import db
from src.routes.user import user_bp
from src.routes.auth import auth_bp
from src.routes.chat import chat_bp
from src.routes.tts import tts_bp
from src.routes.static import static_bp
from src.routes.invite import invite_bp

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'nonotalk-secret-key-2025')
db_url = os.getenv('DATABASE_URL')
# Normalise et force le driver psycopg (psycopg3) pour compatibilité Render/Python 3.13
if db_url:
    # Render fournit parfois 'postgres://', que SQLAlchemy déconseille
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    # Remplacer +psycopg2 par +psycopg pour psycopg3
    if db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    # Si aucun driver n'est précisé, on impose psycopg (psycopg3)
    if db_url.startswith("postgresql://") and "+psycopg" not in db_url and "+psycopg2" not in db_url and "+pg8000" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
if db_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    # Fallback SQLite pour développement local
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

import os
from datetime import timedelta

is_production = os.getenv('FLASK_ENV') == 'production'

# Configuration de session
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

if is_production:
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
    app.config['SESSION_COOKIE_SECURE'] = True
    # Définir le domaine cookie pour permettre le partage entre frontend et backend sur vercel.app
    app.config['SESSION_COOKIE_DOMAIN'] = '.vercel.app'
else:
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Lax car proxy Vite = même origine
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['SESSION_COOKIE_DOMAIN'] = None

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_NAME'] = 'nonotalk_session'

# Options moteur SQLAlchemy: SSL requis + pré-ping pour éviter timeouts Render
if app.config['SQLALCHEMY_DATABASE_URI'] and app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgresql"):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_pre_ping": True,  # évite les timeouts Render / connexions dormantes
        "connect_args": {"sslmode": "require"}  # sécurise la connexion PostgreSQL
    }

# CORS précis pour origines autorisées (credentials cross-site)
# Exemple d'ENV: FRONTEND_ORIGINS="https://nonotalk-frontend.onrender.com,http://localhost:5173"
frontend_origins_env = os.getenv('FRONTEND_ORIGINS', '')
origins_list = [o.strip() for o in frontend_origins_env.split(',') if o.strip()]
if not origins_list:
    origins_list = [
        'http://localhost:5173',
        'http://127.0.0.1:5173',
        'http://localhost:4173',
        'https://nonotalk-frontend.onrender.com'
    ]

def cors_origin_validator(origin):
    if origin is None:
        return False
    # Autoriser localhost et 127.0.0.1
    if origin in origins_list:
        return True
    # Autoriser les sous-domaines vercel.app (frontend et backend)
    if origin.endswith('.vercel.app'):
        return True
    return False

def cors_origin_callable(origin):
    if cors_origin_validator(origin):
        return origin
    return False

CORS(app, supports_credentials=True, resources={r"/*": {"origins": cors_origin_callable}})

# Initialisation de Flask-Session
Session(app)

# Enregistrement des blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(chat_bp, url_prefix='/api/chat')
app.register_blueprint(tts_bp, url_prefix='/api')
app.register_blueprint(static_bp, url_prefix='/api')
app.register_blueprint(invite_bp, url_prefix='/api')

# Initialisation de la base de données
db.init_app(app)
with app.app_context():
    db.create_all()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
            return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404

@app.route('/api/health', methods=['GET'])
def health_check():
    """Point de santé de l'API"""
    return {'status': 'ok', 'message': 'NonoTalk API is running'}, 200

@app.route('/api/test', methods=['GET'])
def test_endpoint():
    """Endpoint de test pour vérifier l'API"""
    return {'status': 'ok', 'message': 'API is working', 'cors': 'enabled'}, 200

if __name__ == '__main__':
    # threaded=True pour éviter tout blocage et améliorer le flush SSE en dev
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)

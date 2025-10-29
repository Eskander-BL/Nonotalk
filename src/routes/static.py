from flask import Blueprint, send_from_directory, current_app
import os

static_bp = Blueprint('static', __name__)

@static_bp.route('/uploads/<filename>')
def uploaded_file(filename):
    """Servir les fichiers uploadés"""
    upload_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'uploads')
    return send_from_directory(upload_dir, filename)


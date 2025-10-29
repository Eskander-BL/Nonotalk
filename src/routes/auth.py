from flask import Blueprint, request, jsonify, session
from src.models.user import db, User, Invitation
from datetime import datetime
from sqlalchemy.exc import IntegrityError
import os

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    """Connexion utilisateur avec username et PIN"""
    try:
        data = request.get_json()
        username = data.get('username')
        pin = data.get('pin')

        if not username or not pin:
            return jsonify({'error': 'Username et PIN requis'}), 400


        user = User.query.filter_by(username=username).first()
        if not user or not user.check_pin(pin):
            return jsonify({'error': 'Identifiants invalides'}), 401

        # Mise à jour de la dernière connexion
        user.last_login = datetime.utcnow()
        db.session.commit()

        # Session
        session['user_id'] = user.id
        session['username'] = user.username

        return jsonify({
            'message': 'Connexion réussie',
            'user': user.to_dict()
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/register', methods=['POST'])
def register():
    """Inscription d'un nouvel utilisateur"""
    try:
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        pin = data.get('pin')
        parrain_email = data.get('parrain_email')

        if not username or not pin:
            return jsonify({'error': 'Username et PIN requis'}), 400

        # Validation email obligatoire
        if not email or not str(email).strip():
            return jsonify({'error': 'Le champ email est obligatoire'}), 400
        email = str(email).strip()

        # Vérifier si l'utilisateur existe déjà
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Ce nom d\'utilisateur existe déjà'}), 400

        if email and User.query.filter_by(email=email).first():
            return jsonify({'error': 'Cet email est déjà utilisé'}), 400

        # Créer le nouvel utilisateur
        new_user = User(
            username=username,
            email=email,
            parrain_email=parrain_email
        )
        new_user.set_pin(pin)

        # Gestion du parrainage
        bonus_quota = 0
        # Priorité à une invitation existante basée sur l'email du nouvel utilisateur
        invitation = Invitation.query.filter_by(email=email, accepted=False).first()
        if invitation:
            parrain = User.query.get(invitation.inviter_id)
            if parrain:
                # +5 pour le parrain et le filleul
                parrain.add_quota(5)
                parrain.filleuls_count += 1
                new_user.add_quota(5)  # +5 en plus des 10 de base
                bonus_quota = 5
                invitation.accepted = True
                invitation.accepted_at = datetime.utcnow()
        elif parrain_email:
            parrain = User.query.filter_by(email=parrain_email).first()
            if parrain:
                # +5 pour le parrain et le filleul
                parrain.add_quota(5)
                parrain.filleuls_count += 1
                new_user.add_quota(5)  # +5 en plus des 10 de base
                bonus_quota = 5

        db.session.add(new_user)
        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            err_msg = str(e).lower()
            if 'user.username' in err_msg or 'username' in err_msg:
                return jsonify({'error': "Ce nom d'utilisateur existe déjà"}), 400
            if 'user.email' in err_msg or 'email' in err_msg:
                return jsonify({'error': "Cet email est déjà utilisé"}), 400
            return jsonify({'error': "Erreur d'intégrité des données"}), 400

        # Session automatique après inscription
        session['user_id'] = new_user.id
        session['username'] = new_user.username

        return jsonify({
            'message': 'Inscription réussie',
            'user': new_user.to_dict(),
            'bonus_quota': bonus_quota
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Déconnexion utilisateur"""
    session.clear()
    return jsonify({'message': 'Déconnexion réussie'}), 200

@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    """Récupérer les informations de l'utilisateur connecté"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Non connecté'}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Utilisateur non trouvé'}), 404

    return jsonify({'user': user.to_dict()}), 200

@auth_bp.route('/check-quota', methods=['GET'])
def check_quota():
    """Vérifier le quota restant de l'utilisateur"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Non connecté'}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Utilisateur non trouvé'}), 404

    return jsonify({
        'quota_remaining': user.quota_remaining,
        'total_quota': user.total_quota,
        'can_chat': user.quota_remaining > 0
    }), 200

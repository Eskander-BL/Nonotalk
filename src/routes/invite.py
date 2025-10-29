from flask import Blueprint, request, jsonify, session
from datetime import datetime
from src.models.user import db, User, Invitation
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
import traceback

invite_bp = Blueprint('invite', __name__)

def build_invitation_html(base_url: str, signup_url: str, inviter_name: str) -> str:
    logo_url = f"{base_url.rstrip('/')}/logonono.png"
    avatar_url = f"{base_url.rstrip('/')}/assets/ai-avatar.png"
    # Fallback si logo/asset non disponibles publiquement
    # Vous pouvez héberger les images sur votre domaine et ajuster base_url via PUBLIC_BASE_URL
    return f"""
<div style="font-family:Arial, sans-serif; text-align:center; color:#333;">
  <img src="{logo_url}" alt="NonoTalk" width="90" style="margin-bottom:15px;">
  <h2 style="color:#6c4bff;">Ton ami {inviter_name} t’a invité à rejoindre NonoTalk 💜</h2>
  <p>Une application bienveillante où tu peux parler librement et en toute confidentialité.</p>
  <p>Rejoins-nous et commence à discuter avec Nono dès aujourd’hui 👇</p>
  <p><strong>Profite de +5 échanges grâce à l'invitation</strong></p>
  <a href="{signup_url}"
     style="background:#6c4bff; color:white; padding:12px 24px; border-radius:8px;
            text-decoration:none; display:inline-block; margin-top:10px;">
     Rejoindre NonoTalk 💬
  </a>
  <div style="margin-top:18px;">
    <img src="{avatar_url}" alt="Nono" width="140" style="border-radius:12px;">
  </div>
  <p style="margin-top:20px; font-size:13px; color:#777;">
    Ce message t’a été envoyé par NonoTalk — toujours là pour t’écouter 💜
  </p>
</div>
""".strip()

def send_invitation_email(to_email: str, inviter_name: str) -> bool:
    try:
        smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_user = os.getenv('SMTP_USER')  # pas de défaut dangereux
        smtp_pass = os.getenv('SMTP_PASSWORD')  # pas de défaut dangereux
        smtp_from = os.getenv('SMTP_FROM') or smtp_user or 'no-reply@nonotalk.local'
        smtp_from_name = os.getenv('SMTP_FROM_NAME', '📩 NonoTalk')
        public_base = os.getenv('PUBLIC_BASE_URL', 'https://nonoTalk.fr')
        signup_url = os.getenv('APP_SIGNUP_URL', f'{public_base.rstrip("/")}/signup de l/app quand sera prête')
        smtp_secure = (os.getenv('SMTP_SECURE') or '').strip().lower()  # 'ssl' | 'starttls' | 'none' | ''
        smtp_debug = (os.getenv('SMTP_DEBUG') or '').strip().lower() in ('1', 'true', 'yes', 'on')

        subject = "📩 Ton ami t’invite à rejoindre NonoTalk"
        html = build_invitation_html(public_base, signup_url, inviter_name)

        # Texte simple fallback
        text = (
            f"Ton ami {inviter_name} t’invite à rejoindre NonoTalk.\n"
            f"Profite de +5 échanges grâce à l’invitation.\n"
            f"Inscris-toi ici: {signup_url}\n"
        )

        msg = MIMEMultipart('alternative')
        msg['From'] = formataddr((smtp_from_name, smtp_from))
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(text, 'plain', 'utf-8'))
        msg.attach(MIMEText(html, 'html', 'utf-8'))

        server = None
        try:
            # Déterminer le mode sécurisé si non fourni
            secure = smtp_secure
            if secure not in ('ssl', 'starttls', 'none'):
                if smtp_port == 465:
                    secure = 'ssl'
                elif smtp_port == 587:
                    secure = 'starttls'
                else:
                    secure = 'starttls'

            print(f"[invite] SMTP connecting to {smtp_host}:{smtp_port} secure={secure} user={(smtp_user[:3] + '***') if smtp_user else '(none)'} from={smtp_from}")
            if secure == 'ssl':
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=20)

            server.set_debuglevel(1 if smtp_debug else 0)
            server.ehlo()
            if secure == 'starttls':
                server.starttls()
                server.ehlo()

            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            else:
                print("[invite] Attention: SMTP_USER ou SMTP_PASSWORD manquant - tentative sans authentification")

            server.sendmail(smtp_from, [to_email], msg.as_string())
            return True
        finally:
            try:
                if server:
                    server.quit()
            except Exception:
                pass
    except Exception as e:
        print(f"[invite] Erreur envoi email à {to_email}: {e.__class__.__name__}: {e}")
        traceback.print_exc()
        return False

@invite_bp.route('/invite', methods=['POST'])
def create_invitation():
    """
    Créer une invitation de parrainage
    Route: POST /api/invite
    body: { "email": "ami@example.com", "invited_by": "username" }
    """
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Non connecté'}), 401

        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()
        invited_by = data.get('invited_by')  # non obligatoire, on fait foi de la session

        if not email:
            return jsonify({'error': 'Email requis'}), 400
        if '@' not in email:
            return jsonify({'error': 'Email invalide'}), 400

        inviter = User.query.get(user_id)
        if not inviter:
            return jsonify({'error': 'Utilisateur non trouvé'}), 404

        # Ne pas autoriser l'auto-invitation
        if inviter.email and inviter.email.lower() == email:
            return jsonify({'error': 'Tu ne peux pas t’inviter toi-même'}), 400

        # Si un compte existe déjà avec cet email
        existing_user = User.query.filter(User.email == email).first()
        if existing_user:
            return jsonify({'error': 'Cet email a déjà un compte'}), 400

        # Idempotent: si une invitation en attente existe déjà, on peut renvoyer l'email
        existing_invite = Invitation.query.filter_by(inviter_id=inviter.id, email=email, accepted=False).first()
        if existing_invite:
            email_sent = send_invitation_email(email, inviter.username)
            return jsonify({
                'message': 'Invitation déjà envoyée',
                'invitation': existing_invite.to_dict(),
                'email_sent': email_sent
            }), 200

        invitation = Invitation(inviter_id=inviter.id, email=email)
        db.session.add(invitation)
        db.session.commit()

        email_sent = send_invitation_email(email, inviter.username)

        return jsonify({
            'message': 'Invitation créée',
            'invitation': invitation.to_dict(),
            'email_sent': email_sent
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

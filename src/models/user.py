from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    pin_hash = db.Column(db.String(255), nullable=False)
    quota_remaining = db.Column(db.Integer, default=10)
    total_quota = db.Column(db.Integer, default=10)
    parrain_email = db.Column(db.String(120), nullable=True)
    filleuls_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    conversations = db.relationship('Conversation', backref='user', lazy=True, cascade='all, delete-orphan')
    crisis_alerts = db.relationship('CrisisAlert', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_pin(self, pin):
        """Hash and set the PIN"""
        self.pin_hash = generate_password_hash(str(pin))

    def check_pin(self, pin):
        """Check if the provided PIN matches"""
        return check_password_hash(self.pin_hash, str(pin))

    def add_quota(self, amount):
        """Add quota to user"""
        self.quota_remaining += amount
        self.total_quota += amount

    def use_quota(self):
        """Use one quota point"""
        if self.quota_remaining > 0:
            self.quota_remaining -= 1
            return True
        return False

    def __repr__(self):
        return f'<User {self.username}>'

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'quota_remaining': self.quota_remaining,
            'total_quota': self.total_quota,
            'filleuls_count': self.filleuls_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    messages = db.relationship('Message', backref='conversation', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Conversation {self.id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'message_count': len(self.messages)
        }

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_user = db.Column(db.Boolean, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    emotion_detected = db.Column(db.String(50), nullable=True)
    image_path = db.Column(db.String(255), nullable=True)
    audio_path = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f'<Message {self.id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'content': self.content,
            'is_user': self.is_user,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'emotion_detected': self.emotion_detected,
            'image_path': self.image_path,
            'audio_path': self.audio_path
        }

class CrisisAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message_content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    resolved = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<CrisisAlert {self.id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'message_content': self.message_content,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'resolved': self.resolved
        }

class Invitation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inviter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    accepted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    accepted_at = db.Column(db.DateTime, nullable=True)

    # Relation vers le parrain (inviter)
    inviter = db.relationship('User', backref=db.backref('invitations_sent', lazy=True))

    def __repr__(self):
        return f'<Invitation {self.id} -> {self.email}>'

    def to_dict(self):
        return {
            'id': self.id,
            'inviter_id': self.inviter_id,
            'email': self.email,
            'accepted': self.accepted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'accepted_at': self.accepted_at.isoformat() if self.accepted_at else None
        }

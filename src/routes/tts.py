from flask import Blueprint, request, jsonify, send_file
import os
from openai import OpenAI
from datetime import datetime
import io
import tempfile
import time

tts_bp = Blueprint('tts', __name__)

# Configuration OpenAI
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'sk-fake-key')
OPENAI_API_BASE = os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1')
client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)

@tts_bp.route('/text-to-speech', methods=['POST'])
def text_to_speech():
    """Convertir du texte en audio avec OpenAI TTS"""
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        voice = data.get('voice', 'nova')  # nova ou shimmer

        if not text:
            return jsonify({'error': 'Texte requis'}), 400

        # Valider la voix
        if voice not in ['nova', 'shimmer']:
            voice = 'nova'

        # Pour le moment, retourner une réponse simulée
        # En production, utiliser l'API OpenAI TTS
        """
        response = openai.Audio.create(
            model="tts-1-hd",
            voice=voice,
            input=text
        )
        """

        # Simulation - créer un fichier audio factice
        audio_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'audio')
        os.makedirs(audio_dir, exist_ok=True)
        
        filename = f"tts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
        audio_path = os.path.join(audio_dir, filename)
        
        # Créer un fichier audio vide pour la simulation
        with open(audio_path, 'wb') as f:
            f.write(b'')  # Fichier vide pour la simulation

        return jsonify({
            'audio_url': f'/api/audio/{filename}',
            'message': 'Audio généré (simulation)'
        }), 200

    except Exception as e:
        return jsonify({'error': f'Erreur TTS: {str(e)}'}), 500

@tts_bp.route('/audio/<filename>', methods=['GET'])
def serve_audio(filename):
    """Servir les fichiers audio générés"""
    try:
        audio_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'audio')
        audio_path = os.path.join(audio_dir, filename)
        
        if not os.path.exists(audio_path):
            return jsonify({'error': 'Fichier audio non trouvé'}), 404

        return send_file(audio_path, mimetype='audio/mpeg')

    except Exception as e:
        return jsonify({'error': f'Erreur lors de la lecture: {str(e)}'}), 500

@tts_bp.route('/speech-to-text', methods=['POST'])
def speech_to_text():
    """Convertir de l'audio en texte avec OpenAI Whisper"""
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'Fichier audio requis'}), 400

        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'error': 'Aucun fichier sélectionné'}), 400

        # Lecture en mémoire pour éviter les écritures disque et délais Windows
        transcript_text = None
        try:
            raw = audio_file.read()
            buf = io.BytesIO(raw)
            # Donner un nom de fichier pour compatibilité SDK
            buf.name = audio_file.filename or 'audio.webm'
            if OPENAI_API_KEY and OPENAI_API_KEY != 'sk-fake-key':
                try:
                    stt_model = os.getenv('OPENAI_STT_MODEL', 'whisper-1')
                    resp = client.audio.transcriptions.create(
                        model=stt_model,
                        file=buf
                    )
                    transcript_text = getattr(resp, 'text', None) or (resp.get('text') if isinstance(resp, dict) else None)
                except Exception as stt_err:
                    print(f"[backend] STT error: {stt_err}")
                    transcript_text = None
        except Exception as read_err:
            print(f"[backend] STT read error: {read_err}")
            transcript_text = None

        if not transcript_text:
            transcript_text = "Transcription simulée du message vocal"

        return jsonify({
            'transcript': transcript_text,
            'message': 'Transcription réussie (simulation)'
        }), 200

    except Exception as e:
        return jsonify({'error': f'Erreur STT: {str(e)}'}), 500

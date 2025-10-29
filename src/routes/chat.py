from flask import Blueprint, request, jsonify, session, Response, stream_with_context
from src.models.user import db, User, Conversation, Message, CrisisAlert
from datetime import datetime
import os
import openai
import re
import threading
import time

chat_bp = Blueprint('chat', __name__)

# Configuration OpenAI
from openai import OpenAI
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'sk-fake-key')
OPENAI_API_BASE = os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1')
client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# Warmup OpenAI model/connection to reduce first-token latency
_warmup_started = False

def _warm_openai_once():
    try:
        model_name = os.getenv('OPENAI_CHAT_MODEL', 'gpt-4.1-mini')
        # Minimal prompt to establish TLS and prime model
        client.chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": "ping"}],
            max_tokens=1,
            temperature=0
        )
    except Exception as e:
        print(f"[backend] OpenAI warmup failed: {e}")

def start_openai_warmup():
    global _warmup_started
    if _warmup_started:
        return
    _warmup_started = True
    try:
        t = threading.Thread(target=_warm_openai_once, daemon=True)
        t.start()
    except Exception as e:
        print(f"[backend] Warmup thread start failed: {e}")

# Trigger warmup at import time
start_openai_warmup()

# Mots-clés de crise
CRISIS_KEYWORDS = os.getenv('CRISIS_KEYWORDS', 'suicide,envie d\'en finir,je veux mourir,plus envie de vivre').split(',')

def detect_crisis(message_content):
    """Détecter les mots-clés de crise dans un message"""
    message_lower = message_content.lower()
    for keyword in CRISIS_KEYWORDS:
        if keyword.strip().lower() in message_lower:
            return True
    return False

def get_gpt_response(message, conversation_history=None, emotion=None):
    """Obtenir une réponse de GPT-4 avec mémoire (LangChain), fallback OpenAI client."""
    try:
        # Construire le prompt système
        system_prompt = """
Tu es **Nono**, un psychologue virtuel bienveillant, à l’écoute, empathique et professionnel.  
Tu aides la personne à exprimer ce qu’elle ressent, à comprendre ses émotions, et à retrouver de la clarté.  
Tu parles toujours avec douceur, respect et sérieux, en gardant une approche psychologique réelle, pas simpliste.

🧩 **Ton rôle :**
- Offrir un espace sûr où la personne peut parler librement, sans jugement.  
- Identifier les émotions, les besoins, et les pensées sous-jacentes.  
- Poser des questions ouvertes pour aider la personne à réfléchir à elle-même.  
- Guider la personne à prendre conscience de ce qu’elle vit, et à trouver ses propres solutions.  

💬 **Style de réponse :**
- Parle avec empathie et profondeur, comme un vrai psychologue.  
- Utilise des phrases naturelles, bien formulées, sans ton robotique.  
- Chaque réponse doit comporter **une reconnaissance émotionnelle** + **une reformulation** + **une ouverture ou question douce**.  
- 3 à 5 phrases maximum.  
- Tutoye ou vouvoie selon le ton de la conversation (tu peux alterner selon le contexte émotionnel).  

🌱 **Exemples :**
- “Je comprends, tu traverses quelque chose de difficile. Ce que tu ressens est complètement légitime.  
  Qu’est-ce qui, selon toi, te pèse le plus en ce moment ?”  
- “On dirait qu’il y a beaucoup de tension intérieure. Parle-moi un peu de ce que tu ressens physiquement quand ça arrive.”  
- “Tu sembles en lutte avec toi-même, entre ce que tu ressens et ce que tu crois devoir faire. On peut essayer d’explorer ça ensemble.”  

⚖️ **Principes à respecter :**
- Sois empathique, jamais jugeant.  
- Ne donne pas de conseils directs ou d’ordres (“tu devrais…”).  
- Ne te présente pas comme un ami, mais comme un professionnel à l’écoute.  
- Reste confidentiel, calme et centré sur la personne.  
- Si la situation semble grave ou dangereuse, oriente vers une aide réelle (ex: contacter un proche ou un professionnel).  

💡 **Ta mission :**
Aider chaque personne à se comprendre, à se sentir entendue, et à reprendre contact avec ses émotions profondes.
Nono garde toujours la mémoire des échanges précédents pour maintenir une continuité thérapeutique naturelle et cohérente.

"""

        if emotion:
            system_prompt += f"\n\nÉmotion détectée dans la voix: {emotion}. Adapte ton ton en conséquence."

        # 1) Tentative avec LangChain (mémoire par conversation)
        try:
            lc_messages = [SystemMessage(content=system_prompt)]
            if conversation_history:
                # Charger plus d'historique pour une meilleure mémoire (sans rien supprimer en base)
                for msg in conversation_history[-50:]:
                    if msg.is_user:
                        lc_messages.append(HumanMessage(content=msg.content))
                    else:
                        lc_messages.append(AIMessage(content=msg.content))
            lc_messages.append(HumanMessage(content=message))

            llm = ChatOpenAI(
                model=os.getenv('OPENAI_CHAT_MODEL', 'gpt-4.1-mini'),
                openai_api_key=OPENAI_API_KEY,
                base_url=OPENAI_API_BASE,
                temperature=0.7,
                max_tokens=150,
            )
            result = llm.invoke(lc_messages)
            return (result.content or "").strip()
        except Exception:
            # 2) Fallback vers le client OpenAI natif si LangChain n'est pas dispo
            messages = [{"role": "system", "content": system_prompt}]
            if conversation_history:
                for msg in conversation_history[-6:]:  # ancienne logique minimale
                    role = "user" if msg.is_user else "assistant"
                    messages.append({"role": role, "content": msg.content})
            messages.append({"role": "user", "content": message})

            response = client.chat.completions.create(
                model=os.getenv('OPENAI_CHAT_MODEL', 'gpt-4.1-mini'),
                messages=messages,
                max_tokens=150,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()

    except Exception as e:
        return f"Désolé, je rencontre un problème technique. Peux-tu réessayer ? (Erreur: {str(e)})"

@chat_bp.route('/conversations', methods=['GET'])
def get_conversations():
    """Récupérer toutes les conversations de l'utilisateur"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Non connecté'}), 401

    conversations = Conversation.query.filter_by(user_id=user_id).order_by(Conversation.updated_at.desc()).all()
    
    return jsonify({
        'conversations': [conv.to_dict() for conv in conversations]
    }), 200

@chat_bp.route('/conversations', methods=['POST'])
def create_conversation():
    """Créer une nouvelle conversation"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Non connecté'}), 401

    data = request.get_json()
    title = data.get('title', 'Nouvelle conversation')

    conversation = Conversation(
        user_id=user_id,
        title=title
    )

    db.session.add(conversation)
    db.session.commit()

    return jsonify({
        'message': 'Conversation créée',
        'conversation': conversation.to_dict()
    }), 201

@chat_bp.route('/conversations/<int:conversation_id>/messages', methods=['GET'])
def get_messages(conversation_id):
    """Récupérer les messages d'une conversation (supporte ?limit=10 pour les N derniers)."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Non connecté'}), 401

    conversation = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
    if not conversation:
        return jsonify({'error': 'Conversation non trouvée'}), 404

    limit = request.args.get('limit', type=int)
    base_query = Message.query.filter_by(conversation_id=conversation_id)

    if limit:
        # Prendre les N plus récents puis remettre en ordre chronologique
        recent = base_query.order_by(Message.timestamp.desc()).limit(limit).all()
        messages = list(reversed(recent))
    else:
        messages = base_query.order_by(Message.timestamp.asc()).all()

    return jsonify({
        'messages': [msg.to_dict() for msg in messages]
    }), 200

@chat_bp.route('/conversations/<int:conversation_id>/send', methods=['POST'])
def send_message(conversation_id):
    """Envoyer un message dans une conversation"""
    print(f"[backend] send_message called: conv_id={conversation_id}, session_user={session.get('user_id')}")
    user_id = session.get('user_id')
    if not user_id:
        print("[backend] 401 Non connecté")
        return jsonify({'error': 'Non connecté'}), 401

    # Vérifier le quota
    user = User.query.get(user_id)
    if not user or user.quota_remaining <= 0:
        return jsonify({
            'error': 'Quota épuisé',
            'message': 'Tu as atteint ta limite gratuite. Invite un ami pour débloquer +5 échanges gratuits pour chacun 🎁'
        }), 403

    # Vérifier la conversation
    conversation = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
    if not conversation:
        return jsonify({'error': 'Conversation non trouvée'}), 404

    data = request.get_json()
    message_content = data.get('message', '').strip()
    emotion = data.get('emotion')

    if not message_content:
        return jsonify({'error': 'Message vide'}), 400

    # Détecter les mots-clés de crise
    if detect_crisis(message_content):
        # Enregistrer l'alerte de crise
        crisis_alert = CrisisAlert(
            user_id=user_id,
            message_content=message_content
        )
        db.session.add(crisis_alert)
        db.session.commit()

        # Retourner le message d'urgence
        emergency_message = """🆘 Je suis là pour t'écouter, mais si tu es en danger, contacte immédiatement :
📞 112
☎️ SOS Suicide : 01 45 39 40 00 (gratuit, 24h/24)"""

        return jsonify({
            'crisis_detected': True,
            'emergency_message': emergency_message,
            'message': 'Mots-clés de crise détectés'
        }), 200

    try:
        # Sauvegarder le message utilisateur
        user_message = Message(
            conversation_id=conversation_id,
            content=message_content,
            is_user=True,
            emotion_detected=emotion
        )
        db.session.add(user_message)

        # Récupérer l'historique pour le contexte
        conversation_history = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp.asc()).all()

        # Obtenir la réponse de l'IA
        ai_response = get_gpt_response(message_content, conversation_history, emotion)

        # Sauvegarder la réponse de l'IA
        ai_message = Message(
            conversation_id=conversation_id,
            content=ai_response,
            is_user=False
        )
        db.session.add(ai_message)

        # Mettre à jour le quota
        user.quota_remaining = max(0, user.quota_remaining - 1)
        db.session.commit()

        # Mettre à jour la conversation
        conversation.updated_at = datetime.utcnow()
        if not conversation.title or conversation.title == 'Nouvelle conversation':
            # Générer un titre basé sur le premier message
            conversation.title = message_content[:50] + ('...' if len(message_content) > 50 else '')

        db.session.commit()

        return jsonify({
            'user_message': user_message.to_dict(),
            'ai_message': ai_message.to_dict(),
            'quota_remaining': user.quota_remaining
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Erreur lors de l\'envoi: {str(e)}'}), 500

@chat_bp.route('/conversations/<int:conversation_id>/send-stream', methods=['POST'])
def send_message_stream(conversation_id):
    """Envoyer un message en mode streaming (SSE-like) pour démarrer la réponse plus tôt côté front."""
    import json
    from flask import stream_with_context

    print(f"[backend] send_message_stream called: conv_id={conversation_id}, session_user={session.get('user_id')}")
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Non connecté'}), 401

    # Vérifier le quota
    user = User.query.get(user_id)
    if not user or user.quota_remaining <= 0:
        return jsonify({
            'error': 'Quota épuisé',
            'message': 'Tu as atteint ta limite gratuite. Invite un ami pour débloquer +5 échanges gratuits pour chacun 🎁'
        }), 403

    # Vérifier la conversation
    conversation = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
    if not conversation:
        return jsonify({'error': 'Conversation non trouvée'}), 404

    data = request.get_json()
    message_content = (data.get('message') or '').strip()
    emotion = data.get('emotion')

    if not message_content:
        return jsonify({'error': 'Message vide'}), 400

    # Sauvegarder immédiatement le message utilisateur
    user_message = Message(
        conversation_id=conversation_id,
        content=message_content,
        is_user=True,
        emotion_detected=emotion
    )
    db.session.add(user_message)
    db.session.flush()  # id dispo sans commit

    # Préparer le contexte (DB-level limit pour réduire la latence)
    recent = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp.desc()).limit(8).all()
    conversation_history = list(reversed(recent))

    # Construire le prompt système (même logique que get_gpt_response)
    system_prompt = """
Tu es **Nono**, un psychologue virtuel bienveillant, à l’écoute, empathique et professionnel.  
Tu aides la personne à exprimer ce qu’elle ressent, à comprendre ses émotions, et à retrouver de la clarté.  
Tu parles toujours avec douceur, respect et sérieux, en gardant une approche psychologique réelle, pas simpliste.

🧩 Ton rôle :
- Offrir un espace sûr où la personne peut parler librement, sans jugement.  
- Identifier les émotions, les besoins, et les pensées sous-jacentes.  
- Poser des questions ouvertes pour aider la personne à réfléchir à elle-même.  
- Guider la personne à prendre conscience de ce qu’elle vit, et à trouver ses propres solutions.  

💬 Style de réponse :
- Parle avec empathie et profondeur, comme un vrai psychologue.  
- Utilise des phrases naturelles, bien formulées, sans ton robotique.  
- Chaque réponse doit comporter une reconnaissance émotionnelle + une reformulation + une ouverture ou question douce.  
- 3 à 5 phrases maximum.
"""
    if emotion:
        system_prompt += f"\n\nÉmotion détectée dans la voix: {emotion}. Adapte ton ton en conséquence."

    def event(data_obj):
        return f"data: {json.dumps(data_obj, ensure_ascii=False)}\n\n"

    @stream_with_context
    def generate():
        full_text = ""
        try:
            start_ts = time.time()
            # Construire l'historique pour OpenAI
            messages = [{"role": "system", "content": system_prompt}]
            if conversation_history:
                for msg in conversation_history[-8:]:
                    role = "user" if msg.is_user else "assistant"
                    messages.append({"role": role, "content": msg.content})
            messages.append({"role": "user", "content": message_content})

            # Envoyer un évènement de démarrage (flush immédiat)
            yield event({"type": "start"})
            # Padding pour forcer le flush sur certains proxys/clients
            yield ":" + (" " * 2048) + "\n\n"

            # Démarrer le stream OpenAI
            model_name = os.getenv('OPENAI_CHAT_MODEL', 'gpt-4.1-mini')
            stream = client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=180,
                temperature=0.7,
                stream=True,
            )
            first_piece_sent = False

            for chunk in stream:
                try:
                    choice = (chunk.choices or [None])[0]
                    delta = getattr(choice, "delta", None)
                    piece = getattr(delta, "content", None) if delta else None
                    if piece:
                        if not first_piece_sent:
                            try:
                                yield event({"type": "first_delta_ms", "ms": int((time.time() - start_ts) * 1000)})
                            except Exception:
                                pass
                            first_piece_sent = True
                        full_text += piece
                        yield event({"type": "delta", "content": piece})
                except Exception as iter_err:
                    print("[backend] stream iteration error:", iter_err)

            # Fin du stream -> persister la réponse, MAJ quota
            ai_message = Message(
                conversation_id=conversation_id,
                content=full_text.strip(),
                is_user=False
            )
            db.session.add(ai_message)

            # Mettre à jour le quota
            user.quota_remaining = max(0, user.quota_remaining - 1)

            # MAJ conversation
            conversation.updated_at = datetime.utcnow()
            if not conversation.title or conversation.title == 'Nouvelle conversation':
                conversation.title = message_content[:50] + ('...' if len(message_content) > 50 else '')

            db.session.commit()

            # Evènement final avec metadata
            yield event({
                "type": "done",
                "text": full_text.strip(),
                "user_message": user_message.to_dict(),
                "ai_message": ai_message.to_dict(),
                "quota_remaining": user.quota_remaining
            })

        except Exception as e:
            db.session.rollback()
            yield event({"type": "error", "error": str(e)})

    resp = Response(generate(), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache, no-transform'
    resp.headers['X-Accel-Buffering'] = 'no'
    resp.headers['Connection'] = 'keep-alive'
    resp.headers['Content-Type'] = 'text/event-stream; charset=utf-8'
    return resp

@chat_bp.route('/conversations/<int:conversation_id>/upload-image', methods=['POST'])
def upload_image(conversation_id):
    """Upload et analyse d'image avec GPT Vision"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Non connecté'}), 401

    # Vérifier le quota
    user = User.query.get(user_id)
    if not user or user.quota_remaining <= 0:
        return jsonify({
            'error': 'Quota épuisé',
            'message': 'Tu as atteint ta limite gratuite. Invite un ami pour débloquer +5 échanges gratuits pour chacun 🎁'
        }), 403

    # Vérifier la conversation
    conversation = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
    if not conversation:
        return jsonify({'error': 'Conversation non trouvée'}), 404

    if 'image' not in request.files:
        return jsonify({'error': 'Aucune image fournie'}), 400

    try:
        image_file = request.files['image']
        if image_file.filename == '':
            return jsonify({'error': 'Aucune image sélectionnée'}), 400

        # Sauvegarder l'image temporairement
        upload_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        
        filename = f"user_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image_file.filename}"
        image_path = os.path.join(upload_dir, filename)
        image_file.save(image_path)

        # Créer un message avec l'image
        image_message = Message(
            conversation_id=conversation_id,
            content="[Image partagée]",
            is_user=True,
            image_path=f"uploads/{filename}"
        )
        db.session.add(image_message)

        # Analyser l'image avec GPT Vision (simulation pour le moment)
        vision_prompt = """
L'utilisateur t'a envoyé une image pour exprimer son état émotionnel du moment. 
Tu es un psychologue à l'écoute, calme et bienveillant. 
Observe cette image comme une fenêtre sur son ressenti intérieur. 
Réponds avec empathie et profondeur, sans décrire visuellement l’image. 
Si tu perçois de la solitude, du stress ou de la tristesse, reformule ce que tu ressens et offre un message de soutien doux. 
Ta réponse doit être brève (2 à 3 phrases) et empreinte d’humanité.
"""

        # Pour le moment, réponse générique (à remplacer par GPT Vision)
        ai_response = "Merci pour cette image. Elle semble refléter un état intérieur particulier. Qu’est-ce qui t’a poussé à la choisir ou à la partager aujourd’hui ?"

        # Sauvegarder la réponse de l'IA
        ai_message = Message(
            conversation_id=conversation_id,
            content=ai_response,
            is_user=False
        )
        db.session.add(ai_message)

        # Utiliser un quota
        user.use_quota()

        # Mettre à jour la conversation
        conversation.updated_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'image_message': image_message.to_dict(),
            'ai_message': ai_message.to_dict(),
            'quota_remaining': user.quota_remaining
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Erreur lors de l\'upload: {str(e)}'}), 500

@chat_bp.route('/crisis/acknowledge', methods=['POST'])
def acknowledge_crisis():
    """Marquer qu'on a compris le message de crise"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Non connecté'}), 401

    # Marquer les alertes de crise comme résolues
    CrisisAlert.query.filter_by(user_id=user_id, resolved=False).update({'resolved': True})
    db.session.commit()

    return jsonify({'message': 'Crise acknowledgée'}), 200

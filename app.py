# app.py (Versión Gemini - Corregida y Definitiva)
import os
import google.generativeai as genai
from flask import Flask, request, jsonify

app = Flask(__name__)

# La clave de Gemini se leerá de las variables de entorno de Vercel.
try:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ADVERTENCIA: La variable de entorno GEMINI_API_KEY no está configurada.")
    else:
        genai.configure(api_key=api_key)
except Exception as e:
    print(f"Error al configurar el cliente de Gemini: {e}")

@app.route('/chat', methods=['POST'])
def chat_proxy():
    if not getattr(genai, 'API_KEY', None):
        return jsonify({'error': 'El servidor no tiene una clave de Gemini configurada'}), 500
    
    try:
        data = request.get_json()
        if not data or 'messages' not in data:
            return jsonify({'error': 'No se proporcionó un historial de mensajes'}), 400

        model = genai.GenerativeModel('gemini-pro')
        
        # --- CORRECCIÓN CRÍTICA: Transformar el historial al formato que espera Gemini ---
        gemini_history = []
        for msg in data['messages']:
            # Ignoramos el mensaje de sistema, Gemini Pro lo gestiona de otra forma
            if msg.get('role') in ['user', 'model']:
                gemini_history.append({
                    'role': msg['role'],
                    'parts': [{'text': msg.get('content', '')}] # Convertir 'content' a 'parts'
                })
        
        # Si el historial está vacío (solo tenía un mensaje de sistema), no hacer la llamada
        if not gemini_history:
             return jsonify({'text': "Hola, soy tu asistente de salud. ¿En qué puedo ayudarte?"})

        # Llamada segura a Gemini desde nuestro servidor
        response = model.generate_content(gemini_history)
        
        # Devolvemos una respuesta JSON simple a la app Kivy
        return jsonify({'text': response.text})

    except Exception as e:
        print(f"Error inesperado en el proxy de Gemini: {e}")
        return jsonify({'error': f'Ha ocurrido un error interno en el servidor: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def home():
    return "Servidor del Asistente de Salud PRO (Gemini Edition) funcionando.", 200
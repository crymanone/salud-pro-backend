# app.py (Versión Gemini)
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
    if not genai.API_KEY:
        return jsonify({'error': 'El servidor no tiene una clave de Gemini configurada'}), 500
    
    try:
        data = request.get_json()
        if not data or 'messages' not in data:
            return jsonify({'error': 'No se proporcionó un historial de mensajes'}), 400

        # Preparamos el modelo
        model = genai.GenerativeModel('gemini-pro')
        
        # Adaptamos el historial para Gemini (omitiendo el 'system' prompt si no tiene contenido relevante)
        # Gemini prefiere una alternancia estricta de 'user' y 'model'
        gemini_history = [
            msg for msg in data['messages'] if msg['role'] in ['user', 'model']
        ]

        # Llamada segura a Gemini desde nuestro servidor
        response = model.generate_content(gemini_history)
        
        # Devolvemos una respuesta JSON simple a la app Kivy
        return jsonify({'text': response.text})

    except Exception as e:
        print(f"Error inesperado en el proxy de Gemini: {e}")
        # Devuelve un mensaje de error más detallado a la app
        return jsonify({'error': f'Ha ocurrido un error interno en el servidor: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def home():
    return "Servidor del Asistente de Salud PRO (Gemini Edition) funcionando.", 200
# app.py (Versión Final Definitiva - Corregido el nombre del modelo)
import os
import google.generativeai as genai
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/chat', methods=['POST'])
def chat_proxy():
    try:
        # Mover la configuración y la inicialización DENTRO de la función
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return jsonify({'error': 'La variable de entorno GEMINI_API_KEY no está configurada en el servidor.'}), 500
        
        genai.configure(api_key=api_key)
        
        # --- CORRECCIÓN FINAL: Usar el nombre de modelo estable y correcto ---
        model = genai.GenerativeModel('gemini-1.0-pro')
        # ----------------------------------------------------------------------
        
        data = request.get_json()
        if not data or 'messages' not in data:
            return jsonify({'error': 'La petición no contenía un historial de mensajes válido.'}), 400

        # Transformar el historial al formato que espera Gemini
        gemini_history = []
        for msg in data['messages']:
            if msg.get('role') in ['user', 'model']:
                gemini_history.append({
                    'role': msg['role'],
                    'parts': [{'text': msg.get('content', '')}]
                })
        
        if not gemini_history:
             return jsonify({'text': "Hola, soy tu asistente de salud. ¿En qué puedo ayudarte?"})

        # Llamada a Gemini
        response = model.generate_content(gemini_history)
        
        return jsonify({'text': response.text})

    except Exception as e:
        print(f"ERROR DETALLADO EN EL SERVIDOR: {e}") 
        return jsonify({'error': f'Ha ocurrido un error interno en el servidor: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def home():
    return "Servidor del Asistente de Salud PRO (Gemini Edition) funcionando.", 200
# app.py (Versión Final Definitiva - Tipos de datos corregidos)
import os
import google.generativeai as genai
from flask import Flask, request, jsonify
from google.generativeai.types import HarmCategory, HarmBlockThreshold

app = Flask(__name__)

# --- Definición de la herramienta que la IA puede usar ---
add_medication_tool = {
    "name": "add_medication",
    "description": "Añade un nuevo medicamento a la lista de tratamientos del usuario.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "nombre": {"type": "STRING", "description": "El nombre del medicamento. Por ejemplo: Ibuprofeno"},
            "dosis": {"type": "STRING", "description": "La dosis a tomar. Por ejemplo: 1 pastilla, 10 ml"},
            "frecuencia_horas": {"type": "INTEGER", "description": "El intervalo en horas entre cada toma. Por ejemplo: 8"},
            "duracion_dias": {"type": "INTEGER", "description": "El número total de días que dura el tratamiento. Por ejemplo: 7"},
        },
        "required": ["nombre", "dosis", "frecuencia_horas", "duracion_dias"],
    },
}

@app.route('/chat', methods=['POST'])
def chat_proxy():
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return jsonify({'error': 'La variable de entorno GEMINI_API_KEY no está configurada.'}), 500
        
        genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel(
            model_name='gemini-1.5-pro-latest',
            tools=[add_medication_tool]
        )
        
        data = request.get_json()
        if not data or 'messages' not in data:
            return jsonify({'error': 'Petición inválida.'}), 400

        gemini_history = []
        for msg in data['messages']:
            if msg.get('role') in ['user', 'model']:
                gemini_history.append({
                    'role': msg['role'],
                    'parts': [{'text': msg.get('content', '')}]
                })
        
        if not gemini_history:
             return jsonify({'text': "Hola, ¿en qué puedo ayudarte hoy?"})

        chat = model.start_chat(history=gemini_history)
        response = chat.send_message(
            gemini_history[-1]['parts'],
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )

        if response.candidates[0].content.parts[0].function_call:
            function_call = response.candidates[0].content.parts[0].function_call
            if function_call.name == "add_medication":
                args = {key: value for key, value in function_call.args.items()}
                
                # --- CORRECCIÓN DE TIPO DE DATOS: Aseguramos que sean enteros ---
                try:
                    if 'frecuencia_horas' in args:
                        args['frecuencia_horas'] = int(float(args['frecuencia_horas']))
                    if 'duracion_dias' in args:
                        args['duracion_dias'] = int(float(args['duracion_dias']))
                except (ValueError, TypeError):
                    return jsonify({'text': "He entendido que quieres añadir un medicamento, pero los valores de frecuencia o duración no son números válidos. ¿Podrías repetirlo?"})

                return jsonify({
                    "action": "add_medication",
                    "params": args
                })
        
        return jsonify({'text': response.text})

    except Exception as e:
        print(f"ERROR DETALLADO EN EL SERVIDOR: {e}") 
        return jsonify({'error': f'Error interno en el servidor: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def home():
    return "Servidor del Asistente de Salud PRO (Gemini Edition v3 - Tools & Type Fix) funcionando.", 200
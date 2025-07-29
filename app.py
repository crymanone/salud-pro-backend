# app.py (Versión de Producción Final con Herramientas Completas)
import os
import google.generativeai as genai
from flask import Flask, request, jsonify
from google.generativeai.types import HarmCategory, HarmBlockThreshold

app = Flask(__name__)

# --- DEFINICIÓN DE LAS HERRAMIENTAS QUE LA IA PUEDE USAR ---

add_medication_tool = {
    "name": "add_medication",
    "description": "Añade un nuevo medicamento a la lista de tratamientos del usuario. Extrae todos los detalles de la frase del usuario.",
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

delete_medication_tool = {
    "name": "delete_medication",
    "description": "Elimina un medicamento de la lista activa del usuario. Útil para comandos como 'quita el paracetamol' o 'borra la aspirina'.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "nombre": {"type": "STRING", "description": "El nombre del medicamento que se debe eliminar."},
        },
        "required": ["nombre"],
    },
}

query_medication_tool = {
    "name": "query_medication_info",
    "description": "Consulta información sobre un medicamento específico. Útil para preguntas como 'cuánto paracetamol queda' o 'cuándo empecé a tomar la aspirina'.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "nombre": {"type": "STRING", "description": "El nombre del medicamento sobre el que se pregunta."},
        },
        "required": ["nombre"],
    },
}


@app.route('/chat', methods=['POST'])
def chat_proxy():
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return jsonify({'error': 'La variable de entorno GEMINI_API_KEY no está configurada.'}), 500
        
        genai.configure(api_key=api_key)
        
        # Le decimos al modelo que tiene un conjunto de herramientas disponibles
        model = genai.GenerativeModel(
            model_name='gemini-1.5-pro-latest',
            tools=[add_medication_tool, delete_medication_tool, query_medication_tool]
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

        # Comprobamos si la IA decidió usar una herramienta
        if response.candidates[0].content.parts[0].function_call:
            function_call = response.candidates[0].content.parts[0].function_call
            args = {key: value for key, value in function_call.args.items()}
            
            # Forzar conversión a entero de los campos numéricos
            if 'frecuencia_horas' in args:
                args['frecuencia_horas'] = int(float(args['frecuencia_horas']))
            if 'duracion_dias' in args:
                args['duracion_dias'] = int(float(args['duracion_dias']))

            # Devolvemos la orden a la app Kivy
            return jsonify({
                "action": function_call.name,
                "params": args
            })
        
        # Si no usó una herramienta, devolvemos la respuesta de texto normal
        return jsonify({'text': response.text})

    except Exception as e:
        print(f"ERROR DETALLADO EN EL SERVIDOR: {e}") 
        return jsonify({'error': f'Error interno en el servidor: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def home():
    return "Servidor del Asistente de Salud PRO (v4 - Herramientas Completas) funcionando.", 200
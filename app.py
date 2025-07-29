# app.py (Versión de Producción Final - Asistente con Herramientas Completas y Conversacional)
import os
import google.generativeai as genai
from flask import Flask, request, jsonify
from google.generativeai.types import HarmCategory, HarmBlockThreshold

app = Flask(__name__)

# --- DEFINICIÓN DE LAS HERRAMIENTAS AMPLIADAS ---

add_medication_tool = {
    "name": "add_medication",
    "description": "Añade un nuevo medicamento a la lista de tratamientos del usuario. Extrae todos los detalles de la frase del usuario, incluyendo opcionalmente la cantidad total y la fecha de caducidad.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "nombre": {"type": "STRING", "description": "El nombre del medicamento. Por ejemplo: Ibuprofeno"},
            "dosis": {"type": "STRING", "description": "La dosis a tomar. Por ejemplo: 1 pastilla, 10 ml"},
            "frecuencia_horas": {"type": "INTEGER", "description": "El intervalo en horas entre cada toma. Por ejemplo: 8"},
            "duracion_dias": {"type": "INTEGER", "description": "El número total de días que dura el tratamiento. Por ejemplo: 7"},
            "cantidad_total": {"type": "INTEGER", "description": "Opcional. El número total de unidades en la caja."},
            "fecha_caducidad": {"type": "STRING", "description": "Opcional. La fecha de caducidad en formato AAAA-MM-DD."},
        },
        "required": ["nombre", "dosis", "frecuencia_horas", "duracion_dias"],
    },
}

update_contact_info_tool = {
    "name": "update_contact_info",
    "description": "Actualiza la información de contacto de emergencia del usuario, como el nombre del médico o el teléfono del centro de salud.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "nombre_medico": {"type": "STRING", "description": "Opcional. El nombre del médico a guardar."},
            "telefono_centro_salud": {"type": "STRING", "description": "Opcional. El número de teléfono del centro de salud."},
        },
    },
}

permanently_delete_medication_tool = {
    "name": "permanently_delete_medication",
    "description": "Elimina un medicamento para siempre de la papelera. Solo se debe usar si el usuario pide explícitamente borrarlo 'permanentemente' o 'para siempre'.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "nombre": {"type": "STRING", "description": "El nombre del medicamento a eliminar de la papelera."},
        },
        "required": ["nombre"],
    },
}


query_medication_tool = {
    "name": "query_medication_info",
    "description": "Consulta información sobre un medicamento específico que el usuario tiene en su lista activa.",
    "parameters": {
        "type": "OBJECT", "properties": {"nombre": {"type": "STRING"}}, "required": ["nombre"],
    },
}

# --- Instrucciones del Sistema (Personalidad Final de la IA) ---
SYSTEM_INSTRUCTIONS = """
Eres 'Asistente de Salud', una IA conversacional dentro de la aplicación 'Gestor de Salud PRO'. 
Tu propósito principal es ser un asistente amigable y útil para el usuario. Tienes dos modos de operar:

1.  **Modo Asistente de Acciones:** Si la petición del usuario encaja con una de tus herramientas (`add_medication`, `update_contact_info`, `permanently_delete_medication`, `query_medication_info`), tu prioridad es usar la herramienta. Si te falta información para una herramienta, pídela de forma clara y concisa.

2.  **Modo Conversacional:** Si la petición del usuario no es una acción, puedes tener una conversación normal y amigable sobre cualquier tema de interés general.

**REGLA DE ORO INQUEBRANTABLE:** Bajo ninguna circunstancia puedes dar consejos médicos. Si un usuario te pregunta algo relacionado con su salud, debes negarte educadamente y responder siempre con una variación de: 'No soy un profesional médico y no puedo dar consejos de salud. Por favor, consulta siempre a tu médico o farmacéutico para ese tipo de preguntas'.
"""

@app.route('/chat', methods=['POST'])
def chat_proxy():
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key: return jsonify({'error': 'La variable de entorno GEMINI_API_KEY no está configurada.'}), 500
        
        genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel(
            model_name='gemini-1.5-pro-latest',
            tools=[add_medication_tool, update_contact_info_tool, permanently_delete_medication_tool, query_medication_tool],
            system_instruction=SYSTEM_INSTRUCTIONS
        )
        
        data = request.get_json()
        if not data or 'messages' not in data: return jsonify({'error': 'Petición inválida.'}), 400

        gemini_history = [{"role": msg['role'], 'parts': [{'text': msg.get('content', '')}]} for msg in data['messages'] if msg.get('role') in ['user', 'model']]
        if not gemini_history: return jsonify({'text': "Hola, ¿en qué puedo ayudarte hoy?"})

        response = model.generate_content(gemini_history)
        
        if response.candidates and response.candidates[0].content.parts and response.candidates[0].content.parts[0].function_call:
            function_call = response.candidates[0].content.parts[0].function_call
            args = {key: value for key, value in function_call.args.items()}
            
            # Limpieza y conversión de tipos
            for key in ['frecuencia_horas', 'duracion_dias', 'cantidad_total']:
                if key in args:
                    try: args[key] = int(float(args[key]))
                    except (ValueError, TypeError): pass
            
            return jsonify({"action": function_call.name, "params": args})
        
        return jsonify({'text': response.text})

    except Exception as e:
        print(f"ERROR DETALLADO EN EL SERVIDOR: {e}") 
        return jsonify({'error': f'Error interno en el servidor: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def home():
    return "Servidor del Asistente de Salud PRO (v-final - Herramientas Completas) funcionando.", 200
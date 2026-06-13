# app.py (Versión limpia con el NUEVO SDK google.genai)

import os
import json
import re
from datetime import datetime, timedelta
import calendar

# --- NUEVAS IMPORTACIONES DE GOOGLE GENAI ---
from google import genai
from google.genai import types

from flask import Flask, request, jsonify

app = Flask(__name__)

# --- PARSER DE FECHAS ---
MESES = {'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12}
NUMEROS_PALABRA = {'un': '1', 'una': '1', 'dos': '2', 'tres': '3', 'cuatro': '4', 'cinco': '5', 'seis': '6', 'siete': '7', 'ocho': '8', 'nueve': '9', 'diez': '10', 'once': '11', 'doce': '12'}

def texto_a_numero(texto: str) -> str:
    for palabra, digito in NUMEROS_PALABRA.items():
        texto = texto.replace(palabra, digito)
    return texto

def parsear_fecha_hora(texto: str) -> datetime or None:
    texto_norm = texto_a_numero(texto.lower())
    now = datetime.now()
    hora, minuto = None, 0
    match_hora = re.search(r'(\d{1,2})\s*[:y]\s*(\d{2})', texto_norm)
    if match_hora: hora, minuto = int(match_hora.group(1)), int(match_hora.group(2))
    else:
        match_hora_simple = re.search(r'(a la|a las|las)\s+(\d{1,2})', texto_norm)
        if match_hora_simple: hora = int(match_hora_simple.group(2))
        if 'y media' in texto_norm: minuto = 30
    if hora is None: return None
    if any(s in texto_norm for s in ['tarde', 'noche', 'pm']) and hora < 12: hora += 12
    if 'de la mañana' in texto_norm and hora == 12: hora = 0
    fecha_base = None
    match_fecha_esp = re.search(r'(\d{1,2})\s+de\s+([a-zA-Záéíóúñ]+)', texto_norm)
    if match_fecha_esp:
        dia_str, mes_str = match_fecha_esp.groups()
        if mes_str in MESES:
            anio, mes, dia = now.year, MESES[mes_str], int(dia_str)
            try:
                if datetime(anio, mes, dia).date() < now.date(): anio += 1
                fecha_base = datetime(anio, mes, dia).date()
            except ValueError: return None
    if not fecha_base:
        if 'hoy' in texto_norm: fecha_base = now.date()
        elif 'mañana' in texto_norm: fecha_base = (now + timedelta(days=1)).date()
    if not fecha_base: return None
    try: return datetime(fecha_base.year, fecha_base.month, fecha_base.day, hora, minuto)
    except ValueError: return None

def format_datetime_espanol(dt_obj: datetime) -> str:
    dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    return f"el {dias[dt_obj.weekday()]} {dt_obj.day} de {meses[dt_obj.month - 1]} a las {dt_obj.strftime('%H:%M')}"

# --- DEFINICIÓN DE LAS HERRAMIENTAS (NUEVO FORMATO SDK) ---
add_medication_decl = types.FunctionDeclaration(
    name="add_medication",
    description="Añade un nuevo medicamento.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "nombre": {"type": "STRING"},
            "dosis": {"type": "STRING"},
            "frecuencia_horas": {"type": "INTEGER"},
            "duracion_dias": {"type": "INTEGER"}
        },
        "required": ["nombre", "dosis", "frecuencia_horas", "duracion_dias"]
    }
)

update_contact_info_decl = types.FunctionDeclaration(
    name="update_contact_info",
    description="Actualiza la información de contacto.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "nombre_medico": {"type": "STRING"},
            "telefono_centro_salud": {"type": "STRING"}
        }
    }
)

schedule_appointment_decl = types.FunctionDeclaration(
    name="schedule_appointment",
    description="Interpreta el texto de una fecha y hora dadas por el usuario para agendar una cita.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "fecha_texto": {"type": "STRING", "description": "El texto exacto que el usuario dijo sobre la fecha y hora. Ej: 'el siete de octubre a las 10:30 de la mañana'"}
        },
        "required": ["fecha_texto"]
    }
)

# Empaquetamos las declaraciones en una Tool de GenAI
herramientas = [types.Tool(function_declarations=[add_medication_decl, update_contact_info_decl, schedule_appointment_decl])]

# --- SYSTEM PROMPT ---
SYSTEM_INSTRUCTIONS = """
Eres 'Asistente de Salud PRO'. Tu propósito es ayudar al usuario a gestionar su salud usando tus herramientas. Eres empático y seguro.

**REGLA MAESTRA PARA CONVERSACIÓN (VOZ):**
El usuario te está escuchando a través de un sintetizador de voz (Text-To-Speech). 
- NUNCA uses formato Markdown.
- ESTÁN PROHIBIDOS los asteriscos (*) para hacer negritas o viñetas.
- ESTÁN PROHIBIDAS las almohadillas (#) u otros símbolos extraños.
- Redacta tus respuestas siempre en TEXTO PLANO y fluido, como si estuvieras hablando con alguien por teléfono, usando comas y puntos para las pausas naturales.

**REGLAS DE FLUJO:**
- Si estás agendando una cita y el usuario te da una fecha, **usa la herramienta `schedule_appointment`**.
- Si el usuario quiere añadir un medicamento, **usa `add_medication`**.
- Si el usuario habla de un centro de salud, **usa `update_contact_info`**.
- **EXCEPCIÓN CRÍTICA:** Si estás en medio de agendar una cita y el usuario te da un lugar como respuesta a "¿dónde será la cita?", NO uses ninguna herramienta. Espera la confirmación.

**REGLA DE SEGURIDAD:** Si el usuario te hace una pregunta sobre síntomas, salud o medicamentos que no encaja en ninguna herramienta, niégate educadamente y recomienda SIEMPRE consultar a un médico. Solo puedes dar consejos de bienestar muy genéricos (descansar, beber agua) para síntomas muy leves.
"""

# --- AJUSTES DE SEGURIDAD (NUEVO FORMATO SDK) ---
SAFETY_SETTINGS = [
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
]

@app.route('/chat', methods=['POST'])
def chat_proxy():
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key: return jsonify({'error': 'API key no configurada.'}), 500
        
        # --- INICIALIZACIÓN DEL NUEVO CLIENTE ---
        client = genai.Client(api_key=api_key)
        
        data = request.get_json()
        gemini_history = []
        
        for msg in data.get('messages', []):
            role = msg['role']
            text_content = msg.get('content', '')
            gemini_history.append(
                types.Content(role=role, parts=[types.Part.from_text(text=text_content)])
            )
            
        if not gemini_history: return jsonify({'text': "Hola, ¿en qué puedo ayudarte hoy?"})

        # --- CONFIGURACIÓN DEL MODELO ---
        config = types.GenerateContentConfig(
            tools=herramientas,
            system_instruction=SYSTEM_INSTRUCTIONS,
            safety_settings=SAFETY_SETTINGS,
            temperature=0.5
        )

        # --- GENERAR RESPUESTA ---
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=gemini_history,
            config=config
        )
        
        # --- LÓGICA DE RESPUESTA ---
        if response.function_calls:
            function_call = response.function_calls[0]
            action_name = function_call.name
            args = function_call.args if function_call.args else {}
            
            if action_name == "schedule_appointment":
                fecha_texto = args.get("fecha_texto", "")
                parsed_datetime = parsear_fecha_hora(fecha_texto)
                if parsed_datetime:
                    return jsonify({
                        "action": "confirm_appointment",
                        "params": { 
                            "parsed_datetime": parsed_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                            "confirmation_string": f"Entendido, he anotado la fecha: {format_datetime_espanol(parsed_datetime)}. Ahora, ¿dónde será la cita?"
                        }
                    })
                else:
                    return jsonify({"text": "No he podido entender esa fecha y hora. Por favor, dímela de nuevo."})
            else:
                return jsonify({"action": action_name, "params": args})

        response_text = response.text if response.text else ""
        response_text = response_text.strip()
        response_json = None
        
        if response_text.startswith('{') and response_text.endswith('}'):
            try: response_json = json.loads(response_text)
            except json.JSONDecodeError: pass
        if response_json is None:
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                try: response_json = json.loads(match.group(0))
                except json.JSONDecodeError: pass
        
        if response_json and response_json.get("action") == "schedule_appointment":
            fecha_texto = response_json.get("params", {}).get("fecha_texto", "")
            parsed_datetime = parsear_fecha_hora(fecha_texto)
            if parsed_datetime:
                return jsonify({ "action": "confirm_appointment", "params": { "parsed_datetime": parsed_datetime.strftime("%Y-%m-%d %H:%M:%S"), "confirmation_string": f"Entendido, he anotado la fecha: {format_datetime_espanol(parsed_datetime)}. Ahora, ¿dónde será la cita?" }})
            else:
                return jsonify({"text": "No he podido entender esa fecha y hora. Por favor, dímela de nuevo."})
        
        return jsonify({'text': response_text})

    except Exception as e:
        print(f"ERROR DETALLADO EN EL SERVIDOR: {e}") 
        return jsonify({'error': f'Error interno en el servidor: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def home():
    return "Servidor del Asistente de Salud PRO funcionando con la nueva API GenAI.", 200
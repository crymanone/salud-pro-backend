# app.py (Versión final, robusta y con ajustes de seguridad)

import os
import json
import re
from datetime import datetime, timedelta
import calendar
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- PARSER DE FECHAS ---
MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
    'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11,
    'diciembre': 12
}
DIAS_SEMANA = {
    'lunes': 0, 'martes': 1, 'miércoles': 2, 'jueves': 3, 'viernes': 4,
    'sábado': 5, 'domingo': 6
}

def parsear_fecha_hora(texto: str) -> datetime or None:
    # (Esta función es correcta, la mantenemos)
    texto_norm = texto.lower()
    now = datetime.now()
    hora, minuto = None, 0
    match_hora = re.search(r'(\d{1,2})\s*[:y]\s*(\d{2})', texto_norm)
    if match_hora:
        hora, minuto = int(match_hora.group(1)), int(match_hora.group(2))
    else:
        match_hora_simple = re.search(r'(a la|a las|las)\s+(\d{1,2})', texto_norm)
        if match_hora_simple:
            hora = int(match_hora_simple.group(2))
        if 'y media' in texto_norm: minuto = 30
    if hora is None: return None
    if any(s in texto_norm for s in ['tarde', 'noche', 'pm']) and hora < 12: hora += 12
    fecha_base = None
    match_fecha_esp = re.search(r'(\d{1,2})\s+de\s+([a-zA-Záéíóúñ]+)', texto_norm)
    if match_fecha_esp:
        dia_str, mes_str = match_fecha_esp.groups()
        if mes_str in MESES:
            anio = now.year
            mes = MESES[mes_str]
            dia = int(dia_str)
            try:
                fecha_candidata = datetime(anio, mes, dia).date()
                if fecha_candidata < now.date(): anio += 1
                fecha_base = datetime(anio, mes, dia).date()
            except ValueError: return None
    if not fecha_base:
        if 'hoy' in texto_norm: fecha_base = now.date()
        elif 'mañana' in texto_norm: fecha_base = (now + timedelta(days=1)).date()
    if not fecha_base: return None
    try:
        return datetime(fecha_base.year, fecha_base.month, fecha_base.day, hora, minuto)
    except ValueError:
        return None

def format_datetime_espanol(dt_obj: datetime) -> str:
    dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    return f"el {dias[dt_obj.weekday()]} {dt_obj.day} de {meses[dt_obj.month - 1]} a las {dt_obj.strftime('%H:%M')}"

# --- HERRAMIENTAS Y SYSTEM PROMPT (Sin cambios) ---
add_medication_tool = { "name": "add_medication", "description": "Añade un nuevo medicamento.", "parameters": { "type": "OBJECT", "properties": { "nombre": {"type": "STRING"}, "dosis": {"type": "STRING"}, "frecuencia_horas": {"type": "INTEGER"}, "duracion_dias": {"type": "INTEGER"}}, "required": ["nombre", "dosis", "frecuencia_horas", "duracion_dias"]}}
update_contact_info_tool = { "name": "update_contact_info", "description": "Actualiza la información de contacto.", "parameters": { "type": "OBJECT", "properties": { "nombre_medico": {"type": "STRING"}, "telefono_centro_salud": {"type": "STRING"}}}}
permanently_delete_medication_tool = { "name": "permanently_delete_medication", "description": "Elimina un medicamento para siempre.", "parameters": { "type": "OBJECT", "properties": { "nombre": {"type": "STRING"}}, "required": ["nombre"]}}
query_medication_tool = { "name": "query_medication_info", "description": "Consulta información sobre un medicamento.", "parameters": { "type": "OBJECT", "properties": {"nombre": {"type": "STRING"}}, "required": ["nombre"]}}

SYSTEM_INSTRUCTIONS = """
Eres 'Asistente de Salud', una IA conversacional empática y segura. Tus modos de operar son:
1. Modo de Herramientas: Si el usuario pide una acción concreta (añadir medicamento, contacto, etc.), usa las herramientas formales. Si te falta información, pídela.
2. Modo de Agendar Citas: Cuando el usuario está agendando una cita y te da una fecha y hora en lenguaje natural (ej: "el 3 de septiembre a las 9 y media"), tu ÚNICA RESPUESTA debe ser un JSON con el formato: `{"action": "schedule_appointment", "params": {"fecha_texto": "el texto original que dijo el usuario"}}`. NO confirmes la fecha, solo pasa el texto.
3. Modo de Consejo de Bienestar: Para síntomas leves, da consejos seguros (descansar, hidratarse) y SIEMPRE termina recomendando consultar a un médico si los síntomas persisten.
4. Modo de Derivación (REGLA DE ORO): Para CUALQUIER otra pregunta de salud (síntomas graves, medicamentos, diagnósticos), niégate educadamente y recomienda SIEMPRE consultar a un médico o farmacéutico.
"""

# --- AJUSTES DE SEGURIDAD PARA LA API ---
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
}

@app.route('/chat', methods=['POST'])
def chat_proxy():
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key: return jsonify({'error': 'La variable de entorno GEMINI_API_KEY no está configurada.'}), 500
        
        genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            tools=[add_medication_tool, update_contact_info_tool, permanently_delete_medication_tool, query_medication_tool],
            system_instruction=SYSTEM_INSTRUCTIONS,
            safety_settings=SAFETY_SETTINGS  # <-- ¡AQUÍ ESTÁ LA LÍNEA MÁGICA!
        )
        
        data = request.get_json()
        gemini_history = [{"role": msg['role'], 'parts': [{'text': msg.get('content', '')}]} for msg in data['messages']]
        if not gemini_history: return jsonify({'text': "Hola, ¿en qué puedo ayudarte hoy?"})

        response = model.generate_content(gemini_history, request_options={"timeout": 100})
        
        # --- LÓGICA DE RESPUESTA (Sin cambios, ya es robusta) ---
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts and response.candidates[0].content.parts[0].function_call:
            function_call = response.candidates[0].content.parts[0].function_call
            args = {key: value for key, value in function_call.args.items()}
            return jsonify({"action": function_call.name, "params": args})

        response_text = response.text
        match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if match:
            json_str = match.group(1)
            try:
                response_json = json.loads(json_str)
                if response_json.get("action") == "schedule_appointment":
                    fecha_texto = response_json.get("params", {}).get("fecha_texto", "")
                    parsed_datetime = parsear_fecha_hora(fecha_texto)
                    if parsed_datetime:
                        return jsonify({
                            "action": "confirm_appointment",
                            "params": { "parsed_datetime": parsed_datetime.strftime("%Y-%m-%d %H:%M:%S"), "confirmation_string": f"Entendido, he anotado la fecha: {format_datetime_espanol(parsed_datetime)}. Ahora, ¿dónde será la cita?" }
                        })
                    else:
                        return jsonify({"text": "No he podido entender esa fecha y hora. Por favor, dímela de nuevo."})
            except json.JSONDecodeError:
                return jsonify({'text': response_text})

        return jsonify({'text': response_text})

    except Exception as e:
        print(f"ERROR DETALLADO EN EL SERVIDOR: {e}") 
        return jsonify({'error': f'Error interno en el servidor: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def home():
    return "Servidor del Asistente de Salud PRO funcionando.", 200
# app.py (Versión final, con 'schedule_appointment' como herramienta formal)

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

# --- DEFINICIÓN DE LAS HERRAMIENTAS ---
add_medication_tool = {"name": "add_medication", "description": "Añade un nuevo medicamento.", "parameters": { "type": "OBJECT", "properties": { "nombre": {"type": "STRING"}, "dosis": {"type": "STRING"}, "frecuencia_horas": {"type": "INTEGER"}, "duracion_dias": {"type": "INTEGER"}}, "required": ["nombre", "dosis", "frecuencia_horas", "duracion_dias"]}}
update_contact_info_tool = {"name": "update_contact_info", "description": "Actualiza la información de contacto.", "parameters": { "type": "OBJECT", "properties": { "nombre_medico": {"type": "STRING"}, "telefono_centro_salud": {"type": "STRING"}}}}
# --- ¡LA NUEVA HERRAMIENTA OFICIAL! ---
schedule_appointment_tool = {"name": "schedule_appointment", "description": "Interpreta el texto de una fecha y hora dadas por el usuario para agendar una cita.", "parameters": { "type": "OBJECT", "properties": {"fecha_texto": {"type": "STRING", "description": "El texto exacto que el usuario dijo sobre la fecha y hora. Ej: 'el siete de octubre a las 10:30 de la mañana'"}}, "required": ["fecha_texto"]}}

# --- SYSTEM PROMPT (Ahora es más simple y directo) ---
SYSTEM_INSTRUCTIONS = """
Eres 'Asistente de Salud PRO'. Tu propósito es ayudar al usuario a gestionar su salud usando tus herramientas. Eres empático y seguro.

**REGLA MAESTRA:** Cuando el usuario te dé una respuesta que encaje en el paso actual de una conversación, usa la herramienta apropiada.
- Si estás agendando una cita y el usuario te da una fecha, **usa la herramienta `schedule_appointment`**.
- Si el usuario quiere añadir un medicamento, **usa `add_medication`**.
- Si el usuario habla de un centro de salud, **usa `update_contact_info`**.
- **EXCEPCIÓN CRÍTICA:** Si estás en medio de agendar una cita y el usuario te da un lugar como respuesta a "¿dónde será la cita?", NO uses ninguna herramienta. Simplemente espera a la confirmación final.

**REGLA DE SEGURIDAD:** Si el usuario te hace una pregunta sobre síntomas, salud o medicamentos que no encaja en ninguna herramienta, niégate educadamente y recomienda SIEMPRE consultar a un médico. Solo puedes dar consejos de bienestar muy genéricos (descansar, beber agua) para síntomas muy leves (cansancio, dolor de cabeza leve).
"""

# --- AJUSTES DE SEGURIDAD ---
SAFETY_SETTINGS = {HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE, HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE, HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE, HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE}

@app.route('/chat', methods=['POST'])
def chat_proxy():
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key: return jsonify({'error': 'API key no configurada.'}), 500
        genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            # ¡AÑADIMOS LA NUEVA HERRAMIENTA A LA LISTA OFICIAL!
            tools=[add_medication_tool, update_contact_info_tool, schedule_appointment_tool],
            system_instruction=SYSTEM_INSTRUCTIONS,
            safety_settings=SAFETY_SETTINGS
        )
        
        data = request.get_json()
        gemini_history = [{"role": msg['role'], 'parts': [{'text': msg.get('content', '')}]} for msg in data['messages']]
        if not gemini_history: return jsonify({'text': "Hola, ¿en qué puedo ayudarte hoy?"})

        response = model.generate_content(gemini_history, request_options={"timeout": 100})
        
        # --- LÓGICA DE RESPUESTA FINAL Y UNIFICADA ---
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts and response.candidates[0].content.parts[0].function_call:
            function_call = response.candidates[0].content.parts[0].function_call
            action_name = function_call.name
            args = {key: value for key, value in function_call.args.items()}

            # SI LA IA LLAMA A NUESTRA NUEVA HERRAMIENTA, LA PROCESAMOS AQUÍ
            if action_name == "schedule_appointment":
                fecha_texto = args.get("fecha_texto", "")
                parsed_datetime = parsear_fecha_hora(fecha_texto)
                if parsed_datetime:
                    # Devolvemos el JSON que la app espera
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
                # Para el resto de herramientas, pasamos la acción a la app
                return jsonify({"action": action_name, "params": args})

        # Si no hay llamada a función, es texto normal
        return jsonify({'text': response.text})

    except Exception as e:
        print(f"ERROR DETALLADO EN EL SERVIDOR: {e}") 
        return jsonify({'error': f'Error interno en el servidor: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def home():
    return "Servidor del Asistente de Salud PRO funcionando.", 200
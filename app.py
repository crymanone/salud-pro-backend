# app.py (Versión final, completa, robusta y con todas las importaciones y funciones)

import os
import json
import re
from datetime import datetime, timedelta
import calendar
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- PARSER DE FECHAS (Toda la lógica de parseo vive ahora en el backend) ---
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
        elif 'pasado mañana' in texto_norm: fecha_base = (now + timedelta(days=2)).date()
        else:
             for dia_str, dia_num in DIAS_SEMANA.items():
                if dia_str in texto_norm:
                    dias_a_sumar = (dia_num - now.weekday() + 7) % 7
                    if dias_a_sumar == 0 and 'próximo' in texto_norm: dias_a_sumar = 7
                    fecha_base = (now + timedelta(days=dias_a_sumar)).date()
                    break
    if not fecha_base: fecha_base = now.date()
    try:
        fecha_final = datetime(fecha_base.year, fecha_base.month, fecha_base.day, hora, minuto)
        if fecha_final < now and not match_fecha_esp and 'hoy' not in texto_norm:
             if now.hour > hora or (now.hour == hora and now.minute > minuto):
                 fecha_final += timedelta(days=1)
        return fecha_final
    except ValueError:
        return None
        
def format_datetime_espanol(dt_obj: datetime) -> str:
    dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    return f"el {dias[dt_obj.weekday()]} {dt_obj.day} de {meses[dt_obj.month - 1]} a las {dt_obj.strftime('%H:%M')}"

# --- DEFINICIÓN DE LAS HERRAMIENTAS ---
add_medication_tool = {"name": "add_medication", "description": "Añade un nuevo medicamento a la lista de tratamientos del usuario. Extrae todos los detalles de la frase del usuario, incluyendo opcionalmente la cantidad total y la fecha de caducidad.", "parameters": {"type": "OBJECT", "properties": {"nombre": {"type": "STRING", "description": "El nombre del medicamento. Por ejemplo: Ibuprofeno"},"dosis": {"type": "STRING", "description": "La dosis a tomar. Por ejemplo: 1 pastilla, 10 ml"},"frecuencia_horas": {"type": "INTEGER", "description": "El intervalo en horas entre cada toma. Por ejemplo: 8"},"duracion_dias": {"type": "INTEGER", "description": "El número total de días que dura el tratamiento. Por ejemplo: 7"},"cantidad_total": {"type": "INTEGER", "description": "Opcional. El número total de unidades en la caja."},"fecha_caducidad": {"type": "STRING", "description": "Opcional. La fecha de caducidad en formato AAAA-MM-DD."}}, "required": ["nombre", "dosis", "frecuencia_horas", "duracion_dias"]}}
update_contact_info_tool = {"name": "update_contact_info", "description": "Actualiza la información de contacto de emergencia del usuario, como el nombre del médico o el teléfono del centro de salud.", "parameters": {"type": "OBJECT", "properties": {"nombre_medico": {"type": "STRING", "description": "Opcional. El nombre del médico a guardar."},"telefono_centro_salud": {"type": "STRING", "description": "Opcional. El número de teléfono del centro de salud."}}}}
permanently_delete_medication_tool = {"name": "permanently_delete_medication", "description": "Elimina un medicamento para siempre de la papelera. Solo se debe usar si el usuario pide explícitamente borrarlo 'permanentemente' o 'para siempre'.", "parameters": {"type": "OBJECT", "properties": {"nombre": {"type": "STRING", "description": "El nombre del medicamento a eliminar de la papelera."}}, "required": ["nombre"]}}
query_medication_tool = {"name": "query_medication_info", "description": "Consulta información sobre un medicamento específico que el usuario tiene en su lista activa.", "parameters": {"type": "OBJECT", "properties": {"nombre": {"type": "STRING"}}, "required": ["nombre"]}}

# --- SYSTEM PROMPT COMPLETO Y DEFINITIVO ---
SYSTEM_INSTRUCTIONS = """
Eres 'Asistente de Salud PRO', una IA conversacional dentro de una app de gestión de salud. Eres empático, seguro y sigues las instrucciones al pie de la letra.

**REGLA MAESTRA:** A veces, el usuario te enviará un mensaje de 'Contexto interno'. Este mensaje es tu instrucción MÁS IMPORTANTE y te dice cuál es la tarea actual. Debes basar tu respuesta únicamente en completar el siguiente paso de esa tarea.

**FLUJO DE AGENDAR CITA (`add_appointment`):**
Este es un flujo de varios pasos. Sigue estas reglas estrictamente:
- **Contexto `step: especialista`**: El usuario te dará el nombre de un especialista. Tu única respuesta será: `Entendido, cita con [Especialista]. Ahora, dime la fecha y la hora.`
- **Contexto `step: fecha_hora`**: El usuario te dará una fecha y hora. Tu única respuesta será llamar a tu función interna con el formato JSON: `{"action": "schedule_appointment", "params": {"fecha_texto": "el texto original del usuario"}}`. No digas nada más.
- **Contexto `step: ubicacion`**: El usuario te dará el nombre de un lugar (hospital, centro de salud, etc.). Tu única tarea es esperar ese nombre. **NO debes confundirlo con una petición de actualizar contactos.** Cuando lo recibas, simplemente úsalo para confirmar la cita.
- **Contexto `step: confirmacion`**: El usuario te dirá "sí" o "no". Responde confirmando o cancelando la operación.

**HERRAMIENTAS FORMALES:**
Si la petición del usuario encaja con una de tus herramientas (`add_medication`, `update_contact_info`, etc.), úsala. **EXCEPCIÓN:** Si el contexto es `add_appointment` y el `step` es `ubicacion`, NUNCA uses la herramienta `update_contact_info`, incluso si el usuario dice "ambulatorio".

**SEGURIDAD (REGLA DE ORO):**
- **SÍ puedes** dar consejos de bienestar para síntomas leves (dolor de cabeza, cansancio) como descansar o hidratarse.
- **NO puedes** dar consejos médicos, diagnósticos, o información sobre medicamentos o lugares específicos. Si te preguntan algo que no sea un síntoma leve, tu única respuesta debe ser una derivación educada: "Lo siento, pero no puedo ayudarte con eso. Te recomiendo que consultes a un médico o farmacéutico."
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
        if not api_key: return jsonify({'error': 'API key no configurada.'}), 500
        genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            tools=[add_medication_tool, update_contact_info_tool, permanently_delete_medication_tool, query_medication_tool],
            system_instruction=SYSTEM_INSTRUCTIONS,
            safety_settings=SAFETY_SETTINGS
        )
        
        data = request.get_json()
        gemini_history = [{"role": msg['role'], 'parts': [{'text': msg.get('content', '')}]} for msg in data['messages']]
        if not gemini_history: return jsonify({'text': "Hola, ¿en qué puedo ayudarte hoy?"})

        response = model.generate_content(gemini_history, request_options={"timeout": 100})
        
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts and response.candidates[0].content.parts[0].function_call:
            function_call = response.candidates[0].content.parts[0].function_call
            args = {key: value for key, value in function_call.args.items()}
            return jsonify({"action": function_call.name, "params": args})

        response_text = response.text.strip()
        response_json = None
        
        if response_text.startswith('{') and response_text.endswith('}'):
            try:
                response_json = json.loads(response_text)
            except json.JSONDecodeError:
                pass
        
        if response_json is None:
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                try:
                    response_json = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        
        if response_json and response_json.get("action") == "schedule_appointment":
            fecha_texto = response_json.get("params", {}).get("fecha_texto", "")
            parsed_datetime = parsear_fecha_hora(fecha_texto)
            if parsed_datetime:
                return jsonify({
                    "action": "confirm_appointment",
                    "params": { "parsed_datetime": parsed_datetime.strftime("%Y-%m-%d %H:%M:%S"), "confirmation_string": f"Entendido, he anotado la fecha: {format_datetime_espanol(parsed_datetime)}. Ahora, ¿dónde será la cita?" }
                })
            else:
                return jsonify({"text": "No he podido entender esa fecha y hora. Por favor, dímela de nuevo."})

        return jsonify({'text': response_text})

    except Exception as e:
        print(f"ERROR DETALLADO EN EL SERVIDOR: {e}") 
        return jsonify({'error': f'Error interno en el servidor: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def home():
    return "Servidor del Asistente de Salud PRO funcionando.", 200
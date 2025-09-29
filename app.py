# app.py (Versión de Producción Final - Asistente con Herramientas Completas y Conversacional)
import os
import google.generativeai as genai
from flask import Flask, request, jsonify
from google.generativeai.types import HarmCategory, HarmBlockThreshold

app = Flask(__name__)


def parsear_fecha_hora(texto: str) -> datetime or None:
    texto_norm = texto.lower()
    now = datetime.now()
    
    # Bandera para saber si se mencionó explícitamente un día
    dia_explicito = False
    
    # --- 1. PRIMERO EXTRAER LA FECHA ---
    fecha_base = None
    
    # Días relativos explícitos (estos son muy claros)
    if 'hoy' in texto_norm:
        fecha_base = now.date()
        dia_explicito = True
    elif 'mañana' in texto_norm:
        fecha_base = (now + timedelta(days=1)).date()
        dia_explicito = True
    elif 'pasado mañana' in texto_norm:
        fecha_base = (now + timedelta(days=2)).date()
        dia_explicito = True
    
    # Días de la semana
    dia_semana_encontrado = None
    for dia_str, dia_num in DIAS_SEMANA.items():
        if dia_str in texto_norm:
            dia_semana_encontrado = dia_num
            dia_explicito = True
            break
    
    if dia_semana_encontrado is not None:
        dias_a_sumar = (dia_semana_encontrado - now.weekday() + 7) % 7
        
        # Si es "próximo [día]", asegurar que sea de la próxima semana
        if 'próximo' in texto_norm or 'proximo' in texto_norm:
            if dias_a_sumar == 0:  # Si es hoy, sumar 7 días
                dias_a_sumar = 7
        elif dias_a_sumar == 0:  # Si es hoy y no se especifica "próximo"
            # Usar hoy
            dias_a_sumar = 0
        
        fecha_base = (now + timedelta(days=dias_a_sumar)).date()
    
    # Fecha específica (día y mes) - "15 de diciembre"
    match_fecha = re.search(r'(\d{1,2})\s+de\s+([a-zA-Záéíóúñ]+)', texto_norm)
    if match_fecha:
        dia_str, mes_str = match_fecha.groups()
        mes_str = mes_str.lower().strip()
        
        if mes_str in MESES:
            anio = now.year
            mes = MESES[mes_str]
            dia = int(dia_str)
            
            try:
                fecha_candidata = datetime(anio, mes, dia).date()
                # Si la fecha ya pasó este año, usar próximo año
                if fecha_candidata < now.date():
                    anio += 1
                fecha_base = datetime(anio, mes, dia).date()
                dia_explicito = True
            except ValueError:
                pass

    # Si no se encontró fecha explícita, usar hoy
    if fecha_base is None:
        fecha_base = now.date()
    
    # --- 2. LUEGO EXTRAER LA HORA ---
    hora, minuto = None, 0
    
    # PRIMERO buscar minutos especiales (antes que la hora normal)
    if 'y media' in texto_norm: 
        minuto = 30
    elif 'y cuarto' in texto_norm or 'y quart' in texto_norm: 
        minuto = 15
    elif 'menos cuarto' in texto_norm or 'menos quart' in texto_norm:
        minuto = 45
    
    # AHORA buscar la hora
    patrones_hora = [
        r'(\d{1,2})\s*[:\.]\s*(\d{2})',  # 14:30, 14.30
        r'a las (\d{1,2})',              # a las 3
        r'las (\d{1,2})',                # las 3
        r'a la (\d{1,2})',               # a la 1
        r'(\d{1,2})\s+(de la|de)',       # 3 de la tarde
        r'(\d{1,2})\s*$',                # solo el número al final
        r'(\d{1,2})\s+(en punto|exactas|punto)',  # 3 en punto
    ]
    
    for patron in patrones_hora:
        match = re.search(patron, texto_norm)
        if match:
            hora = int(match.group(1))
            # Si el patrón incluye minutos (como 14:30), sobreescribir los minutos
            if len(match.groups()) >= 2 and match.group(2).isdigit():
                minuto = int(match.group(2))
            break
    
    # Si no encontramos hora pero sí minutos, buscar hora por separado
    if hora is None and minuto > 0:
        # Buscar cualquier número que podría ser la hora
        match_hora = re.search(r'(\d{1,2})', texto_norm)
        if match_hora:
            hora = int(match_hora.group(1))
    
    # Ajustar formato 12h a 24h
    if hora is not None:
        if any(s in texto_norm for s in ['tarde', 'noche', 'pm', 'p.m.']) and hora < 12: 
            hora += 12
        if any(s in texto_norm for s in ['de la mañana', 'am', 'a.m.']) and hora == 12: 
            hora = 0
        if any(s in texto_norm for s in ['de la mañana', 'am', 'a.m.']) and hora > 12:
            # Si dice "13 de la mañana", corregir a 1 PM
            hora = hora % 12
        # Asegurar rango válido
        hora = hora % 24
        
        # Manejar "menos cuarto" (restar 1 hora y poner 45 minutos)
        if 'menos cuarto' in texto_norm or 'menos quart' in texto_norm:
            hora -= 1
            if hora < 0:
                hora = 23
    else:
        # Si no se especifica hora, usar 9 AM por defecto
        hora = 9
        minuto = 0

    # --- 3. COMBINAR FECHA Y HORA ---
    try:
        fecha_final = datetime(fecha_base.year, fecha_base.month, fecha_base.day, hora, minuto)
        
        # Lógica de ajuste
        if (fecha_final < now and 
            not dia_explicito and 
            dia_semana_encontrado is None and
            not any(palabra in texto_norm for palabra in ['hoy', 'mañana', 'pasado mañana'])):
            
            diferencia = now - fecha_final
            dias_a_agregar = (diferencia.days + 1)
            fecha_final += timedelta(days=dias_a_agregar)
        
        return fecha_final
        
    except ValueError:
        return None

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
Eres 'Asistente de Salud', una IA conversacional empática y segura.

Tus modos de operar son:
1.  **Modo de Herramientas:** Si el usuario pide añadir un medicamento, contacto, etc., usa las herramientas formales.

2.  **Modo de Agendar Citas (¡NUEVA REGLA!):** Cuando el usuario está agendando una cita y te da una fecha y hora en lenguaje natural (ej: "el 3 de septiembre a las 9 y media"), tu ÚNICA RESPUESTA debe ser llamar a la función `schedule_appointment`. Esta función NO es una herramienta formal de la API, sino una directiva para el backend. Tu respuesta JSON debe ser: `{"action": "schedule_appointment", "params": {"fecha_texto": "el texto que dijo el usuario"}}`. NO intentes confirmar la fecha tú mismo, solo pasa el texto.

3.  **Modo de Consejo de Bienestar:** Para síntomas leves, da consejos generales (descansar, hidratarse) y siempre termina recomendando consultar a un médico si los síntomas persisten.

4.  **Modo de Derivación (REGLA DE ORO):** Para CUALQUIER otra pregunta de salud (síntomas graves, medicamentos, diagnósticos), niégate educadamente y recomienda SIEMPRE consultar a un médico o farmacéutico.
"""

@app.route('/chat', methods=['POST'])
def chat_proxy():
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key: return jsonify({'error': 'La variable de entorno GEMINI_API_KEY no está configurada.'}), 500
        
        genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash-latest',
            tools=[add_medication_tool, update_contact_info_tool, permanently_delete_medication_tool, query_medication_tool],
            system_instruction=SYSTEM_INSTRUCTIONS,
            response_mime_type="application/json" # Forzamos la salida a JSON
        )
        
        data = request.get_json()
        if not data or 'messages' not in data: return jsonify({'error': 'Petición inválida.'}), 400

        gemini_history = [{"role": msg['role'], 'parts': [{'text': msg.get('content', '')}]} for msg in data['messages'] if msg.get('role') in ['user', 'model']]
        if not gemini_history: return jsonify({'text': "Hola, ¿en qué puedo ayudarte hoy?"})

        response = model.generate_content(gemini_history)
        
        # Analizamos la respuesta de Gemini
        try:
            # El modelo ahora debería devolver JSON directamente
            response_json = json.loads(response.text)
            
            # --- NUEVA LÓGICA PARA MANEJAR LA ACCIÓN DE AGENDAR ---
            if response_json.get("action") == "schedule_appointment":
                fecha_texto = response_json["params"]["fecha_texto"]
                parsed_datetime = parsear_fecha_hora(fecha_texto) # Usamos el parser aquí, en el backend
                
                if parsed_datetime:
                    # Creamos una respuesta estructurada para la app
                    return jsonify({
                        "action": "confirm_appointment",
                        "params": {
                            "parsed_datetime": parsed_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                            "confirmation_string": f"Entendido, he anotado la fecha y hora: {format_datetime_espanol(parsed_datetime)}. Ahora, ¿dónde será la cita?"
                        }
                    })
                else:
                    # Si nuestro parser robusto falla, pedimos al usuario que lo intente de nuevo
                    return jsonify({"text": "No he podido entender esa fecha y hora. ¿Podrías decírmelo de otra forma, por ejemplo, 'mañana a las 5 de la tarde'?"})

            return jsonify(response_json) # Devolvemos el JSON tal cual para otras acciones

        except (json.JSONDecodeError, KeyError):
             # Si la respuesta no es un JSON válido o no tiene la estructura esperada,
             # la tratamos como texto normal.
             return jsonify({'text': response.text})

    except Exception as e:
        print(f"ERROR DETALLADO EN EL SERVIDOR: {e}") 
        return jsonify({'error': f'Error interno en el servidor: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def home():
    return "Servidor del Asistente de Salud PRO (v-final - Herramientas Completas) funcionando.", 200
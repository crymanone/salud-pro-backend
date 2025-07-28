# app.py
import os
import openai
from flask import Flask, request, jsonify

app = Flask(__name__)

# La clave se leerá de las variables de entorno de Vercel. ¡Es seguro!
try:
    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    if not os.environ.get("OPENAI_API_KEY"):
        print("ADVERTENCIA: La variable de entorno OPENAI_API_KEY no está configurada.")
except Exception as e:
    print(f"Error al inicializar el cliente de OpenAI: {e}")
    client = None

@app.route('/chat', methods=['POST'])
def chat_proxy():
    if not client:
        return jsonify({'error': 'El servidor no tiene una clave de OpenAI configurada'}), 500
    
    try:
        data = request.get_json()
        if not data or 'messages' not in data:
            return jsonify({'error': 'No se proporcionó un historial de mensajes'}), 400

        # Llamada segura a OpenAI desde nuestro servidor
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=data['messages']
        )
        
        # Devolvemos la respuesta completa de OpenAI a la app Kivy
        return response.to_json(), 200

    except openai.AuthenticationError:
        return jsonify({'error': 'Clave API de OpenAI inválida o sin fondos. Revisa la configuración del servidor.'}), 500
    except Exception as e:
        print(f"Error inesperado en el proxy: {e}")
        return jsonify({'error': 'Ha ocurrido un error interno en el servidor'}), 500

# Añadimos una ruta raíz para comprobar que el servidor funciona
@app.route('/', methods=['GET'])
def home():
    return "Servidor del Asistente de Salud PRO funcionando.", 200
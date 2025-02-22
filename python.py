from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from supabase_connection import *
import whisper
import os
import threading
import queue
import logging
import tempfile

# Configurar logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Cargar modelo de Whisper
model = whisper.load_model("base")

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Crear cola de tareas sin bloqueos
task_queue = queue.SimpleQueue()

# Flag para detener el worker correctamente
worker_running = True

def transcribe_worker():
    global worker_running
    while worker_running:
        try:
            user_id = task_queue.get()
            if user_id is None:
                continue

            logging.info(f"Iniciando transcripción para el usuario {user_id}")
            socketio.emit("transcription_status", {"user_id": user_id, "status": "iniciando"})

            bucket_name = 'files'
            response = supabase.storage.from_(bucket_name).list(
                f'{user_id}/audio/', {"limit": 1, "offset": 0, "sortBy": {"column": "name", "order": "desc"}}
            )

            if not response:
                logging.warning(f"No se encontraron audios para el usuario {user_id}")
                socketio.emit("transcription_status", {"user_id": user_id, "status": "error", "message": "No se encontraron audios."})
                continue

            audio_name = response[0]['name']
            file_path = f'{user_id}/audio/{audio_name}'

            audio_data = supabase.storage.from_(bucket_name).download(file_path)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
                temp_audio.write(audio_data)
                temp_audio_path = temp_audio.name

            result = model.transcribe(temp_audio_path)
            transcription_text = result["text"]

            os.remove(temp_audio_path)

            transcription_file_name = f"{audio_name.split('.')[0]}_transcription.txt"
            with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".txt") as temp_transcription:
                temp_transcription.write(transcription_text)
                temp_transcription_path = temp_transcription.name

            transcription_path = f'{user_id}/transcription/{transcription_file_name}'
            with open(temp_transcription_path, 'rb') as transcription_file:
                supabase.storage.from_(bucket_name).upload(transcription_path, transcription_file)

            os.remove(temp_transcription_path)
            
            socketio.emit("transcription_completed", {"user_id": user_id, "transcription": transcription_text})

            #ogging.info(f"Transcripción completada para el usuario {user_id}")
        
        except Exception as e:
            logging.error(f"Error procesando la transcripción para el usuario {user_id}: {str(e)}")
            socketio.emit("transcription_status", {"user_id": user_id, "status": "error", "message": str(e)})

worker_thread = threading.Thread(target=transcribe_worker, daemon=True)
worker_thread.start()

@app.route('/transcribe', methods=['POST'])
def transcribe():
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id es requerido"}), 400

    task_queue.put(user_id)
    return jsonify({"message": "Solicitud de transcripción recibida."})

@app.route('/shutdown', methods=['POST'])
def shutdown():
    global worker_running
    worker_running = False
    task_queue.put(None)
    return jsonify({"message": "El servidor se está cerrando"}), 200

if __name__ == '__main__':
    try:
        socketio.run(app, debug=True)
    except KeyboardInterrupt:
        logging.info("Cerrando el servidor...")
        worker_running = False
        worker_thread.join()

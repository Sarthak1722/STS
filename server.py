from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import assemblyai as aai
import threading
import requests
import base64
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# API Keys
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
ELEVEN_LABS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

aai.settings.api_key = os.getenv("AAI_API_KEY")

class WebSocketTranscriber:
    def __init__(self, socket_id):
        self.socket_id = socket_id
        self.transcriber = aai.RealtimeTranscriber(
            on_data=self.on_data,
            on_error=self.on_error,
            sample_rate=44_100,
            on_open=self.on_open,
            on_close=self.on_close,
        )
        self.active = False

    def on_open(self, session_opened: aai.RealtimeSessionOpened):
        socketio.emit('status', {'message': 'Session started'}, room=self.socket_id)

    def on_data(self, transcript: aai.RealtimeTranscript):
        if transcript.text:
            is_final = isinstance(transcript, aai.RealtimeFinalTranscript)
            socketio.emit('transcript', {
                'text': transcript.text,
                'is_final': is_final
            }, room=self.socket_id)
            
            if is_final:
                self.synthesize_speech(transcript.text)

    def synthesize_speech(self, text):
        def run():
            try:
                headers = {
                    "Accept": "audio/mpeg",
                    "Content-Type": "application/json",
                    "xi-api-key": os.getenv("ELEVEN_LABS_API_KEY")
                }
                payload = {
                    "text": text,
                    "model_id": "eleven_monolingual_v1",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.5
                    }
                }

                response = requests.post(ELEVEN_LABS_URL, json=payload, headers=headers)
                response.raise_for_status()

                audio_data = base64.b64encode(response.content).decode('utf-8')
                socketio.emit('audio', {
                    'data': audio_data,
                    'text': text
                }, room=self.socket_id)

            except Exception as e:
                socketio.emit('error', {
                    'message': f"Synthesis Error: {str(e)}"
                }, room=self.socket_id)

        threading.Thread(target=run).start()

    def on_error(self, error: aai.RealtimeError):
        socketio.emit('error', {
            'message': str(error)
        }, room=self.socket_id)

    def on_close(self):
        socketio.emit('status', {
            'message': 'Session closed'
        }, room=self.socket_id)

    def process_audio(self, audio_data):
        self.transcriber.stream(audio_data)

    def start(self):
        self.active = True
        self.transcriber.connect()

    def stop(self):
        self.active = False
        self.transcriber.close()

# Store active transcribers
transcribers = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    transcribers[request.sid] = WebSocketTranscriber(request.sid)
    transcribers[request.sid].start()

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in transcribers:
        transcribers[request.sid].stop()
        del transcribers[request.sid]

@socketio.on('audio_data')
def handle_audio_data(data):
    if request.sid in transcribers:
        audio_bytes = base64.b64decode(data['audio'])
        transcribers[request.sid].process_audio(audio_bytes)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
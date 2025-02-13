from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import assemblyai as aai
from openai import OpenAI
from elevenlabs.client import ElevenLabs
import threading
import base64
import os
from dotenv import load_dotenv
from collections import deque

load_dotenv()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# API Configurations
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_MODEL = "eleven_turbo_v2"

aai.settings.api_key = "372010b5feaa4fc5871aa742e32e992c"
openai_client = OpenAI(api_key="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")
elevenlabs_client = ElevenLabs(api_key="sk_e2623168a6341fa87a3d0fc200d47145a18b8c7a7a114511")

class WebSocketTranscriber:
    def __init__(self, socket_id):
        self.socket_id = socket_id
        self.history = deque(maxlen=4)
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
        if transcript.text and isinstance(transcript, aai.RealtimeFinalTranscript):
            # is_final = isinstance(transcript, aai.RealtimeFinalTranscript)
            socketio.emit('transcript', {
                'text': transcript.text,
                'is_final': True
            }, room=self.socket_id)
            
            # if is_final:
            self.process_gpt_response(transcript.text)

    def process_gpt_response(self, user_text):
        def generate_and_synthesize():
            try:
                # Generate GPT response
                self.history.append({"role": "user", "content": user_text})
                messages = [
                    {"role": "system", "content": "Respond concisely and conversationally. Keep the response short to maximum 2-3 sentences."},
                    *list(self.history)
                ]
                
                gpt_response = openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=messages,
                    max_tokens=100,
                    temperature=0.7
                )
                response_text = gpt_response.choices[0].message.content
                self.history.append({"role": "assistant", "content": response_text})

                # Convert text to audio bytes
                audio_stream = elevenlabs_client.text_to_speech.convert(
                    voice_id=VOICE_ID,
                    text=response_text,
                    model_id=ELEVENLABS_MODEL,
                )
                
                # Read all audio chunks into bytes
                audio_bytes = b""
                for chunk in audio_stream:
                    if chunk:
                        audio_bytes += chunk
                
                # Encode and send audio
                audio_data = base64.b64encode(audio_bytes).decode('utf-8')
                
                with app.app_context():
                    socketio.emit('audio', {
                        'data': audio_data,
                        'text': response_text
                    }, room=self.socket_id)
                    socketio.emit('assistant_response', {
                        'text': response_text
                    }, room=self.socket_id)

            except Exception as e:
                with app.app_context():
                    socketio.emit('error', {'message': f"Error: {str(e)}"}, room=self.socket_id)

        threading.Thread(target=generate_and_synthesize).start()

    def on_error(self, error: aai.RealtimeError):
        with app.app_context():
            socketio.emit('error', {'message': str(error)}, room=self.socket_id)

    def on_close(self):
        with app.app_context():
            socketio.emit('status', {'message': 'Session closed'}, room=self.socket_id)

    def process_audio(self, audio_data):
        self.transcriber.stream(audio_data)

    def start(self):
        self.active = True
        self.transcriber.connect()

    def stop(self):
        self.active = False
        self.transcriber.close()

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
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
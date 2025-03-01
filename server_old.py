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
import time

load_dotenv()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# API Configurations
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_MODEL = "eleven_turbo_v2"

aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
elevenlabs_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

# Debug flag - set to True to see more verbose output
DEBUG = True

def debug_log(message):
    if DEBUG:
        print(f"[DEBUG] {message}")

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
        self.interrupt_flag = False
        self.audio_generation_thread = None
        self.is_processing_response = False  # Add a flag to track if we're processing a response

    def on_open(self, session_opened: aai.RealtimeSessionOpened):
        debug_log("Transcription session opened")
        socketio.emit('status', {'message': 'Session started'}, room=self.socket_id)

    def on_data(self, transcript: aai.RealtimeTranscript):
        if transcript.text and isinstance(transcript, aai.RealtimeFinalTranscript):
            debug_log(f"Received final transcript: {transcript.text}")
            socketio.emit('transcript', {
                'text': transcript.text,
                'is_final': True
            }, room=self.socket_id)
            
            # Set interrupt flag if a previous generation is in progress
            if self.audio_generation_thread and self.audio_generation_thread.is_alive():
                debug_log("Interrupting previous audio generation")
                # self.interrupt_flag = True
                socketio.emit('audio_interrupted', room=self.socket_id)
                # Wait a brief moment for the previous thread to notice the interrupt
                threading.Event().wait(0.5)
            
            self.process_gpt_response(transcript.text)

    def process_gpt_response(self, user_text):
        # Reset interrupt flag for new generation
        self.interrupt_flag = False
        debug_log(f"Processing user text: {user_text}")
        self.is_processing_response = True  # Set flag to indicate we're processing
        
        def generate_and_synthesize():
            try:
                # Generate GPT response
                self.history.append({"role": "user", "content": user_text})
                messages = [
                    {"role": "system", "content": "Respond concisely and conversationally. Keep the response short to maximum 2-3 sentences."},
                    *list(self.history)
                ]
                
                # Check if interrupted before expensive API call
                if self.interrupt_flag:
                    debug_log("Generation interrupted before GPT call")
                    self.is_processing_response = False  # Reset processing flag
                    return
                
                gpt_response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    max_tokens=100,
                    temperature=0.7
                )
                response_text = gpt_response.choices[0].message.content
                
                self.history.append({"role": "assistant", "content": response_text})
                debug_log(f"Generated response: {response_text}")

                # Check if interrupted before audio generation
                # if self.interrupt_flag:
                #     debug_log("Generation interrupted before audio synthesis")
                #     self.is_processing_response = False  # Reset processing flag
                #     return
                
                # Use app context for all socketio emissions
                # This ensures the Flask context is properly maintained in the thread
                with app.app_context():
                    try:
                        socketio.emit('assistant_response', {
                            'text': response_text
                        }, room=self.socket_id)
                        debug_log(f"Emitted assistant_response to {self.socket_id}")
                        
                        socketio.emit('audio_generation_started', room=self.socket_id)
                        debug_log("Emitted audio_generation_started")
                    except Exception as e:
                        debug_log(f"Error emitting response: {str(e)}")

                try:
                    # Convert text to audio bytes
                    debug_log(f"Starting ElevenLabs audio generation for: '{response_text}'")
                    debug_log(f"Using voice ID: {VOICE_ID} and model: {ELEVENLABS_MODEL}")
                    
                    start_time = time.time()
                    audio_buffer = []
                    
                    # Test with a simple audio generation approach for debugging
                    audio_stream = elevenlabs_client.text_to_speech.convert(
                        voice_id=VOICE_ID,
                        text=response_text,
                        model_id=ELEVENLABS_MODEL,
                    )
                    debug_log("Audio stream created successfully")
                    
                    # Collect audio chunks
                    chunk_count = 0
                    for chunk in audio_stream:
                        if self.interrupt_flag:
                            debug_log("Interrupting audio generation during streaming")
                            with app.app_context():
                                socketio.emit('audio_generation_cancelled', room=self.socket_id)
                            self.is_processing_response = False  # Reset processing flag
                            return
                        
                        if chunk:
                            chunk_count += 1
                            audio_buffer.append(chunk)
                    
                    debug_log(f"Collected {chunk_count} audio chunks")
                    
                    # Then send all chunks together
                    # if audio_buffer and not self.interrupt_flag:
                    if audio_buffer:
                        with app.app_context():
                            try:
                                # Send a complete audio buffer to prevent choppy playback
                                complete_audio = b''.join(audio_buffer)
                                audio_data = base64.b64encode(complete_audio).decode('utf-8')
                                
                                debug_log(f"Audio generation completed in {time.time() - start_time:.2f} seconds")
                                debug_log(f"Audio size: {len(complete_audio)} bytes, Base64 length: {len(audio_data)}")
                                
                                socketio.emit('audio_complete', {
                                    'data': audio_data,
                                    'text': response_text
                                }, room=self.socket_id)
                                debug_log(f"Emitted audio_complete to {self.socket_id}")
                            except Exception as e:
                                debug_log(f"Error sending audio: {str(e)}")
                    else:
                        debug_log("No audio data to send or interrupted")
                
                except Exception as e:
                    debug_log(f"Error in audio generation: {str(e)}")
                    with app.app_context():
                        socketio.emit('error', {'message': f"Audio generation error: {str(e)}"}, room=self.socket_id)

            except Exception as e:
                debug_log(f"Error in generate_and_synthesize: {str(e)}")
                with app.app_context():
                    socketio.emit('error', {'message': f"Error: {str(e)}"}, room=self.socket_id)
            
            finally:
                self.is_processing_response = False  # Always reset the processing flag when done

        # Store the thread reference so we can check its status
        debug_log("Starting audio generation thread")
        self.audio_generation_thread = threading.Thread(target=generate_and_synthesize)
        self.audio_generation_thread.daemon = True  # Make thread daemon so it doesn't block app shutdown
        self.audio_generation_thread.start()

    def on_error(self, error: aai.RealtimeError):
        debug_log(f"Transcription error: {str(error)}")
        with app.app_context():
            socketio.emit('error', {'message': str(error)}, room=self.socket_id)

    def on_close(self):
        debug_log("Transcription session closed")
        with app.app_context():
            socketio.emit('status', {'message': 'Session closed'}, room=self.socket_id)

    def process_audio(self, audio_data):
        # Only interrupt if we're currently generating a response AND new speech is detected
        if self.is_processing_response and self.audio_generation_thread and self.audio_generation_thread.is_alive():
            # Check for voice activity here - this would be better if coordinated with the client
            # For now, we'll only interrupt if we're actively processing a response
            debug_log("User is speaking - interrupting assistant audio")
            # self.interrupt_flag = True
        
        self.transcriber.stream(audio_data)

    def start(self):
        debug_log(f"Starting transcriber for socket ID: {self.socket_id}")
        self.active = True
        self.transcriber.connect()

    def stop(self):
        debug_log(f"Stopping transcriber for socket ID: {self.socket_id}")
        self.active = False
        # self.interrupt_flag = True  # Ensure any ongoing processes are stopped
        if self.audio_generation_thread and self.audio_generation_thread.is_alive():
            self.audio_generation_thread.join(timeout=1.0)  # Wait briefly for thread to terminate
        self.transcriber.close()

transcribers = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    debug_log(f"Client connected: {request.sid}")
    transcribers[request.sid] = WebSocketTranscriber(request.sid)
    transcribers[request.sid].start()

@socketio.on('disconnect')
def handle_disconnect():
    debug_log(f"Client disconnected: {request.sid}")
    if request.sid in transcribers:
        transcribers[request.sid].stop()
        del transcribers[request.sid]

@socketio.on('audio_data')
def handle_audio_data(data):
    if request.sid in transcribers:
        try:
            audio_bytes = base64.b64decode(data['audio'])
            transcribers[request.sid].process_audio(audio_bytes)
        except Exception as e:
            debug_log(f"Error processing audio data: {str(e)}")

@socketio.on('interrupt')
def handle_interrupt():
    debug_log(f"Interrupt requested by client: {request.sid}")
    if request.sid in transcribers:
        transcribers[request.sid].interrupt_flag = True
        emit('audio_interrupted', room=request.sid)


@socketio.on('voice_activity')
def handle_voice_activity(data):
    debug_log(f"Voice activity update from client: {data}")
    if request.sid in transcribers:
        # Only set interrupt flag if voice is detected and we're processing a response
        if data.get('active', False) and transcribers[request.sid].is_processing_response:
            debug_log(f"Setting interrupt flag due to user voice activity")
            transcribers[request.sid].interrupt_flag = True
            emit('audio_interrupted', room=request.sid)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    debug_log(f"Starting server on port {port}")
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
import assemblyai as aai
from elevenlabs.client import ElevenLabs
from elevenlabs import stream
import time
import threading
import queue
from collections import deque
import concurrent.futures
import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class LatencyTracker:
    def __init__(self):
        self.timestamps = {}
        self.latency_data = {
            'transcription': [],
            'gpt': [],
            'tts': [],
            'total': []
        }
        
    def mark(self, event_name):
        self.timestamps[event_name] = time.time()
        
    def record_latency(self, stage, start_event, end_event):
        if start_event in self.timestamps and end_event in self.timestamps:
            latency = self.timestamps[end_event] - self.timestamps[start_event]
            self.latency_data[stage].append(latency)
            return latency
        return None

    def get_average_latency(self, stage):
        if self.latency_data[stage]:
            return sum(self.latency_data[stage])/len(self.latency_data[stage])
        return 0

class AudioProcessor:
    def __init__(self, tracker):
        self.text_queue = queue.Queue(maxsize=3)  # Small queue size to prevent backlog
        self.tracker = tracker
        self.client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.running = True

    def stream_audio(self, audio_stream):
        """Stream audio in main thread to avoid playback delays"""
        try:
            stream(audio_stream)
        except Exception as e:
            print(f"Audio streaming error: {e}")

    def process_tts(self):
        while self.running:
            try:
                text = self.text_queue.get(timeout=0.5)
                if text is None:
                    break
                    
                self.tracker.mark('tts_start')
                
                # Direct API call with low-latency parameters
                audio_stream = self.client.text_to_speech.convert_as_stream(
                    text=text,
                    voice_id="JBFqnCBsd6RMkjVDRZzb",
                    model_id="eleven_turbo_v2",
                    optimize_streaming_latency=3
                )
                
                self.tracker.record_latency('tts', 'tts_start', 'tts_end')
                self.stream_audio(audio_stream)

            except queue.Empty:
                continue
            except Exception as e:
                print(f"TTS Error: {e}")

    def start(self):
        threading.Thread(target=self.process_tts, daemon=True).start()

    def stop(self):
        self.running = False
        self.executor.shutdown(wait=False)

class GPTProcessor:
    def __init__(self, tracker):
        self.prompt_queue = queue.Queue(maxsize=3)
        self.response_queue = queue.Queue(maxsize=3)
        self.tracker = tracker
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.history = deque(maxlen=3)  # Keep last 3 exchanges
        self.running = True

    def process_prompts(self):
        while self.running:
            try:
                prompt = self.prompt_queue.get(timeout=0.5)
                if prompt is None:
                    break
                
                self.tracker.mark('gpt_start')
                
                # Build conversation history
                messages = [
                    {"role": "system", "content": "Respond concisely and conversationally. Keep responses under 2 sentences."},
                    *[{"role": role, "content": content} for role, content in self.history],
                    {"role": "user", "content": prompt}
                ]
                
                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    max_tokens=100,
                    temperature=0.7,
                    stream=False  # Streaming adds complexity but can reduce perceived latency
                )
                
                response_text = response.choices[0].message.content
                self.response_queue.put(response_text)
                
                # Update history
                self.history.extend([
                    ("user", prompt),
                    ("assistant", response_text)
                ])
                
                self.tracker.mark('gpt_end')
                self.tracker.record_latency('gpt', 'gpt_start', 'gpt_end')

            except queue.Empty:
                continue
            except Exception as e:
                print(f"GPT Error: {e}")

    def start(self):
        threading.Thread(target=self.process_prompts, daemon=True).start()

    def stop(self):
        self.running = False

class RealtimeTranscriber:
    def __init__(self):
        self.tracker = LatencyTracker()
        self.audio_processor = AudioProcessor(self.tracker)
        self.gpt_processor = GPTProcessor(self.tracker)
        
        aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
        self.transcriber = aai.RealtimeTranscriber(
            on_data=self.on_data,
            on_error=self.on_error,
            sample_rate=44_100,
            on_open=self.on_open,
            on_close=self.on_close,
        )

    def on_open(self, session_opened: aai.RealtimeSessionOpened):
        print("Session ID:", session_opened.session_id)
        self.tracker.mark('session_start')
        self.audio_processor.start()
        self.gpt_processor.start()

    def on_data(self, transcript: aai.RealtimeTranscript):
        if not transcript.text:
            return

        if isinstance(transcript, aai.RealtimeFinalTranscript):
            self.tracker.mark('transcription_end')
            latency = self.tracker.record_latency(
                'transcription', 'session_start', 'transcription_end'
            )
            
            print(f"User: {transcript.text}")
            print(f"Transcription Latency: {latency:.3f}s")
            
            # Send to GPT processor
            self.gpt_processor.prompt_queue.put(transcript.text)
            
            # Get GPT response and queue for TTS
            try:
                response = self.gpt_processor.response_queue.get(timeout=5)
                print(f"Assistant: {response}")
                self.audio_processor.text_queue.put(response)
            except queue.Empty:
                print("GPT response timeout")

    def on_error(self, error: aai.RealtimeError):
        print("Error:", error)

    def on_close(self):
        print("Closing Session")
        self.audio_processor.stop()
        self.gpt_processor.stop()
        
        # Print latency statistics
        print("\nAverage Latencies:")
        print(f"Transcription: {self.tracker.get_average_latency('transcription'):.3f}s")
        print(f"GPT Processing: {self.tracker.get_average_latency('gpt'):.3f}s")
        print(f"TTS Conversion: {self.tracker.get_average_latency('tts'):.3f}s")

    def start(self):
        self.transcriber.connect()
        microphone_stream = aai.extras.MicrophoneStream()
        print("Start speaking...")
        self.transcriber.stream(microphone_stream)

    def stop(self):
        self.transcriber.close()

def main():
    transcriber = RealtimeTranscriber()
    try:
        transcriber.start()
    except KeyboardInterrupt:
        transcriber.stop()

if __name__ == "__main__":
    main()
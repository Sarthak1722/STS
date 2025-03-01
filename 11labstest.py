from elevenlabs.client import ElevenLabs
import os
from dotenv import load_dotenv
from elevenlabs import stream
load_dotenv()

elevenlabs_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_MODEL = "eleven_turbo_v2"

# audio = generate(
#     text="Test audio generation",
#     voice=VOICE_ID,
#     model="eleven_turbo_v2"
# )

audio_stream = elevenlabs_client.text_to_speech.convert(
                        voice_id=VOICE_ID,
                        text="Hello! How may i help you?",
                        model_id=ELEVENLABS_MODEL,
                    )

stream(audio_stream)


# Error in audio generation: status_code: 401,
# body: {'detail': {'status': 'detected_unusual_activity',
# 'message': 'Unusual activity detected. Free Tier usage disabled.
# If you are using a proxy/VPN you might need to purchase a Paid Plan to not trigger our abuse detectors.
# Free Tier only works if users do not abuse it, for example by creating multiple free accounts.
# If we notice that many people try to abuse it, we will need to reconsider Free Tier altogether.
#  \nPlease play fair and purchase any Paid Subscription to continue.'}}
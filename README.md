# End-to-End Voice Chatbot 🤖🎙️

An intelligent, real-time voice chatbot built with AssemblyAI, GPT-4, and ElevenLabs for seamless transcription, response generation, and text-to-speech conversion. Hosted on AWS EC2 with robust backend architecture using Flask.

## 🔧 Features

- 🎤 **Real-Time Voice Transcription** using [AssemblyAI](https://www.assemblyai.com/)
- 🧠 **Smart Response Generation** powered by OpenAI's **GPT-4**
- 🔊 **Natural Text-to-Speech** using [ElevenLabs API](https://www.elevenlabs.io/)
- 🔁 **Smart Interruption Handling** for smooth, interactive conversations
- 📅 **Calendar Booking System** with automatic availability checking
- ☁️ **Cloud Deployment** on AWS EC2 for scalable and reliable access

## 🏗️ Tech Stack

- **Backend:** Python, Flask, Socket.IO
- **APIs:** AssemblyAI, OpenAI GPT-4, ElevenLabs
- **Hosting:** AWS EC2
- **Others:** Threading, Parallel Processing, WebSockets

## 📌 Getting Started

### Prerequisites

- Python 3.8+
- API keys for:
  - AssemblyAI
  - OpenAI
  - ElevenLabs

### Installation

```bash
git clone https://github.com/yourusername/voice-chatbot.git
cd voice-chatbot
pip install -r requirements.txt
```


### Configuration
Create a .env file and add your API keys:

```env Copy Edit
ASSEMBLYAI_API_KEY=your_key
OPENAI_API_KEY=your_key
ELEVENLABS_API_KEY=your_key
```

### Run the App
```
python app.py
```

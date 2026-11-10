"""
Jarvis voice loop (Windows).

Say "Hey Jarvis" -> speak your request -> Jarvis answers out loud.

Flow: wake word (openWakeWord) -> record -> faster-whisper -> n8n webhook -> speak reply

Install:
    pip install sounddevice numpy requests faster-whisper openwakeword pyttsx3
    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12     (for the NVIDIA GPU)
    pip install piper-tts                                (nicer voice)
    python -m piper.download_voices en_GB-alan-medium    (run in the script's folder)

Run:
    python jarvis_voice.py
"""

import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

# --- GPU (NVIDIA) setup: lets Windows find the CUDA libraries installed with pip ---
for _pkg in ("nvidia.cublas", "nvidia.cudnn"):
    try:
        _mod = __import__(_pkg, fromlist=["x"])
        _bin = os.path.join(list(_mod.__path__)[0], "bin")
        os.add_dll_directory(_bin)
        os.environ["PATH"] = _bin + os.pathsep + os.environ["PATH"]
    except ImportError:
        pass

import numpy as np
import openwakeword
import pyttsx3
import requests
import sounddevice as sd
from faster_whisper import WhisperModel
from openwakeword.model import Model

# ---------------------------------------------------------------- settings
WEBHOOK_URL = os.getenv("JARVIS_WEBHOOK_URL", "http://localhost:5678/webhook/jarvis")
# Set via environment variable or replace placeholder directly
WEBHOOK_KEY = os.getenv("JARVIS_VOICE_KEY", "YOUR_VOICE_WEBHOOK_KEY")
WEBHOOK_HEADER = "X-Jarvis-Key"

# --- Voice (Piper) settings
PIPER_VOICE = "en_GB-alan-medium"
PIPER_LENGTH_SCALE = 1.08          # above 1 = slower and calmer, below 1 = faster
VOICE_DIR = Path(__file__).parent  # folder containing the .onnx and .onnx.json files

WHISPER_MODEL = "medium"           # tiny / base / small / medium / large-v3-turbo (12 GB cards)
DEVICE = "cuda"                    # NVIDIA RTX 3060. Use "cpu" if CUDA gives errors
COMPUTE_TYPE = "float16"           # use "int8_float16" on a 6 GB laptop card, "int8" on cpu

WAKE_THRESHOLD = 0.5               # lower = more sensitive, higher = fewer false triggers
SAMPLE_RATE = 16000
FRAME = 1280                       # 80 ms, what openWakeWord expects

SILENCE_RMS = 500                  # raise if it never stops recording, lower if it cuts you off
SILENCE_SECONDS = 1.3              # silence that ends your sentence
MAX_RECORD_SECONDS = 15
NO_SPEECH_TIMEOUT = 5              # give up if you say nothing

# ---------------------------------------------------------------- setup
print("Loading models (first run downloads them)...")
openwakeword.utils.download_models()
wake = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
stt = WhisperModel(WHISPER_MODEL, device=DEVICE, compute_type=COMPUTE_TYPE)


def _speak_windows_voice(text: str) -> None:
    """Fallback: built-in Windows voice."""
    engine = pyttsx3.init()
    engine.setProperty("rate", 175)
    engine.say(text)
    engine.runAndWait()
    engine.stop()


def _speak_piper(text: str) -> bool:
    """Speak with Piper."""
    model = VOICE_DIR / f"{PIPER_VOICE}.onnx"
    if not model.exists():
        print(f"(Piper voice not found: {model}. Using the Windows voice.)")
        return False

    wav_path = Path(tempfile.gettempdir()) / "jarvis_tts.wav"
    try:
        subprocess.run(
            [
                sys.executable, "-m", "piper",
                "--model", str(model),
                "--output_file", str(wav_path),
                "--length-scale", str(PIPER_LENGTH_SCALE),
            ],
            input=text.encode("utf-8"),
            check=True,
            capture_output=True,
            timeout=60,
        )
        with wave.open(str(wav_path), "rb") as wf:
            rate = wf.getframerate()
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        sd.play(audio, rate)
        sd.wait()
        return True
    except Exception as e:
        print("(Piper failed, using the Windows voice):", e)
        return False


def speak(text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    print("Jarvis:", text)
    if not _speak_piper(text):
        _speak_windows_voice(text)


def rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))


def record_request(stream: sd.InputStream) -> np.ndarray:
    chunks = []
    started = False
    silent_frames = 0
    start_time = time.time()
    silence_limit = int(SILENCE_SECONDS * SAMPLE_RATE / FRAME)

    while time.time() - start_time < MAX_RECORD_SECONDS:
        data, _ = stream.read(FRAME)
        frame = data[:, 0]
        chunks.append(frame.copy())
        if rms(frame) > SILENCE_RMS:
            started = True
            silent_frames = 0
        else:
            silent_frames += 1
            if started and silent_frames >= silence_limit:
                break
            if not started and time.time() - start_time > NO_SPEECH_TIMEOUT:
                return np.array([], dtype=np.int16)
    return np.concatenate(chunks) if chunks else np.array([], dtype=np.int16)


def transcribe(audio: np.ndarray) -> str:
    if audio.size == 0:
        return ""
    samples = audio.astype(np.float32) / 32768.0
    segments, _ = stt.transcribe(samples, language=None, vad_filter=True, beam_size=1)
    return " ".join(s.text.strip() for s in segments).strip()


def ask_jarvis(text: str) -> str:
    try:
        r = requests.post(
            WEBHOOK_URL,
            json={"text": text},
            headers={WEBHOOK_HEADER: WEBHOOK_KEY},
            timeout=120,
        )
        r.raise_for_status()
        return r.json().get("reply", "I got an empty reply.")
    except requests.exceptions.ConnectionError:
        return "I cannot reach n8n. Is it running?"
    except requests.exceptions.HTTPError as e:
        return f"n8n returned an error: {e.response.status_code}"
    except Exception as e:
        return f"Something went wrong: {e}"


def wake_detected(frame: np.ndarray) -> bool:
    scores = wake.predict(frame)
    return any("jarvis" in name and score >= WAKE_THRESHOLD for name, score in scores.items())


def main() -> None:
    print("Ready. Say 'Hey Jarvis'. Press Ctrl+C to quit.")
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME) as stream:
        while True:
            data, _ = stream.read(FRAME)
            if not wake_detected(data[:, 0]):
                continue

            wake.reset()
            print("Wake word heard. Listening...")
            speak("Yes?")
            stream.read(FRAME * 3)

            text = transcribe(record_request(stream))
            if not text:
                print("Heard nothing.")
                continue
            print("You:", text)

            speak(ask_jarvis(text))
            wake.reset()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye.")
# Jarvis Personal AI Assistant

> A self-hosted, privacy-first personal AI assistant running locally on Windows. Integrates voice control (wake word + offline STT/TTS), Telegram messaging, an n8n intelligent agent core with LLM fallback, and secure local PC automation.

---

## 📸 Overview

**Jarvis** is an extensible personal assistant designed to bridge local hardware control with cloud and local language models. It listens for spoken commands or Telegram messages, processes requests through an n8n-powered autonomous agent, queries productivity integrations (Gmail, Google Calendar, Google Sheets), and executes safe, whitelisted actions directly on your PC.

### Highlights
* **Hands-free Voice Loop:** Local wake word detection (*"Hey Jarvis"*), GPU-accelerated speech-to-text, and natural text-to-speech output.
* **Dual Input Interfaces:** Seamlessly control Jarvis via Telegram chat or local audio input.
* **Hybrid LLM Brain:** Powered primarily by Google Gemini Flash, automatically falling back to an offline local Ollama model (`qwen2.5:7b` / `qwen3.5:4b`) if Gemini is unreachable or rate-limited.
* **Secure PC Control:** Local REST API server enforcing strict action whitelisting for app execution, volume adjustment, desktop screenshots, clipboard reading, and screen locking.
* **Productivity Suite:** Read-only access to unread emails, daily calendar schedules, and job application tracking sheets.

---

## 🏗️ Architecture

```text
  Phone (Telegram)                    Microphone / Speaker
        |                                      |
  Telegram Bot API                    jarvis_voice.py
        |  (via ngrok HTTPS)          wake word -> Whisper -> HTTP
        v                                      |
  +--------------------------- n8n (local, port 5678) ----------------------------+
  |  Telegram Trigger / Voice Webhook -> Normalize Input -> Allowed? ->            |
  |  Jarvis Agent (Gemini, Ollama fallback, Memory, Tools) -> Clean Reply ->       |
  |  Telegram reply  OR  Respond to Webhook                                        |
  +--------------------------------------------------------------------------------+
        | tools                                   |
        v                                         v
  Gmail, Calendar, Google Sheets          pc_control_server.py (127.0.0.1:8787)
                                          whitelisted PC actions
```

---

## 🛠️ Stack & Technologies

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Workflow Engine** | [n8n](https://n8n.io/) (2.46.6+ via npm) | Coordinates agent logic, tool calls, and messaging routers |
| **Primary LLM** | Google Gemini Flash | Main reasoning engine for tool selection and conversation |
| **Fallback LLM** | [Ollama](https://ollama.com/) (`qwen2.5:7b`) | Offline/private LLM execution |
| **Wake Word** | [openWakeWord](https://github.com/dscripka/openWakeWord) (`hey_jarvis`) | Local background acoustic wake-word listener |
| **Speech-to-Text** | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (`medium`, CUDA) | Near-instant transcription using NVIDIA GPU acceleration |
| **Text-to-Speech** | [Piper TTS](https://github.com/rhasspy/piper) (`en_GB-alan-medium`) | Offline British male voice generation (fallback: Windows SAPI) |
| **PC Automation** | Python 3.12 + FastAPI + Uvicorn | Local security sandbox endpoint for hardware/OS commands |

---

## 📁 Repository Structure

```text
.
├── jarvis_agent_final.json     # Complete n8n workflow export
├── pc_control_server.py        # Local FastAPI server for PC control commands
├── jarvis_voice.py             # Voice listener & synthesizer pipeline
├── start_jarvis.ps1            # Launcher script to initialize all background services
├── en_GB-alan-medium.onnx      # Piper TTS model weight (download separately)
└── en_GB-alan-medium.onnx.json # Piper TTS model config (download separately)
```

---

## 🔒 Security Design

Security is built into every tier of Jarvis to prevent unauthorized access or command execution:

1. **User ID Allowlisting:** Telegram requests are filtered against your specific Telegram User ID inside the `Normalize Input` node.
2. **Key Separation:** 
   - `X-Jarvis-Key` authorizes the voice loop to post to the n8n HTTP webhook.
   - `X-Api-Key` authorizes n8n to call the local `pc_control_server.py`.
3. **Local Loopback Only:** `pc_control_server.py` binds exclusively to `127.0.0.1` and will refuse non-loopback connections.
4. **No Arbitrary Shell Execution:** Actions are strictly mapped to an immutable Python dictionary whitelist (`APPS`). Raw command-line injection is impossible by design.
5. **Read-Only Third-Party Scope:** Cloud tool integrations (Gmail, Calendar, Sheets) operate under read-only scopes.

---

## ⚡ Quick Setup & Installation

### Prerequisites
* **Operating System:** Windows 10/11 with an NVIDIA RTX GPU (for optimal STT performance).
* **Node.js:** v18 or v20.
* **Python:** 3.12 (Python 3.15 is currently not recommended due to missing prebuilt wheels).

### 1. Install Global Binaries & Models
```powershell
# Install n8n globally
npm install -g n8n

# Install Ollama and pull fallback model
ollama pull qwen2.5:7b

# Download Python 3.12 (if not already installed)
winget install Python.Python.3.12
```

### 2. Configure Python Virtual Environment
```powershell
# Navigate to directory and initialize venv
py -3.12 -m venv jarvis-env
.\jarvis-env\Scripts\Activate.ps1

# Upgrade pip and install machine learning / audio dependencies
python -m pip install --upgrade pip
python -m pip install numpy sounddevice requests faster-whisper openwakeword pyttsx3 piper-tts nvidia-cublas-cu12 nvidia-cudnn-cu12 fastapi uvicorn pyautogui pillow pyperclip pycaw comtypes

# Download British male voice model for Piper
python -m piper.download_voices en_GB-alan-medium
```

### 3. Generate API Keys
Generate two unique secrets for authentication:
```powershell
python -c "import secrets; print('Key:', secrets.token_urlsafe(32))"
```
* Assign **Key A** to `WEBHOOK_KEY` in `jarvis_voice.py` and the n8n Header Auth credential.
* Assign **Key B** to `API_KEY` in `pc_control_server.py` and the `X-Api-Key` header parameter in the n8n `pc_control` node.

### 4. Import & Configure Workflow
1. Open n8n (`http://localhost:5678`).
2. Go to **Workflows** -> **Import from File** -> Select `jarvis_agent_final.json`.
3. Link your Google Gemini, Ollama, Gmail, Calendar, Sheets, and Telegram API credentials.
4. Update your Telegram User ID inside the `Normalize Input` JavaScript node.
5. Toggle the workflow to **Active**.

---

## 🚀 Running Jarvis

Launch each component in a separate PowerShell session (or run `./start_jarvis.ps1`):

```powershell
# Session 1: n8n Workflow Engine
$env:WEBHOOK_URL="https://<your-ngrok-domain>/"
n8n start

# Session 2: Ngrok HTTPS Tunnel (for Telegram webhooks)
ngrok http --url=<your-ngrok-domain> 5678

# Session 3: PC Control Server
.\jarvis-env\Scripts\Activate.ps1
python pc_control_server.py

# Session 4: Real-time Voice Loop
.\jarvis-env\Scripts\Activate.ps1
python jarvis_voice.py
```

When `jarvis_voice.py` displays **`Ready. Say 'Hey Jarvis'`**, you can speak your command out loud or message your Telegram bot directly.

---

## 📋 Whitelisted PC Actions

| Command Key | Example Input | Performed Action |
| :--- | :--- | :--- |
| `open_app` | `"open notepad"`, `"launch vscode"` | Starts whitelisted application binary |
| `open_url` | `"open github.com"` | Opens default web browser to target URL |
| `screenshot` | `"take a screenshot"` | Saves PNG capture in `Pictures\Jarvis` |
| `volume` | `"set volume to 40"` | Adjusts Windows master audio level (0-100) |
| `clipboard_read`| `"what is in my clipboard?"` | Reads and returns text buffer |
| `lock` | `"lock my pc"` | Immediately locks Windows workstation |

---

## 🛣️ Roadmap

- [ ] Support sending captured screenshots back as images in Telegram.
- [ ] Implement persistent vector-store database (SQLite/ChromaDB) for long-term memory.
- [ ] Add explicit user-confirmation steps before executing write actions (sending emails, altering calendar events).
- [ ] Integrate local web search tool for live internet retrieval.
- [ ] Add auto-start Windows Service configuration.

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more details.
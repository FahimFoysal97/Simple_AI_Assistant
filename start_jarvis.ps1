# Jarvis launcher (Windows PowerShell)
# Starts n8n, ngrok, the PC control server and the voice loop, each in its own window.
#
# Usage (from PowerShell):   .\start_jarvis.ps1
# If scripts are blocked, run once:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# ----------------------------------------------------------------- settings
$Root      = "$HOME\Downloads"                       # folder with the .py files and jarvis-env
$Activate  = "$Root\jarvis-env\Scripts\Activate.ps1"
$NgrokHost = "oyster-blubber-sneer.ngrok-free.dev"   # your free static ngrok domain
$N8nPort   = 5678
$UseTelegram = $true                                 # set $false to skip ngrok (voice only)

# ----------------------------------------------------------------- 1. Ollama
# Ollama normally runs in the background on Windows. Quick check:
try { ollama list | Out-Null; Write-Host "Ollama: OK" } catch { Write-Host "Ollama not found. Start it from the Start menu." -ForegroundColor Yellow }

# ----------------------------------------------------------------- 2. n8n
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:WEBHOOK_URL='https://$NgrokHost/'; n8n start"
Write-Host "Starting n8n... waiting 25 seconds"
Start-Sleep -Seconds 25

# ----------------------------------------------------------------- 3. ngrok (Telegram only)
if ($UseTelegram) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "ngrok http --url=$NgrokHost $N8nPort"
    Start-Sleep -Seconds 5
}

# ----------------------------------------------------------------- 4. PC control server
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Root'; & '$Activate'; python pc_control_server.py"
Start-Sleep -Seconds 5

# ----------------------------------------------------------------- 5. Voice loop
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Root'; & '$Activate'; python jarvis_voice.py"

Write-Host ""
Write-Host "All components started. In n8n, make sure the Jarvis workflow is Active." -ForegroundColor Green
Write-Host "Wait for: Ready. Say 'Hey Jarvis'"

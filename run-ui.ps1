# run-ui.ps1 - levanta la interfaz web local (Gradio).
# Abre el navegador en http://127.0.0.1:7860. Ctrl+C para detener.
# Uso:  .\run-ui.ps1

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Host "Aviso: no hay .env - ejecuta .\install.ps1 o copia .env.example a .env" -ForegroundColor Yellow
    Write-Host "       y pon tus claves. El modo prueba solo necesita ANTHROPIC_API_KEY."
}

Write-Host "=== Escalator UI ===  http://127.0.0.1:7860  (Ctrl+C para salir)" -ForegroundColor Cyan
python -m escalator.ui
exit $LASTEXITCODE

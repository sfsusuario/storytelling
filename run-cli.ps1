# run-cli.ps1 - ejecuta el pipeline por linea de comandos con preguntas guiadas.
# Todos los valores tienen un valor por defecto: pulsa Enter para aceptarlo.
# Uso:  .\run-cli.ps1

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host "=== Escalator: generacion guiada ===" -ForegroundColor Cyan
Write-Host ""

# --- Imagen ----------------------------------------------------------------
$defaultImage = if (Test-Path "example.png") { "example.png" } else { "" }
$image = Read-Host "Imagen del retrato [$defaultImage]"
if (-not $image) { $image = $defaultImage }
if (-not $image -or -not (Test-Path $image)) {
    Write-Host "ERROR: no existe la imagen '$image'." -ForegroundColor Red
    exit 1
}

# --- Frase (obligatoria) ---------------------------------------------------
$phrase = Read-Host "Frase a escalar (p. ej. 'Shut that off')"
if (-not $phrase) {
    Write-Host "ERROR: la frase es obligatoria." -ForegroundColor Red
    exit 1
}

# --- Set de estilos --------------------------------------------------------
Write-Host ""
python -m escalator.cli --list-style-sets
Write-Host ""
$styleSet = Read-Host "Set de estilos (nombre / random / mix) [random]"
if (-not $styleSet) { $styleSet = "random" }

$seed = Read-Host "Seed para reproducibilidad (vacio = aleatorio)"

# --- Etapas y voz ----------------------------------------------------------
$stages = Read-Host "Numero de escenas (2-5) [5]"
if (-not $stages) { $stages = "5" }

$language = Read-Host "Idioma de textos y narracion (es/en/pt/fr...) [es]"
if (-not $language) { $language = "es" }

$voice = Read-Host "Voz del narrador [es-ES-AlvaroNeural, grave y pausada] (es-MX-JorgeNeural, en-US-ChristopherNeural...)"
if (-not $voice) { $voice = "es-ES-AlvaroNeural" }

# --- Formato ---------------------------------------------------------------
$fit = Read-Host "Relleno del encuadre vertical: crop (llena, TikTok) / blur (fondo difuminado) / pad (bandas) [crop]"
if (-not $fit) { $fit = "crop" }

# --- Modo prueba -----------------------------------------------------------
$test = Read-Host "Modo prueba? Sin imagenes IA, casi gratis (S/n) [S]"
$testMode = ($test -eq "" -or $test -match '^[sSyY]')

# --- Construir y ejecutar --------------------------------------------------
$cliArgs = @($image, $phrase, "--style-set", $styleSet, "--stages", $stages, "--voice", $voice, "--language", $language, "--fit", $fit)
if ($seed) { $cliArgs += @("--seed", $seed) }
if ($testMode) { $cliArgs += "--test-mode" }

Write-Host ""
Write-Host ("Ejecutando: escalate " + ($cliArgs -join " ")) -ForegroundColor DarkGray
Write-Host ""
python -m escalator.cli @cliArgs
exit $LASTEXITCODE

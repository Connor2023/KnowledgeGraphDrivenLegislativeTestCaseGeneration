# Load the credentials kg_testgen needs into the CURRENT PowerShell session.
#
# Dot-source it (note the leading dot and space) so the variables persist in your shell:
#
#     . .\setup_env.ps1
#
# Running it without the leading dot sets them in a child process that then exits,
# and your shell sees nothing.
#
# Reads Neo4j credentials straight from the file Aura generated, so the password is not
# duplicated anywhere. Reads the LLM key from your user environment. Nothing is printed.

param(
    [string]$CredsFile = "C:\Users\conno\FYP\KnowledgeGraph\Neo4j-e6598edc-Created-2026-08-11.txt"
)

if (-not (Test-Path $CredsFile)) {
    Write-Error "Aura credentials file not found: $CredsFile`nPass the path: . .\setup_env.ps1 -CredsFile 'C:\path\to\Neo4j-xxxx-Created-....txt'"
    return
}

Get-Content $CredsFile | ForEach-Object {
    if ($_ -match '^\s*(NEO4J_[A-Z_]+)\s*=\s*(.+?)\s*$') {
        Set-Item -Path ("env:" + $matches[1]) -Value $matches[2]
    }
}

if (-not $env:OPENAI_API_KEY) {
    $userKey = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "User")
    if (-not $userKey) { $userKey = [Environment]::GetEnvironmentVariable("OPENAI_KEY", "User") }
    if ($userKey) { $env:OPENAI_API_KEY = $userKey }
}

# Python UTF-8 mode: the corpus and generated Gherkin contain non-cp1252 characters.
$env:PYTHONUTF8 = "1"

# Report presence only -- never the values.
$report = @(
    @{ Name = "NEO4J_URI";      Set = [bool]$env:NEO4J_URI },
    @{ Name = "NEO4J_USERNAME"; Set = [bool]$env:NEO4J_USERNAME },
    @{ Name = "NEO4J_PASSWORD"; Set = [bool]$env:NEO4J_PASSWORD },
    @{ Name = "NEO4J_DATABASE"; Set = [bool]$env:NEO4J_DATABASE },
    @{ Name = "OPENAI_API_KEY"; Set = [bool]$env:OPENAI_API_KEY }
)
foreach ($r in $report) {
    $status = if ($r.Set) { "set" } else { "MISSING" }
    "{0,-16} {1}" -f $r.Name, $status
}

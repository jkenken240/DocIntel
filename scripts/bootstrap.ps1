[CmdletBinding()]
param(
    [Parameter()]
    [string]$DataRoot = "E:\DocIntelData"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([Parameter(Mandatory)][string]$Message)

    Write-Host "[DocIntel] $Message"
}

try {
    $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
    $examplePath = Join-Path $repoRoot ".env.example"
    $environmentPath = Join-Path $repoRoot ".env"

    if (-not [System.IO.Path]::IsPathRooted($DataRoot)) {
        throw "DataRoot must be an absolute path. Received: $DataRoot"
    }

    $resolvedDataRoot = [System.IO.Path]::GetFullPath($DataRoot).TrimEnd('\', '/')
    $dataDrive = [System.IO.Path]::GetPathRoot($resolvedDataRoot)
    if ($dataDrive -and $dataDrive.TrimEnd('\', '/').Equals("C:", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Persistent DocIntel data may not be placed on C:. Choose E:\DocIntelData or another explicit non-C: root."
    }

    if (-not (Test-Path -LiteralPath $examplePath -PathType Leaf)) {
        throw "Missing environment template: $examplePath"
    }

    foreach ($commandName in @("git", "docker")) {
        if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) {
            throw "Required command '$commandName' was not found on PATH."
        }
    }

    Write-Step "Checking Docker Compose and the Linux Docker engine."
    & docker compose version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose is unavailable. Install or enable the Docker Compose plugin."
    }

    $dockerOs = (& docker info --format '{{.OSType}}' 2>$null).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Engine is not reachable. Start Docker Desktop and retry."
    }
    if ($dockerOs -ne "linux") {
        throw "DocIntel requires the Linux Docker engine; Docker reported '$dockerOs'."
    }

    Write-Step "Creating required data directories beneath $resolvedDataRoot."
    foreach ($directoryName in @("postgres", "uploads", "processed", "samples", "backups")) {
        $directoryPath = Join-Path $resolvedDataRoot $directoryName
        New-Item -ItemType Directory -Path $directoryPath -Force | Out-Null
    }

    if (Test-Path -LiteralPath $environmentPath -PathType Leaf) {
        Write-Step ".env already exists; preserving it without changes."
    }
    else {
        $environmentText = [System.IO.File]::ReadAllText($examplePath)
        $composeRoot = $resolvedDataRoot.Replace('\', '/')
        $environmentText = [System.Text.RegularExpressions.Regex]::Replace(
            $environmentText,
            '(?m)^DOCINTEL_DATA_ROOT=.*$',
            "DOCINTEL_DATA_ROOT=$composeRoot"
        )
        foreach ($directoryName in @("uploads", "processed", "samples", "backups")) {
            $variableName = "DOCINTEL_{0}_PATH" -f $directoryName.ToUpperInvariant()
            $environmentText = [System.Text.RegularExpressions.Regex]::Replace(
                $environmentText,
                "(?m)^$variableName=.*$",
                "$variableName=$composeRoot/$directoryName"
            )
        }
        [System.IO.File]::WriteAllText(
            $environmentPath,
            $environmentText,
            [System.Text.UTF8Encoding]::new($false)
        )
        Write-Step "Created .env from .env.example."
    }

    Write-Step "Bootstrap complete. Persistent data root: $resolvedDataRoot"
    Write-Step "Start DocIntel with: docker compose up --build -d"
}
catch {
    Write-Error "DocIntel bootstrap failed: $($_.Exception.Message)"
    exit 1
}

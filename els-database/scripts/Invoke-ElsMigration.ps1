<#
.SYNOPSIS
    Runs Flyway against one schema's migrations, using connection details from a local config file.

.DESCRIPTION
    Thin wrapper around the Flyway command-line tool. It never stores or hardcodes credentials: it
    reads them from a JSON config file that is gitignored (see config/config.template.json for the
    expected shape and config/.gitignore for the rule that keeps real configs out of the repo),
    builds the SQL Server JDBC URL and Flyway arguments from it, and invokes `flyway`.

    Flyway is run scoped to exactly one schema per invocation, matching how Flyway itself handles
    multiple schemas: each run gets its own flyway_schema_history tracking table, created inside
    whichever schema was targeted. Running -Schema utils and -Schema els are genuinely independent
    histories — there's no need to run them together or in a fixed order, beyond utils needing to
    exist before anything in els depends on it.

    Named "Invoke-" rather than "Deploy-" because PowerShell only recognizes a fixed list of
    "approved verbs" for scripts/functions (see Get-Verb) — "Deploy" isn't one of them, and using an
    unapproved verb triggers a warning if this is ever turned into a module function. "Invoke" is the
    closest approved verb for "run this external tool."

.PARAMETER Schema
    Which schema to run Flyway against. Must match a key under the config file's flyway.schemas
    object (e.g. "utils" or "els"). Required — there's no default, so a run always states which
    schema it targets rather than silently defaulting to one.

.PARAMETER ConfigPath
    Path to the JSON config file to read. Defaults to config/config.json next to this script's repo.

.PARAMETER FlywayCommand
    Which Flyway command to run. Defaults to "migrate".

.EXAMPLE
    ./scripts/Invoke-ElsMigration.ps1 -Schema utils
    Runs `flyway migrate` against the "utils" schema's migrations.

.EXAMPLE
    ./scripts/Invoke-ElsMigration.ps1 -Schema els
    Runs `flyway migrate` against the "els" schema's migrations. Safe to run as often as you like —
    only re-run -Schema utils when something under migrations/utils actually changes.

.EXAMPLE
    ./scripts/Invoke-ElsMigration.ps1 -Schema els -FlywayCommand info
    Shows pending/applied migrations for "els" without changing anything.

.EXAMPLE
    ./scripts/Invoke-ElsMigration.ps1 -Schema els -ConfigPath ./config/config.local.json
    Uses an alternate config file, e.g. for a second local environment.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Schema,

    [string]$ConfigPath = (Join-Path $PSScriptRoot "..\config\config.json"),

    [ValidateSet("migrate", "info", "validate", "repair", "baseline")]
    [string]$FlywayCommand = "migrate"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command flyway -ErrorAction SilentlyContinue)) {
    throw "flyway was not found on PATH. Install the Flyway command-line tool and add it to PATH first."
}

if (-not (Test-Path $ConfigPath)) {
    throw "Config file not found at '$ConfigPath'. Copy config/config.template.json to config/config.json (or another gitignored name) and fill in real values first."
}

$config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json

$sqlServer = $config.sqlServer
$auth = $config.auth
$schemaConfig = $config.flyway.schemas.$Schema

if (-not $schemaConfig) {
    $knownSchemas = $config.flyway.schemas.PSObject.Properties.Name -join ", "
    throw "Schema '$Schema' is not defined under flyway.schemas in '$ConfigPath'. Known schemas: $knownSchemas"
}

if ([string]::IsNullOrWhiteSpace($sqlServer.instanceName)) {
    $serverPart = "$($sqlServer.host):$($sqlServer.port)"
} else {
    $serverPart = "$($sqlServer.host)\$($sqlServer.instanceName)"
}

$encrypt = $sqlServer.encrypt.ToString().ToLower()
$trustCert = $sqlServer.trustServerCertificate.ToString().ToLower()
$jdbcUrl = "jdbc:sqlserver://$serverPart;databaseName=$($sqlServer.database);encrypt=$encrypt;trustServerCertificate=$trustCert"

$migrationsPath = Resolve-Path (Join-Path $PSScriptRoot $schemaConfig.migrationsPath)

Write-Host "Running 'flyway $FlywayCommand' against database '$($sqlServer.database)' on $serverPart (schema: $Schema)"

& flyway $FlywayCommand `
    "-url=$jdbcUrl" `
    "-user=$($auth.user)" `
    "-password=$($auth.password)" `
    "-schemas=$Schema" `
    "-locations=filesystem:$migrationsPath"

if ($LASTEXITCODE -ne 0) {
    throw "flyway $FlywayCommand failed with exit code $LASTEXITCODE"
}

Write-Host "flyway $FlywayCommand completed successfully."

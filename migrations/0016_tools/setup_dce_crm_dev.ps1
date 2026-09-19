<#
.SYNOPSIS
  Builds (or refreshes) a DEV-ONLY copy of dce_crm so the anon -> service-key swap
  can be rehearsed against the DEV Supabase project, never against prod.

.DESCRIPTION
  * Clones the committed code of dce_crm into a sibling folder (dce_crm_dev) and removes
    that clone's git remote, so nothing there can be pushed anywhere.
  * Writes dce_crm_dev\.streamlit\secrets.toml. The dev URL and key are read from the
    API repo's .env WITHOUT printing them. Only key NAMES, kinds and lengths are shown.
  * Prod's SMTP / Groq credentials are NEVER copied. They are replaced with dummies
    (email and AI calls simply fail) unless you opt in with -EnableEmail, which prompts
    (hidden) for a DEV sender Gmail account + app password. The daily-report recipient
    list is always forced to -Recipient (your own address).
  * Checks `git check-ignore -v` on the secrets path BEFORE writing and `git status`
    after; aborts if the file would not be ignored or the clone is not clean.
  * Read-only towards prod: it only READS dce_crm\.streamlit\secrets.toml (for the
    comparison guards and the non-secret college settings) and clones committed code.

  Stage 1 = DEV anon (publishable) key  -> baseline, same as today's behaviour.
  Stage 2 = DEV secret key              -> rehearsal for the prod service_role swap.
  Re-run with the other -Stage to switch; restart streamlit / scheduler afterwards.

.EXAMPLE
  # If script execution is blocked, prefix with:  powershell -ExecutionPolicy Bypass -File
  .\migrations\0016_tools\setup_dce_crm_dev.ps1 -Recipient me@example.com
  .\migrations\0016_tools\setup_dce_crm_dev.ps1 -Recipient me@example.com -Stage 2
  .\migrations\0016_tools\setup_dce_crm_dev.ps1 -Recipient me@example.com -EnableEmail
#>
[CmdletBinding()]
param(
    [ValidateSet(1, 2)] [int] $Stage = 1,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$')] [string] $Recipient,

    [switch] $EnableEmail,
    [switch] $SkipVenv,

    [string] $ApiDir  = '',
    [string] $ProdDir = '',
    [string] $DevDir  = ''
)

$ErrorActionPreference = 'Stop'

# Defaults are resolved here, not in param(): $PSScriptRoot is empty inside param() defaults in Windows PowerShell 5.1.
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $ApiDir)  { $ApiDir  = (Resolve-Path (Join-Path $scriptDir '../..')).Path }
if (-not $ProdDir) { $ProdDir = Join-Path (Split-Path -Parent $ApiDir) 'dce_crm' }
if (-not $DevDir)  { $DevDir  = Join-Path (Split-Path -Parent $ApiDir) 'dce_crm_dev' }

function Fail([string]$Message) { Write-Host "ABORT: $Message" -ForegroundColor Red; exit 1 }
function Step([string]$Message) { Write-Host "`n=== $Message" -ForegroundColor Cyan }

# name = value lines (.env or simple TOML). Values are returned, never printed.
function Read-KeyValueFile([string]$Path) {
    $h = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*#') { continue }
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $name = $Matches[1]; $v = $Matches[2]
            if ($v -match '^"(.*)"$') { $v = $Matches[1] }
            elseif ($v -match "^'(.*)'$") { $v = $Matches[1] }
            $h[$name] = $v
        }
    }
    return $h
}

function Get-KeyInfo([string]$Key) {
    if ($Key -like 'sb_publishable_*') { return @{ Kind = 'sb_publishable'; Role = 'anon' } }
    if ($Key -like 'sb_secret_*')      { return @{ Kind = 'sb_secret'; Role = 'service_role' } }
    $parts = $Key.Split('.')
    if ($parts.Count -eq 3) {
        try {
            $p = $parts[1].Replace('-', '+').Replace('_', '/')
            switch ($p.Length % 4) { 2 { $p += '==' } 3 { $p += '=' } }
            $role = ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($p)) | ConvertFrom-Json).role
            return @{ Kind = 'jwt'; Role = $role }
        } catch { }
    }
    return @{ Kind = 'unknown'; Role = $null }
}

function Toml([string]$s) { return '"' + $s.Replace('\', '\\').Replace('"', '\"') + '"' }
function Norm-Url([string]$u) { return $u.Trim().TrimEnd('/').ToLowerInvariant() }

function Git-Run([string[]]$GitArgs) {
    # 'Continue' inside: Windows PowerShell 5.1 turns native stderr text (e.g. CRLF warnings) into terminating errors under 'Stop'
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { $out = & git @GitArgs 2>&1; $rc = $LASTEXITCODE } finally { $ErrorActionPreference = $old }
    return @{ Out = @($out | ForEach-Object { "$_" }); Rc = $rc }
}

function Read-Hidden([string]$Prompt) {
    $sec = Read-Host $Prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

# ---------------------------------------------------------------- 0. preconditions
Step "0. Preconditions (Stage $Stage)"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'git is not on PATH.' }
$envFile     = Join-Path $ApiDir '.env'
$prodSecrets = Join-Path $ProdDir '.streamlit/secrets.toml'
foreach ($path in @($envFile, $prodSecrets)) { if (-not (Test-Path -LiteralPath $path)) { Fail "Missing file: $path" } }
if (-not (Test-Path -LiteralPath (Join-Path $ProdDir '.git'))) { Fail "$ProdDir is not a git repository." }
$resolvedDev = [IO.Path]::GetFullPath($DevDir).TrimEnd('\', '/')
foreach ($other in @($ProdDir, $ApiDir)) {
    if ($resolvedDev -ieq [IO.Path]::GetFullPath($other).TrimEnd('\', '/')) { Fail "DevDir must not be $other" }
}
Write-Host "API repo : $ApiDir"
Write-Host "prod copy: $ProdDir   (READ-ONLY here)"
Write-Host "dev copy : $DevDir"
Write-Host "recipient: $Recipient   (the only report recipient the dev copy will have)"

# ---------------------------------------------------------------- 1. read config silently
Step '1. Read DEV settings from the API .env (values are NOT printed)'
$e = Read-KeyValueFile $envFile
$p = Read-KeyValueFile $prodSecrets
foreach ($k in 'DEV_SUPABASE_URL', 'DEV_SUPABASE_KEY', 'DEV_SUPABASE_ANON_KEY', 'PROD_SUPABASE_URL') {
    if (-not $e.ContainsKey($k) -or [string]::IsNullOrWhiteSpace($e[$k])) { Fail "$k is missing/empty in $envFile" }
}
$devUrl = $e['DEV_SUPABASE_URL']
if ($devUrl -notmatch '^https://[a-z0-9]+\.supabase\.co/?$') { Fail 'DEV_SUPABASE_URL does not look like a Supabase project URL.' }
$prodUrls = @($e['PROD_SUPABASE_URL'], $p['SUPABASE_URL']) | Where-Object { $_ }
if ($prodUrls | Where-Object { (Norm-Url $_) -eq (Norm-Url $devUrl) }) { Fail 'The DEV URL equals a PROD URL. Refusing.' }

$keyName = if ($Stage -eq 1) { 'DEV_SUPABASE_ANON_KEY' } else { 'DEV_SUPABASE_KEY' }
$wantRole = if ($Stage -eq 1) { 'anon' } else { 'service_role' }
$devKey = $e[$keyName]
$info = Get-KeyInfo $devKey
if ($info.Role -ne $wantRole) { Fail "$keyName is kind '$($info.Kind)' role '$($info.Role)', expected role '$wantRole'." }
$prodKeys = @($e['PROD_SUPABASE_KEY'], $e['PROD_SUPABASE_ANON_KEY'], $p['SUPABASE_KEY']) | Where-Object { $_ }
if ($prodKeys | Where-Object { $_ -ceq $devKey }) { Fail "$keyName equals a PROD key. Refusing." }
Write-Host ("using .env name {0} -> kind {1}, role {2}, length {3}  (value never printed)" -f $keyName, $info.Kind, $info.Role, $devKey.Length)
Write-Host ("dev URL host: {0}   (differs from prod: True)" -f ([Uri]$devUrl).Host)

# ---------------------------------------------------------------- 2. optional dev-only email credentials
$sender = 'dev-email-disabled@invalid.example'
$senderPass = 'DEV-EMAIL-DISABLED'
if ($EnableEmail) {
    Step '2. DEV email sender (typed now, hidden; never copied from prod)'
    $sender = (Read-Host 'DEV sender Gmail address').Trim()
    if ($sender -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') { Fail 'Sender is not an e-mail address.' }
    if ($p['GMAIL_ADDRESS'] -and ($sender -ieq $p['GMAIL_ADDRESS'])) { Fail 'That is the PROD sender account. Use a different one.' }
    $senderPass = Read-Hidden 'Gmail app password for that sender'
    if ([string]::IsNullOrWhiteSpace($senderPass)) { Fail 'Empty app password.' }
} else {
    Step '2. Email disabled (dummy SMTP credentials) - re-run with -EnableEmail to test sending to yourself'
}

# ---------------------------------------------------------------- 3. dev copy of the code
Step '3. Dev copy of dce_crm (committed code only, no remote)'
if (-not (Test-Path -LiteralPath $DevDir)) {
    $r = Git-Run @('clone', '--quiet', '--no-hardlinks', $ProdDir, $DevDir)
    if ($r.Rc -ne 0) { Fail ("git clone failed: " + ($r.Out -join ' ')) }
    Write-Host "cloned $ProdDir -> $DevDir"
} else {
    $r = Git-Run @('-C', $DevDir, 'rev-parse', '--is-inside-work-tree')
    if ($r.Rc -ne 0) { Fail "$DevDir exists but is not a git work tree." }
    Write-Host "reusing existing $DevDir"
}
$r = Git-Run @('-C', $DevDir, 'remote')
foreach ($remote in ($r.Out | Where-Object { $_ })) {
    [void](Git-Run @('-C', $DevDir, 'remote', 'remove', $remote))
    Write-Host "removed git remote '$remote' from the dev copy (it can never push)"
}
$r = Git-Run @('-C', $DevDir, 'log', '-1', '--oneline')
Write-Host ("dev copy HEAD: " + ($r.Out -join ' '))

# ---------------------------------------------------------------- 4. gitignore check BEFORE writing
Step '4. git check-ignore BEFORE writing the secrets file'
$rel = '.streamlit/secrets.toml'
$r = Git-Run @('-C', $DevDir, 'check-ignore', '-v', $rel)
if ($r.Rc -ne 0) { Fail "$rel is NOT ignored by git in the dev copy. Not writing secrets." }
Write-Host ($r.Out -join "`n")

# ---------------------------------------------------------------- 5. write secrets.toml
Step '5. Write dev secrets.toml (no BOM)'
$copyKeys = 'DAILY_REPORT_TIME', 'COLLEGE_NAME', 'COLLEGE_SHORT', 'COLLEGE_CITY', 'ACADEMIC_YEAR'   # non-secret settings only
$copied = @()
foreach ($k in $copyKeys) {
    $raw = Get-Content -LiteralPath $prodSecrets | Where-Object { $_ -match ('^\s*' + $k + '\s*=') } | Select-Object -First 1
    if (-not $raw) { Fail "Prod secrets.toml has no $k line to copy." }
    $copied += $raw.Trim()
}
$lines = @(
    "# DEV-ONLY dce_crm secrets. Generated by setup_dce_crm_dev.ps1 (Stage $Stage). Gitignored. Never use against prod.",
    ('SUPABASE_URL = ' + (Toml $devUrl)),
    ('SUPABASE_KEY = ' + (Toml $devKey)),
    ('GROQ_API_KEY = ' + (Toml 'DEV-DUMMY-NOT-A-REAL-KEY')),
    ('GMAIL_ADDRESS = ' + (Toml $sender)),
    ('GMAIL_APP_PASS = ' + (Toml $senderPass)),
    ('DAILY_REPORT_RECIPIENTS = [' + (Toml $Recipient) + ']')
) + $copied
$target = Join-Path $DevDir '.streamlit/secrets.toml'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
[IO.File]::WriteAllText($target, (($lines -join "`n") + "`n"), (New-Object Text.UTF8Encoding($false)))
Write-Host "wrote $target"

# ---------------------------------------------------------------- 6. verify: names only, ignore, clean status
Step '6. Verify (key NAMES, kinds, lengths only)'
$w = Read-KeyValueFile $target
foreach ($k in $w.Keys | Sort-Object) {
    $len = "$($w[$k])".Length
    if ($k -eq 'SUPABASE_KEY') {
        $i = Get-KeyInfo $w[$k]; Write-Host ("  {0,-24} kind={1} role={2} length={3}" -f $k, $i.Kind, $i.Role, $len)
    } elseif ($k -in @('SUPABASE_URL', 'COLLEGE_NAME', 'COLLEGE_SHORT', 'COLLEGE_CITY', 'ACADEMIC_YEAR', 'DAILY_REPORT_TIME')) {
        Write-Host ("  {0,-24} (config value, length {1})" -f $k, $len)
    } else {
        Write-Host ("  {0,-24} (hidden, length {1})" -f $k, $len)
    }
}
$recipLine = ($lines | Where-Object { $_ -like 'DAILY_REPORT_RECIPIENTS*' })
Write-Host ("  DAILY_REPORT_RECIPIENTS entries: 1 -> exactly {0}" -f $Recipient)
if ($recipLine -notmatch [regex]::Escape((Toml $Recipient))) { Fail 'Recipient list is not the forced recipient.' }
if ($w['GROQ_API_KEY'] -notlike 'DEV-DUMMY*') { Fail 'GROQ key is not the dummy.' }
if (-not $EnableEmail -and $w['GMAIL_APP_PASS'] -ne 'DEV-EMAIL-DISABLED') { Fail 'SMTP password is not the dummy.' }

$r = Git-Run @('-C', $DevDir, 'check-ignore', '-v', $rel)
if ($r.Rc -ne 0) { Fail 'secrets.toml is not git-ignored after writing.' }
Write-Host ("check-ignore after: " + ($r.Out -join ' '))
$tracked = Git-Run @('-C', $DevDir, 'ls-files')
if ($tracked.Out | Where-Object { $_ -match 'secrets' }) { Fail 'A secrets file is tracked in the dev copy.' }
$st = Git-Run @('-C', $DevDir, 'status', '--short')
if ($st.Out | Where-Object { $_ }) { Write-Host 'git status --short:'; $st.Out | ForEach-Object { Write-Host "  $_" }; Fail 'Dev copy is not clean.' }
Write-Host 'git status --short: (empty) -> working tree CLEAN'

# ---------------------------------------------------------------- 7. isolated venv + supabase-py check
if ($SkipVenv) {
    Step '7. venv skipped (-SkipVenv)'
} else {
    Step '7. Dev venv (isolated) + supabase-py check'
    $venv = Join-Path $DevDir '.venv'
    $py = Join-Path $venv 'Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $py)) { & python -m venv $venv; if ($LASTEXITCODE -ne 0) { Fail 'python -m venv failed.' } }
    & $py -m pip install --quiet --disable-pip-version-check -r (Join-Path $DevDir 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { Fail 'pip install -r requirements.txt failed.' }
    $test = Join-Path $env:TEMP 'dce_dev_keytest.py'
    @'
import os, importlib.metadata as m
from supabase import create_client
v = m.version("supabase")
try:
    create_client(os.environ["DCE_T_URL"], os.environ["DCE_T_KEY"])
    print(f"supabase-py {v}: client constructs OK with this key type (no network call made)")
except Exception as ex:
    print(f"supabase-py {v}: REJECTED this key ({type(ex).__name__}: {str(ex)[:60]}) -> needs supabase>=2.17")
    raise SystemExit(3)
'@ | Set-Content -LiteralPath $test -Encoding ASCII
    $env:DCE_T_URL = $devUrl; $env:DCE_T_KEY = $devKey
    try { & $py $test; $rc = $LASTEXITCODE } finally { Remove-Item Env:DCE_T_URL, Env:DCE_T_KEY -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $test -ErrorAction SilentlyContinue }
    if ($rc -ne 0) { Fail 'The installed supabase-py cannot use this key type. Upgrade it in the dev venv first.' }
}

Step "Done - dev copy is on STAGE $Stage ($($info.Kind) key)"
Write-Host @"
Run the dev app (from the dev copy; st.secrets reads .streamlit\secrets.toml of the CURRENT folder):
    cd "$DevDir"
    .\.venv\Scripts\streamlit run app.py
Daily-report scheduler (separate process, same folder):
    .\.venv\Scripts\python scheduler.py
Switch stage: re-run this script with -Stage 1|2, then RESTART streamlit and the scheduler.
Nothing here touched prod, the prod copy's files, or any migration.
"@

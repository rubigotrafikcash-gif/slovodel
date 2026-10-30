# Windows entry point: locate a working Python before running the checked workflow.
# No installation, downloads, execution-policy changes, or persistent settings.
[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Python,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$WorkflowArguments
)

$ErrorActionPreference = 'Stop'
# Keep a Core exit code such as 5 from becoming a PowerShell exception/exit 8.
# Script scope only; the caller's preference and system policy are unchanged.
$PSNativeCommandUseErrorActionPreference = $false

function Find-WorkingPython {
    param([string]$Executable, [string[]]$Prefix = @())
    if (-not [IO.Path]::IsPathRooted($Executable) -or
        $Executable -match '(?i)[\\/]Microsoft[\\/]WindowsApps[\\/]' -or
        -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $null }

    $process = New-Object System.Diagnostics.Process
    try {
        $start = New-Object System.Diagnostics.ProcessStartInfo
        $start.FileName = $Executable
        # Prefix is either empty or the fixed py launcher selector -3.
        $probe = "import json,sys;print(json.dumps({'version':list(sys.version_info[:3]),'executable':sys.executable}))"
        $start.Arguments = (($Prefix + @('-I', '-B', '-c', ('"' + $probe + '"'))) -join ' ')
        $start.UseShellExecute = $false
        $start.CreateNoWindow = $true
        $start.RedirectStandardOutput = $true
        $start.RedirectStandardError = $true
        $process.StartInfo = $start
        if (-not $process.Start()) { return $null }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(5000)) {
            $process.Kill()
            $process.WaitForExit()
            return $null
        }
        if ($process.ExitCode -ne 0) { return $null }
        $info = $stdout.GetAwaiter().GetResult() | ConvertFrom-Json
        if ($info.version.Count -ne 3 -or $info.version[0] -ne 3 -or $info.version[1] -lt 10) { return $null }
        $actual = [string]$info.executable
        if (-not [IO.Path]::IsPathRooted($actual) -or
            $actual -match '(?i)[\\/]Microsoft[\\/]WindowsApps[\\/]' -or
            -not (Test-Path -LiteralPath $actual -PathType Leaf)) { return $null }
        return $actual
    }
    catch { return $null }
    finally { $process.Dispose() }
}

try {
    $selected = $null
    # A host-provided path or deliberate override must work; do not silently ignore it.
    $explicit = if ($Python) { $Python } else { $env:SLOVODEL_PYTHON }
    if ($explicit) {
        $selected = Find-WorkingPython -Executable $explicit
        if (-not $selected) { throw 'SLOVODEL_ERROR: REQUESTED_PYTHON_UNAVAILABLE_OR_UNSUPPORTED' }
    }
    else {
        # This bundled-runtime location is a fallback, not an OpenAI API contract.
        # Prefer -Python with a path returned by the host dependency tool when available.
        $runtimeUserDir = [Environment]::GetFolderPath('UserProfile')
        if ($runtimeUserDir) {
            $bundled = Join-Path $runtimeUserDir '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
            $selected = Find-WorkingPython -Executable $bundled
        }
        if (-not $selected) {
            foreach ($name in @('python', 'python3', 'py')) {
                foreach ($command in @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
                    $prefix = if ($name -eq 'py') { @('-3') } else { @() }
                    $selected = Find-WorkingPython -Executable $command.Source -Prefix $prefix
                    if ($selected) { break }
                }
                if ($selected) { break }
            }
        }
        if (-not $selected) { throw 'SLOVODEL_ERROR: NO_WORKING_PYTHON_3_10_PLUS' }
    }
    $script = Join-Path $PSScriptRoot 'check_workflow.py'
    [Console]::Error.WriteLine('SLOVODEL_PYTHON: ' + $selected)
    & $selected -B $script @WorkflowArguments
    exit $LASTEXITCODE
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 8
}

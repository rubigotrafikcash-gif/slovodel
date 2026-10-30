# Прямой резервный запуск Python в Windows

Применяй, если инструмент получения runtime недоступен/вернул ошибку либо PS1
запрещён, а обычный запуск программ из PowerShell разрешён. Это обычные команды
текущего инструмента исполнения: PS1 не загружается, политика не изменяется.
Запрещённый самой средой запуск программ не обходи.

Выполни следующий блок для выбора и проверки встроенного Python. Путь строится
из профиля текущего пользователя, а не запрашивается у него. Стандартная папка —
резервная эвристика, не API OpenAI. Сохрани stdout/stderr и результат пробы
в журнал попыток. Не вычисляй путь через `rust.cache` или имя другого пользователя.

```powershell
$runtimePython = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if ($env:SLOVODEL_PYTHON) { $runtimePython = $env:SLOVODEL_PYTHON }
if (-not [IO.Path]::IsPathRooted($runtimePython) -or $runtimePython -match '(?i)[\\/]Microsoft[\\/]WindowsApps[\\/]' -or -not (Test-Path -LiteralPath $runtimePython -PathType Leaf)) { throw 'SLOVODEL_ERROR: DIRECT_PYTHON_UNAVAILABLE' }
$runtimeStart = New-Object System.Diagnostics.ProcessStartInfo
$runtimeStart.FileName = $runtimePython
$runtimeStart.Arguments = '-I -B -c "import sys;print(sys.executable);print(sys.version.split()[0]);sys.exit(0 if sys.version_info[0]==3 and sys.version_info[1]>=10 else 8)"'
$runtimeStart.UseShellExecute = $false
$runtimeStart.CreateNoWindow = $true
$runtimeProbe = New-Object System.Diagnostics.Process
$runtimeProbe.StartInfo = $runtimeStart
try {
    if (-not $runtimeProbe.Start()) { throw 'SLOVODEL_ERROR: DIRECT_PYTHON_START_FAILED' }
    if (-not $runtimeProbe.WaitForExit(5000)) { $runtimeProbe.Kill(); $runtimeProbe.WaitForExit(); throw 'SLOVODEL_ERROR: DIRECT_PYTHON_PROBE_TIMEOUT' }
    if ($runtimeProbe.ExitCode -ne 0) { throw 'SLOVODEL_ERROR: DIRECT_PYTHON_UNSUPPORTED' }
} finally { $runtimeProbe.Dispose() }
```

После успешной пробы вызывай **`check_workflow.py` из фактически прочитанной
папки навыка**, используя `& $runtimePython -B <полный путь check_workflow.py>`
и обычные аргументы режима. Исходник, редакцию и новый output-dir агент создаёт
в рабочем каталоге. Код `$LASTEXITCODE` сохрани сразу после вызова: это код
проверяющего запускателя; настоящий код Core находится в `execution.json`.
Сверь оба, а также `python_executable`, `python_version` и входные хеши.

Пробы не запускают Core и не равны выполнению проверки. После кода 5 или 7
не меняй путь Python ради другого результата. При недоступной резервной папке
используй другой интерпретатор, который реально предоставляет текущая среда,
с такой же проверкой; если такого нет, сообщи конкретный сбой. Не устанавливай
Python и зависимости и не меняй PATH или права без отдельной задачи.

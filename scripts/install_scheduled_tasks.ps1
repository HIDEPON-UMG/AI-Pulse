param([ValidateSet('Status','Migrate')][string]$Mode='Status')

$ErrorActionPreference='Stop'
$OutputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$repoRoot=Split-Path -Parent $PSScriptRoot
$launcher=Join-Path $PSScriptRoot 'ai_pulse_task_launcher.pyw'
$pythonw=Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'Programs\Python') -Filter pythonw.exe -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\WindowsApps\\' -and $_.FullName -match '\\Python\d+\\pythonw\.exe$' } |
    Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) { throw '実体の pythonw.exe が見つかりません。' }

$targets=[ordered]@{
    'AI-Pulse NotebookLM auth refresh'='auth'
    'AI-Pulse 日次バッチ'='daily'
    'AI-Pulse 週次バッチ'='weekly'
}
$rows=@()
foreach($name in $targets.Keys){
    $task=Get-ScheduledTask -TaskName $name -ErrorAction Stop
    if($Mode -eq 'Migrate'){
        $action=New-ScheduledTaskAction -Execute $pythonw -Argument "`"$launcher`" $($targets[$name])" -WorkingDirectory $repoRoot
        Set-ScheduledTask -TaskName $name -Action $action | Out-Null
        $task=Get-ScheduledTask -TaskName $name
    }
    $rows += [pscustomobject]@{task=$name;state=[string]$task.State;enabled=$task.Settings.Enabled;execute=$task.Actions[0].Execute}
}
$rows|ConvertTo-Json

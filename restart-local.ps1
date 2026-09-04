$ErrorActionPreference='Stop'
$root='D:\aegisgrid'
$apiPid=(Get-NetTCPConnection -State Listen -LocalPort 8001).OwningProcess
$webPid=(Get-NetTCPConnection -State Listen -LocalPort 3000).OwningProcess
$api=(Get-CimInstance Win32_Process -Filter "ProcessId=$apiPid").CommandLine
$web=(Get-CimInstance Win32_Process -Filter "ProcessId=$webPid").CommandLine
if ($api -notlike '*aegisgrid*' -and $api -notlike '*resume-electric-runtime.py*') { throw 'Port 8001 is not AegisGrid' }
if ($web -notlike '*aegisgrid*next*') { throw 'Port 3000 is not AegisGrid' }
Invoke-RestMethod 'http://127.0.0.1:8001/operations' | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath "$root\backend\data\local-runtime-recovery.json" -Encoding utf8
Stop-Process -Id $apiPid
Stop-Process -Id $webPid
Start-Process "$root\.venv\Scripts\python.exe" -ArgumentList @("$root\backend\run_local.py") -WorkingDirectory "$root\backend" -WindowStyle Hidden -RedirectStandardOutput "$root\backend\local-api.log" -RedirectStandardError "$root\backend\local-api-error.log"
Start-Process 'C:\Program Files\nodejs\node.exe' -ArgumentList @("$root\web\node_modules\next\dist\bin\next",'start','--hostname','127.0.0.1','--port','3000') -WorkingDirectory "$root\web" -WindowStyle Hidden -RedirectStandardOutput "$root\web\local-web.log" -RedirectStandardError "$root\web\local-web-error.log"
Write-Output 'AegisGrid restarted entirely from D:\aegisgrid.'

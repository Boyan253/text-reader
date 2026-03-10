$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$shortcut = "$env:USERPROFILE\Desktop\Text Reader.lnk"

if (-Not (Test-Path $shortcut)) {
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut($shortcut)
    $s.TargetPath = Join-Path $dir "start.bat"
    $s.WorkingDirectory = $dir
    $s.IconLocation = Join-Path $dir "icon.ico"
    $s.Description = "Text Reader - Neural TTS"
    $s.WindowStyle = 7
    $s.Save()
    Write-Host "Desktop shortcut created!"
}

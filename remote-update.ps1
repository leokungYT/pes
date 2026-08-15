# ════════════════════════════════════════════════════════════════════
#  remote-update.ps1 — สั่งอัปเดตบอททุกเครื่องรวดเดียวผ่าน Tailscale
#  (ไม่ต้องเดินไปกดทีละเครื่อง)
#
#  วิธีใช้:
#    1) สร้างไฟล์ machines.txt วางข้างๆ สคริปต์นี้ ใส่ชื่อเครื่อง/IP ใน tailscale บรรทัดละเครื่อง เช่น
#         100.101.1.11
#         pes-02
#         pes-03
#    2) รันจากเครื่องแม่:
#         powershell -ExecutionPolicy Bypass -File remote-update.ps1 -Method ssh
#       หรือ
#         powershell -ExecutionPolicy Bypass -File remote-update.ps1 -Method psexec
#
#  ต้องมีอย่างใดอย่างหนึ่งบนเครื่องลูก:
#    • ssh    → เปิด OpenSSH Server (Settings > Optional features > OpenSSH Server)
#    • psexec → เครื่องแม่มี PsExec.exe (Sysinternals) + เครื่องลูกเปิด admin share
# ════════════════════════════════════════════════════════════════════

param(
    [ValidateSet("ssh", "psexec")]
    [string]$Method = "ssh",
    [string]$User = "Administrator",
    [string]$BotPath = "C:\Users\Administrator\Downloads\pes-new\pes",
    [string]$ListFile = "machines.txt"
)

$listPath = Join-Path $PSScriptRoot $ListFile
if (-not (Test-Path $listPath)) {
    Write-Host "ไม่พบไฟล์ $ListFile - สร้างไฟล์แล้วใส่ชื่อเครื่อง/IP บรรทัดละเครื่องก่อน" -ForegroundColor Red
    exit 1
}

$machines = Get-Content $listPath | Where-Object { $_.Trim() -ne "" -and -not $_.StartsWith("#") }
Write-Host "เครื่องทั้งหมด $($machines.Count) เครื่อง | วิธี: $Method" -ForegroundColor Cyan

$ok = 0
$fail = @()

foreach ($m in $machines) {
    $m = $m.Trim()
    Write-Host "`n=== $m ===" -ForegroundColor Yellow
    try {
        if ($Method -eq "ssh") {
            ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$User@$m" "cd /d `"$BotPath`" && force-update.bat"
        }
        else {
            & PsExec.exe -accepteula -nobanner "\\$m" -u $User -h -d cmd /c "cd /d `"$BotPath`" && force-update.bat"
        }

        if ($LASTEXITCODE -eq 0) {
            Write-Host "  OK" -ForegroundColor Green
            $ok++
        }
        else {
            Write-Host "  ล้มเหลว (exit $LASTEXITCODE)" -ForegroundColor Red
            $fail += $m
        }
    }
    catch {
        Write-Host "  ล้มเหลว: $_" -ForegroundColor Red
        $fail += $m
    }
}

Write-Host "`n════════════════════════════════" -ForegroundColor Cyan
Write-Host "สำเร็จ $ok / $($machines.Count) เครื่อง" -ForegroundColor Cyan
if ($fail.Count -gt 0) {
    Write-Host "เครื่องที่ไม่สำเร็จ:" -ForegroundColor Red
    $fail | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
}

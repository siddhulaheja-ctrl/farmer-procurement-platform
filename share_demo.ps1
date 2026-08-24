# Puts the demo on a public link teammates can open from anywhere.
#
# Starts the Flask server, opens a free Cloudflare quick tunnel, then prints the
# link on its own, copies it to the clipboard, and saves it to
# LAST_SHARE_LINK.txt. Closing the window stops both the tunnel and the server.
#
# Launched by share_demo.bat - you do not need to run this directly.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$server  = $null
$tunnel  = $null
$logFile = Join-Path $env:TEMP "procurement_tunnel.log"

function Write-Rule { Write-Host ("=" * 66) -ForegroundColor DarkGray }

try {
    if (-not (Test-Path "procurement.db")) {
        Write-Host "No database found. Creating demo data, this takes a few seconds..."
        python seed.py
        Write-Host ""
    }

    # --- start the portal ---------------------------------------------------
    # If a previous run left a server behind, reuse it rather than starting a
    # second one that would only fail to bind port 5000.
    $ready = $false
    try {
        Invoke-WebRequest -Uri "http://localhost:5000" -UseBasicParsing -TimeoutSec 3 | Out-Null
        Write-Host "A portal server is already running - reusing it." -ForegroundColor Green
        $ready = $true
    } catch { }

    if (-not $ready) {
        Write-Host "Starting the portal server..." -ForegroundColor Cyan
        $server = Start-Process -FilePath "python" -ArgumentList "app.py" `
                                -WorkingDirectory $PSScriptRoot -WindowStyle Minimized -PassThru

        # Wait for Flask to actually bind the port rather than guessing a delay.
        foreach ($i in 1..30) {
            Start-Sleep -Milliseconds 500
            try {
                Invoke-WebRequest -Uri "http://localhost:5000" -UseBasicParsing -TimeoutSec 3 | Out-Null
                $ready = $true
                break
            } catch { }
        }
        if (-not $ready) {
            Write-Host "The server did not start. Run start_demo.bat on its own to see the error." -ForegroundColor Red
            Read-Host "Press Enter to close"
            return
        }
        Write-Host "  Server is up on http://localhost:5000" -ForegroundColor Green
    }

    # --- open the tunnel ----------------------------------------------------
    Write-Host "Opening the public tunnel, this usually takes about 10 seconds..." -ForegroundColor Cyan
    if (Test-Path $logFile) { Remove-Item $logFile -Force }

    $cfd = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\cloudflared.exe"
    if (-not (Test-Path $cfd)) { $cfd = "cloudflared" }

    $tunnel = Start-Process -FilePath $cfd `
                -ArgumentList "tunnel","--url","http://localhost:5000","--logfile",$logFile `
                -WindowStyle Minimized -PassThru

    # cloudflared writes the assigned hostname to its log once the tunnel is up.
    $url = $null
    foreach ($i in 1..60) {
        Start-Sleep -Milliseconds 1000
        if (Test-Path $logFile) {
            $match = Select-String -Path $logFile -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" `
                                   -AllMatches -ErrorAction SilentlyContinue
            if ($match) { $url = $match.Matches.Value | Select-Object -First 1; break }
        }
        if ($tunnel.HasExited) { break }
    }

    if (-not $url) {
        Write-Host ""
        Write-Host "Could not get a tunnel link." -ForegroundColor Red
        Write-Host "Check your internet connection, then look at: $logFile"
        Read-Host "Press Enter to close"
        return
    }

    # --- show it ------------------------------------------------------------
    Set-Content -Path "LAST_SHARE_LINK.txt" -Value $url -Encoding utf8
    try { Set-Clipboard -Value $url } catch { }

    Write-Host ""
    Write-Rule
    Write-Host ""
    Write-Host "  SEND THIS LINK TO YOUR TEAMMATES:" -ForegroundColor White
    Write-Host ""
    Write-Host "    $url" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Already copied to your clipboard - just paste it." -ForegroundColor DarkGray
    Write-Host "  Also saved in LAST_SHARE_LINK.txt" -ForegroundColor DarkGray
    Write-Host ""
    Write-Rule
    Write-Host ""
    Write-Host "  Send these logins with it:"
    Write-Host "    Farmer   9000000001   (clean record)"
    Write-Host "    Farmer   9000000002   (has data mismatches)"
    Write-Host "    OTP      123456"
    Write-Host "    Staff    ADMIN / demo123"
    Write-Host ""
    Write-Rule
    Write-Host ""
    Write-Host "  The link works only while this window stays open." -ForegroundColor DarkGray
    Write-Host "  You get a different link each time you run this." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Close this window, or press Ctrl+C, to stop sharing." -ForegroundColor DarkGray
    Write-Host ""

    # Block on the tunnel itself rather than on keyboard input - that way the
    # script stays alive even when launched without an interactive console.
    $tunnel.WaitForExit()
    Write-Host "The tunnel closed on its own. The link no longer works." -ForegroundColor Yellow
}
finally {
    Write-Host ""
    Write-Host "Shutting down..." -ForegroundColor Cyan
    foreach ($p in @($tunnel, $server)) {
        if ($p -and -not $p.HasExited) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch { }
        }
    }
    Write-Host "Link is down and the server has stopped."
    Start-Sleep -Seconds 2
}

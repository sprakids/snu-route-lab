$ErrorActionPreference = 'Stop'
$contractResearchRoot = $PSScriptRoot
$sourceRows = Get-Content -LiteralPath (Join-Path $contractResearchRoot 'source_register.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$captureRows = foreach ($sourceRow in $sourceRows) {
    $savedPath = Join-Path $contractResearchRoot ('sources\' + $sourceRow.id + '.html')
    try {
        $response = Invoke-WebRequest -Uri $sourceRow.url -TimeoutSec 30
        [IO.File]::WriteAllText($savedPath, $response.Content, [Text.UTF8Encoding]::new($false))
        [pscustomobject]@{
            id = $sourceRow.id
            requested_url = $sourceRow.url
            captured_at = [DateTimeOffset]::Now.ToString('o')
            http_status = [int]$response.StatusCode
            saved_file = ('sources/' + $sourceRow.id + '.html')
            bytes = (Get-Item -LiteralPath $savedPath).Length
            sha256 = (Get-FileHash -LiteralPath $savedPath -Algorithm SHA256).Hash.ToLowerInvariant()
            error = $null
        }
    } catch {
        [pscustomobject]@{
            id = $sourceRow.id
            requested_url = $sourceRow.url
            captured_at = [DateTimeOffset]::Now.ToString('o')
            http_status = $null
            saved_file = $null
            bytes = $null
            sha256 = $null
            error = $_.Exception.Message
        }
    }
}
$captureRows | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $contractResearchRoot 'capture_manifest.json') -Encoding UTF8
$captureRows | Select-Object id, http_status, bytes, error | Format-Table -AutoSize

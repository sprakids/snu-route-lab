$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$assetRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../app/static')).Path
$sourceImage = (Resolve-Path (Join-Path $PSScriptRoot '../hagyogil-snu-home-icon-v2.png')).Path
$iconDirectory = Join-Path $assetRoot 'icons'
New-Item -ItemType Directory -Force -Path $iconDirectory | Out-Null
$sourceBitmap = [System.Drawing.Image]::FromFile($sourceImage)
try {
    foreach ($iconSize in @(16,32,48,64,96,128,180,192,256,512)) {
        $bitmap = [System.Drawing.Bitmap]::new($iconSize,$iconSize,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
            $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
            $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $graphics.DrawImage($sourceBitmap,0,0,$iconSize,$iconSize)
            $bitmap.Save((Join-Path $iconDirectory "hagyogil-v2-$iconSize.png"),[System.Drawing.Imaging.ImageFormat]::Png)
        } finally {$graphics.Dispose();$bitmap.Dispose()}
    }
} finally {$sourceBitmap.Dispose()}
# ICO directory with PNG-backed 16/32/48/64 pixel entries for browsers.
$icoSizes = @(16,32,48,64)
$payloads = @($icoSizes | ForEach-Object {,[System.IO.File]::ReadAllBytes((Join-Path $iconDirectory "hagyogil-v2-$_.png"))})
$stream = [System.IO.MemoryStream]::new()
$writer = [System.IO.BinaryWriter]::new($stream)
try {
    $writer.Write([UInt16]0);$writer.Write([UInt16]1);$writer.Write([UInt16]$icoSizes.Count)
    $offset = 6 + 16*$icoSizes.Count
    for ($index=0;$index -lt $icoSizes.Count;$index++) {
        $writer.Write([byte]$icoSizes[$index]);$writer.Write([byte]$icoSizes[$index]);$writer.Write([byte]0);$writer.Write([byte]0)
        $writer.Write([UInt16]1);$writer.Write([UInt16]32);$writer.Write([UInt32]$payloads[$index].Length);$writer.Write([UInt32]$offset)
        $offset += $payloads[$index].Length
    }
    foreach ($payload in $payloads) {$writer.Write([byte[]]$payload)}
    [System.IO.File]::WriteAllBytes((Join-Path $assetRoot 'favicon-v2.ico'),$stream.ToArray())
    [System.IO.File]::WriteAllBytes((Join-Path $assetRoot 'favicon.ico'),$stream.ToArray())
} finally {$writer.Dispose();$stream.Dispose()}
$inlinePng = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes((Join-Path $iconDirectory 'hagyogil-v2-128.png')))
$svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><image width="128" height="128" href="data:image/png;base64,' + $inlinePng + '"/></svg>'
[System.IO.File]::WriteAllText((Join-Path $assetRoot 'icon.svg'),$svg,[System.Text.UTF8Encoding]::new($false))
Get-ChildItem -LiteralPath $iconDirectory -Filter 'hagyogil-v2-*.png' | Select-Object Name,Length

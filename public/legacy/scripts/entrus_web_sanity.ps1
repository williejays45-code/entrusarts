Write-Host "`n=== ENTRUS WEB SANITY CHECK ===`n" -ForegroundColor Cyan

$root = "C:\EnTrusWeb"
$pagesDir = Join-Path $root "pages"
$assetsDir = Join-Path $root "assets\images"

$products = @(
    "hoodie_protector_v1",
    "hoodie_flow_v1",
    "hoodie_drive_v1",
    "hoodie_seer_v1",
    "bracelet_protector_v1",
    "bracelet_flow_v1",
    "bracelet_drive_v1",
    "bracelet_expression_v1",
    "bracelet_seer_v1",
    "bracelet_transfusion_v1",
    "shoe_fusion_v1"
)

$missingImages = @()
$missingPages = @()
$foundCount = 0

foreach ($p in $products) {
    $img = Join-Path $assetsDir "$p.png"
    $page = Join-Path $pagesDir "$p.html"

    if (Test-Path $img) {
        Write-Host "[IMG OK] $p.png" -ForegroundColor Green
    } else {
        Write-Host "[MISS IMG] $p.png" -ForegroundColor Red
        $missingImages += $p
    }

    if (Test-Path $page) {
        Write-Host "[PAGE OK] $p.html" -ForegroundColor Green
        $foundCount++
    } else {
        Write-Host "[MISS PAGE] $p.html" -ForegroundColor Yellow
        $missingPages += $p
    }
}

Write-Host "`n=== SUMMARY ===" -ForegroundColor Cyan
Write-Host ("Products Checked: {0}" -f $products.Count) -ForegroundColor Green
Write-Host ("Missing Images: {0}" -f $missingImages.Count) -ForegroundColor Yellow
Write-Host ("Missing Pages: {0}" -f $missingPages.Count) -ForegroundColor Yellow

if ($missingImages.Count -eq 0 -and $missingPages.Count -eq 0) {
    Write-Host "`nALL GREEN: Every product has page + image." -ForegroundColor Green
} else {
    Write-Host "`nSome items missing. Scroll above to view details." -ForegroundColor Yellow
}

Write-Host "`n=== ENTRUS WEB SANITY CHECK COMPLETE ===`n" -ForegroundColor Cyan

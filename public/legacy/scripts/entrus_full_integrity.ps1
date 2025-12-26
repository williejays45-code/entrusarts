Write-Host "`n=== ENTRUS FULL INTEGRITY SCAN ===`n" -ForegroundColor Cyan

# Roots
$webRoot    = "C:\EnTrusWeb"
$renderRoot = "C:\EnTrusRender"

$script:MissingTotal = 0

function Check-Path {
    param(
        [string]$Base,
        [string]$RelPath,
        [string]$Label,
        [string]$Kind   # CORE / DYNAMIC
    )

    if ([string]::IsNullOrWhiteSpace($RelPath)) {
        $full = $Base
    } else {
        $full = Join-Path $Base $RelPath
    }

    if (Test-Path $full) {
        Write-Host "[OK]   [$Kind] $Label -> $full" -ForegroundColor Green
    } else {
        Write-Host "[MISS] [$Kind] $Label -> $full" -ForegroundColor Red
        $script:MissingTotal++
    }
}

Write-Host "SECTION A: WEB CORE" -ForegroundColor Yellow

Check-Path $webRoot         ""                    "EnTrusWeb root"              "CORE"
Check-Path $webRoot         "index.html"         "Home page"                   "CORE"
Check-Path $webRoot         "apparel.html"       "Apparel landing page"        "CORE"
Check-Path $webRoot         "pages\bracelets.html" "Bracelets collection page" "CORE"
Check-Path $webRoot         "assets"             "Assets folder"               "CORE"
Check-Path $webRoot         "assets\images"      "Image assets folder"         "CORE"
Check-Path $webRoot         "css\styles.css"     "Main stylesheet"             "CORE"
Check-Path $webRoot         "scripts"            "Web scripts folder"          "CORE"
Check-Path $webRoot         "scripts\entrus_web_sanity.ps1" "Sanity script"    "CORE"

Write-Host "`nSECTION B: RENDER CORE" -ForegroundColor Yellow

Check-Path $renderRoot           ""                      "EnTrusRender root"          "CORE"
Check-Path $renderRoot           "output"               "Render output folder"       "CORE"
Check-Path $renderRoot           "profiles"             "Profiles folder"            "CORE"
Check-Path $renderRoot           "scripts"              "Render scripts folder"      "CORE"
Check-Path $renderRoot           "scripts\entrus_render_watcher.ps1" "Render watcher" "CORE"
Check-Path $renderRoot           "scripts\entrus_profile_checker.ps1" "Profile checker (if created)" "CORE"
Check-Path $renderRoot           "scripts\entrus_profile_creator.ps1" "Profile creator (if created)" "CORE"
Check-Path $renderRoot           "scripts\entrus_render_sync_to_web.ps1" "Web sync (if created)" "CORE"

Write-Host "`nSECTION C: PROFILE JSONS" -ForegroundColor Yellow

$profiles = @(
    "hoodie_protector_v1.json",
    "hoodie_flow_v1.json",
    "hoodie_drive_v1.json",
    "hoodie_seer_v1.json",
    "bracelet_protector_v1.json",
    "bracelet_flow_v1.json",
    "bracelet_drive_v1.json",
    "bracelet_expression_v1.json",
    "bracelet_seer_v1.json",
    "bracelet_transfusion_v1.json",
    "shoe_fusion_v1.json"
)

foreach ($p in $profiles) {
    Check-Path $renderRoot ("profiles\" + $p) "Profile $p" "CORE"
}

Write-Host "`nSECTION D: PRODUCT PAGES & IMAGES (DYNAMIC  GENERATED LATER)" -ForegroundColor Yellow

foreach ($p in $profiles) {
    $name = $p -replace "\.json$",""
    Check-Path $webRoot ("pages\" + $name + ".html") ("Product page " + $name) "DYNAMIC"
    Check-Path $webRoot ("assets\images\" + $name + ".png") ("Product image " + $name + ".png") "DYNAMIC"
}

Write-Host "`n=== SUMMARY ===" -ForegroundColor Cyan
if ($script:MissingTotal -eq 0) {
    Write-Host "ALL GREEN: All checked core + dynamic paths exist." -ForegroundColor Green
} else {
    Write-Host ("Missing items: {0}. Review [MISS] lines above." -f $script:MissingTotal) -ForegroundColor Yellow
    Write-Host "NOTE: Anything marked [DYNAMIC] is expected to be missing until renders and product pages are generated." -ForegroundColor Yellow
}

Write-Host "`n=== ENTRUS FULL INTEGRITY SCAN COMPLETE ===`n" -ForegroundColor Cyan

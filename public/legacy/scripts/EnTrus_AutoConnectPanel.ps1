
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# -----------------------------------------------
# CONFIG: PATHS & URLS
# -----------------------------------------------
$root      = "C:\EnTrusWeb"
$indexPath = Join-Path $root "index.html"

# Local tools
$comfyUIPath = "C:\ComfyUI\ComfyUI\run_cpu.bat"  # CPU launcher

# Web URLs (change to your profiles later)
$urlKling  = "https://klingai.com/"
$urlLuma   = "https://lumalabs.ai/"
$urlEleven = "https://elevenlabs.io/"
$urlTikTok = "https://www.tiktok.com/"
$urlIG     = "https://www.instagram.com/"
$urlFB     = "https://www.facebook.com/"

# -----------------------------------------------
# FLOATING FORM SETUP
# -----------------------------------------------
$form                 = New-Object System.Windows.Forms.Form
$form.Text            = "EnTrus Launcher"
$form.StartPosition   = "Manual"
$form.Location        = New-Object System.Drawing.Point(40,120)
$form.Size            = New-Object System.Drawing.Size(210,220)   # 2 columns x 4 rows
$form.FormBorderStyle = "None"
$form.TopMost         = $true
$form.BackColor       = [System.Drawing.Color]::FromArgb(20,20,20)
$form.Opacity         = 0.9

$borderPanel                  = New-Object System.Windows.Forms.Panel
$borderPanel.Dock             = "Fill"
$borderPanel.Padding          = "4,4,4,4"
$borderPanel.BackColor        = [System.Drawing.Color]::FromArgb(15,15,15)
$form.Controls.Add($borderPanel)

$innerPanel                   = New-Object System.Windows.Forms.TableLayoutPanel
$innerPanel.RowCount          = 4
$innerPanel.ColumnCount       = 2
$innerPanel.Dock              = "Fill"
$innerPanel.BackColor         = [System.Drawing.Color]::FromArgb(25,25,25)
$innerPanel.Margin            = "0,0,0,0"
$innerPanel.Padding           = "2,2,2,2"
$innerPanel.CellBorderStyle   = "None"

for ($r=0; $r -lt $innerPanel.RowCount; $r++) {
    $innerPanel.RowStyles.Add(
        (New-Object System.Windows.Forms.RowStyle(
            [System.Windows.Forms.SizeType]::Percent,25))
    )
}
for ($c=0; $c -lt $innerPanel.ColumnCount; $c++) {
    $innerPanel.ColumnStyles.Add(
        (New-Object System.Windows.Forms.ColumnStyle(
            [System.Windows.Forms.SizeType]::Percent,50))
    )
}
$borderPanel.Controls.Add($innerPanel)

# -----------------------------------------------
# DRAGGABLE WINDOW
# -----------------------------------------------
$global:isDragging = $false
$global:dragOffset = [System.Drawing.Point]::Empty

$form.Add_MouseDown({
    if ($_.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
        $global:isDragging = $true
        $global:dragOffset = New-Object System.Drawing.Point($_.X,$_.Y)
    }
})
$form.Add_MouseMove({
    if ($global:isDragging) {
        $screenPos = [System.Windows.Forms.Cursor]::Position
        $form.Location = New-Object System.Drawing.Point(
            $screenPos.X - $global:dragOffset.X,
            $screenPos.Y - $global:dragOffset.Y
        )
    }
})
$form.Add_MouseUp({ $global:isDragging = $false })

$borderPanel.Add_MouseDown($form.MouseDown)
$borderPanel.Add_MouseMove($form.MouseMove)
$borderPanel.Add_MouseUp($form.MouseUp)
$innerPanel.Add_MouseDown($form.MouseDown)
$innerPanel.Add_MouseMove($form.MouseMove)
$innerPanel.Add_MouseUp($form.MouseUp)

# -----------------------------------------------
# BUTTON CREATOR  (NO TYPES, POSITIONAL PARAMS)
# -----------------------------------------------
$btnFont = New-Object System.Drawing.Font("Segoe UI",8.5,[System.Drawing.FontStyle]::Bold)

function New-EAButton {
    param(
        $Text,
        $OnClick
    )

    $btn = New-Object System.Windows.Forms.Button
    $btn.Text                       = [string]$Text
    $btn.Font                       = $btnFont
    $btn.Dock                       = "Fill"
    $btn.FlatStyle                  = "Flat"
    $btn.ForeColor                  = [System.Drawing.Color]::FromArgb(245,208,138)
    $btn.BackColor                  = [System.Drawing.Color]::FromArgb(32,32,32)
    $btn.FlatAppearance.BorderSize  = 1
    $btn.FlatAppearance.BorderColor = [System.Drawing.Color]::FromArgb(80,80,80)

    # Force whatever we got into a ScriptBlock
    if ($OnClick -is [System.Management.Automation.ScriptBlock]) {
        $sb = $OnClick
    } elseif ($OnClick -is [System.Array]) {
        $sb = [ScriptBlock]::Create( ($OnClick -join "`n") )
    } else {
        $sb = [ScriptBlock]::Create([string]$OnClick)
    }

    $btn.Add_Click($sb)
    return $btn
}

function Launch-Url {
    param(
        [string]$Url,
        [string]$Label
    )
    if ([string]::IsNullOrWhiteSpace($Url)) {
        [System.Windows.Forms.MessageBox]::Show(
            "No URL configured for: $Label`nEdit the script config section at the top.",
            $Label,
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
        return
    }
    Start-Process $Url
}

# -----------------------------------------------
# BUTTONS (use positional args: Text, { scriptblock })
# -----------------------------------------------
$buttons = @(
    (New-EAButton "EnTrus" {
        if (Test-Path $indexPath) {
            Start-Process $indexPath
        } else {
            [System.Windows.Forms.MessageBox]::Show(
                "index.html not found at:`n$indexPath",
                "EnTrus Website",
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Warning
            ) | Out-Null
        }
    }),

    (New-EAButton "ComfyUI" {
        if ($comfyUIPath -and (Test-Path $comfyUIPath)) {
            Start-Process $comfyUIPath
        } else {
            [System.Windows.Forms.MessageBox]::Show(
                "ComfyUI CPU launcher not found:`n$comfyUIPath",
                "ComfyUI",
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Warning
            ) | Out-Null
        }
    }),

    (New-EAButton "Kling" {
        Launch-Url -Url $urlKling -Label "Kling AI"
    }),

    (New-EAButton "Luma" {
        Launch-Url -Url $urlLuma -Label "Luma"
    }),

    (New-EAButton "Eleven" {
        Launch-Url -Url $urlEleven -Label "ElevenLabs"
    }),

    (New-EAButton "TikTok" {
        Launch-Url -Url $urlTikTok -Label "TikTok"
    }),

    (New-EAButton "Instagram" {
        Launch-Url -Url $urlIG -Label "Instagram"
    }),

    (New-EAButton "Facebook" {
        Launch-Url -Url $urlFB -Label "Facebook"
    })
)

$idx = 0
for ($r=0; $r -lt 4; $r++) {
    for ($c=0; $c -lt 2; $c++) {
        if ($idx -lt $buttons.Count) {
            $innerPanel.Controls.Add($buttons[$idx], $c, $r)
            $idx++
        }
    }
}

# -----------------------------------------------
# RIGHT-CLICK ANYWHERE TO CLOSE
# -----------------------------------------------
$form.Add_MouseUp({
    if ($_.Button -eq [System.Windows.Forms.MouseButtons]::Right) {
        $form.Close()
    }
})

# -----------------------------------------------
# RUN
# -----------------------------------------------
[System.Windows.Forms.Application]::EnableVisualStyles()
[System.Windows.Forms.Application]::Run($form) 

$ErrorActionPreference = "Stop"
$out = "D:\nbs可视化\_file_listing.txt"
$path = "D:\nbs可视化"
$lines = @()
try {
    $entries = Get-ChildItem -Path $path -Force
    $lines += "Total entries in root: $($entries.Count)"
    foreach ($e in $entries) {
        $t = if ($e.PSIsContainer) { "DIR " } else { "FILE" }
        $size = if ($e.PSIsContainer) { 0 } else { $e.Length }
        $lines += "$t | $($e.Name) | $size"
    }
    $lines += "=== FULL WALK ==="
    Get-ChildItem -Path $path -Recurse -File -Force | ForEach-Object {
        $lines += "$($_.FullName) | $($_.Length)"
    }
} catch {
    $lines += "ERROR: $_"
}
[System.IO.File]::WriteAllLines($out, $lines, [System.Text.Encoding]::UTF8)

param(
    [string]$Root = (Join-Path $PSScriptRoot '..'),
    [switch]$IncludeHistorical
)

$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root)
if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    throw "Repository root does not exist: $Root"
}

$missing = @()
$checked = 0
Get-ChildItem -LiteralPath $Root -Recurse -File -Filter '*.md' |
    Where-Object {
        $_.FullName -notmatch '\\third_party\\' -and
        ($IncludeHistorical -or $_.FullName -match '\\docs\\|\\README\.md$|\\skill\\|\\validation\\|\\pynq_fpga\\preintegration\\README\.md$|\\pynq_fpga\\release\\')
    } |
    ForEach-Object {
        $file = $_
        $text = [IO.File]::ReadAllText($file.FullName)
        foreach ($match in [regex]::Matches($text, '\[[^\]]+\]\(([^)]+)\)')) {
            $target = $match.Groups[1].Value.Trim()
            if ($target -match '^(https?:|mailto:|#)') { continue }
            if ($target.StartsWith('<') -and $target.EndsWith('>')) {
                $target = $target.Substring(1, $target.Length - 2)
            }
            $target = ($target -split '#')[0]
            if (-not $target -or $target.StartsWith('/')) { continue }
            $checked++
            $decoded = [Uri]::UnescapeDataString($target)
            $path = [IO.Path]::GetFullPath((Join-Path $file.DirectoryName $decoded))
            if (-not (Test-Path -LiteralPath $path)) {
                $missing += [pscustomobject]@{
                    Source = $file.FullName.Substring($Root.Length + 1)
                    Target = $match.Groups[1].Value
                }
            }
        }
    }

Write-Output "MARKDOWN_LINKS_CHECKED=$checked"
Write-Output "MARKDOWN_LINKS_MISSING=$($missing.Count)"
if ($missing.Count) {
    $missing | Format-Table -AutoSize
    exit 1
}
Write-Output 'MARKDOWN_LINKS_PASS'

function Get-CarLinkSource {
    param([Parameter(Mandatory=$true)][string]$WorkspaceRoot)
    # Production PC projects are direct workspace children. Historical/audit
    # copies may have the same file layout, but are never authoritative inputs.
    $Candidates = @(Get-ChildItem -LiteralPath $WorkspaceRoot -Directory |
        ForEach-Object {
            $Path = Join-Path $_.FullName 'pc\pynq_link.py'
            if (Test-Path -LiteralPath $Path -PathType Leaf) { Get-Item -LiteralPath $Path }
        })
    if ($Candidates.Count -ne 1) {
        throw "Expected exactly one authoritative pc/pynq_link.py, found $($Candidates.Count)"
    }
    return $Candidates[0].FullName
}

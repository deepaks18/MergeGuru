[CmdletBinding()]
param(
    [string]$InputPath,
    [string]$OutputPath,
    [string]$CertificateThumbprint,
    [ValidateSet("CurrentUser", "LocalMachine")]
    [string]$CertificateStore = "CurrentUser",
    [string]$TimestampUrl,
    [switch]$CheckOnly,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Find-SignTool {
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $roots = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
        "$env:ProgramFiles\Windows Kits\10\bin"
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    $candidate = Get-ChildItem -Path $roots -Filter signtool.exe -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    return $candidate.FullName
}

function Get-CodeSigningCertificates([string]$Store) {
    $now = Get-Date
    Get-ChildItem -Path "Cert:\$Store\My" -CodeSigningCert -ErrorAction SilentlyContinue |
        Where-Object { $_.HasPrivateKey -and $_.NotBefore -le $now -and $_.NotAfter -gt $now }
}

$signTool = Find-SignTool
$certificates = @(Get-CodeSigningCertificates $CertificateStore)

if ($CheckOnly) {
    [PSCustomObject]@{
        SignToolFound = [bool]$signTool
        SignToolPath = $signTool
        CertificateStore = $CertificateStore
        UsableCertificateCount = $certificates.Count
        Ready = [bool]$signTool -and $certificates.Count -gt 0
    } | Format-List
    if ($certificates.Count) {
        $certificates | Select-Object Subject, Thumbprint, NotAfter | Format-Table -AutoSize
    }
    if (-not $signTool) {
        Write-Warning "SignTool was not found. Install the Windows SDK Signing Tools component."
    }
    if (-not $certificates.Count) {
        Write-Warning "No valid code-signing certificate with a private key was found in Cert:\$CertificateStore\My."
    }
    return
}

if (-not $signTool) {
    throw "SignTool was not found. Install the Windows SDK Signing Tools component before signing."
}
if (-not $InputPath) {
    throw "InputPath is required when signing."
}
if (-not $CertificateThumbprint) {
    throw "CertificateThumbprint is required. Select the exact company certificate explicitly."
}
if (-not $TimestampUrl) {
    throw "TimestampUrl is required. Use the RFC 3161 URL supplied by the certificate provider or your firm."
}

$input = (Resolve-Path -LiteralPath $InputPath).Path
if ([IO.Path]::GetExtension($input) -ine ".exe") {
    throw "Only Windows executable (.exe) artifacts can be signed by this release script."
}

if (-not $OutputPath) {
    $directory = [IO.Path]::GetDirectoryName($input)
    $name = [IO.Path]::GetFileNameWithoutExtension($input)
    $OutputPath = Join-Path $directory ($name + "_Signed.exe")
}
$output = [IO.Path]::GetFullPath($OutputPath)
if ($input -eq $output) {
    throw "OutputPath must differ from InputPath. The unsigned candidate is preserved by design."
}
$outputDirectory = [IO.Path]::GetDirectoryName($output)
if (-not (Test-Path -LiteralPath $outputDirectory -PathType Container)) {
    throw "The output directory does not exist: $outputDirectory"
}
if ((Test-Path -LiteralPath $output) -and -not $Force) {
    throw "The signed output already exists. Choose another path or pass -Force explicitly."
}

$thumbprint = ($CertificateThumbprint -replace '\s', '').ToUpperInvariant()
$certificate = $certificates | Where-Object { $_.Thumbprint -eq $thumbprint } | Select-Object -First 1
if (-not $certificate) {
    throw "The selected thumbprint is not a valid code-signing certificate with an accessible private key."
}

$temporary = Join-Path $outputDirectory (".mergeguru-sign-" + [guid]::NewGuid().ToString("N") + ".exe")
Copy-Item -LiteralPath $input -Destination $temporary
try {
    $arguments = @("sign", "/fd", "SHA256", "/sha1", $thumbprint, "/s", "My")
    if ($CertificateStore -eq "LocalMachine") {
        $arguments += "/sm"
    }
    $arguments += @("/tr", $TimestampUrl, "/td", "SHA256", "/d", "MergeGuru Lite", $temporary)
    & $signTool @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "SignTool failed with exit code $LASTEXITCODE."
    }

    & $signTool verify /pa /all /v $temporary
    if ($LASTEXITCODE -ne 0) {
        throw "Signature verification failed with exit code $LASTEXITCODE."
    }

    Move-Item -LiteralPath $temporary -Destination $output -Force:$Force
    $signature = Get-AuthenticodeSignature -LiteralPath $output
    $hash = Get-FileHash -LiteralPath $output -Algorithm SHA256
    [PSCustomObject]@{
        SignedArtifact = $output
        Signer = $signature.SignerCertificate.Subject
        SignatureStatus = $signature.Status
        TimestampStatus = $signature.TimeStamperCertificate.Subject
        SHA256 = $hash.Hash
    } | Format-List
}
finally {
    if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Force
    }
}

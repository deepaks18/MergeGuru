# MergeGuru Windows Code Signing

MergeGuru production artifacts must be signed with a certificate owned or
approved by the distributing organization. A self-signed certificate is not an
acceptable substitute for enterprise distribution.

The signing script preserves the unsigned candidate and writes a separate
signed executable. It requires an explicit certificate thumbprint so the wrong
certificate cannot be selected automatically.

## Prerequisites

1. Install the Windows SDK **Signing Tools for Desktop Apps** component so
   `signtool.exe` is available.
2. Install the organization code-signing certificate, including its private
   key, in `Cert:\CurrentUser\My` or `Cert:\LocalMachine\My`.
3. Obtain the RFC 3161 timestamp URL from the certificate provider or company
   security team.

Check readiness without changing any file:

```powershell
.\tools\sign_windows_release.ps1 -CheckOnly
```

## Sign A Staged Candidate

```powershell
.\tools\sign_windows_release.ps1 `
  -InputPath ".\candidate\MergeGuru_Lite.exe" `
  -OutputPath ".\candidate\MergeGuru_Lite_Signed.exe" `
  -CertificateThumbprint "COMPANY_CERTIFICATE_THUMBPRINT" `
  -TimestampUrl "COMPANY_RFC3161_TIMESTAMP_URL"
```

Use `-CertificateStore LocalMachine` only when the private key is installed in
the machine certificate store. The script uses SHA-256 for both the file digest
and RFC 3161 timestamp, then runs Authenticode verification before committing
the signed output.

After signing, update the release manifest with the signed artifact's SHA-256
hash and verify it again from the final distribution location. Signing changes
the executable hash, so an unsigned hash must never be reused for a signed file.

Microsoft SignTool reference:

https://learn.microsoft.com/windows/win32/seccrypto/signtool

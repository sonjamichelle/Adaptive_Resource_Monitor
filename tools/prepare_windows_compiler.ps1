$ErrorActionPreference = 'Stop'
$scratch = Join-Path $PWD '.ci'
$compiler = Join-Path $scratch 'inno'
$download = Join-Path $scratch 'innosetup-7.1.1-x64.exe'
$origin = 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe'
$expected = '8a5a6711c3766a6e5fb74f280ba0e3551e719ce94538d901fdbd1f8f9920b3f0'
Invoke-WebRequest -UseBasicParsing -Uri $origin -OutFile $download
if ((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash -ine $expected) {
    throw 'Inno Setup download SHA-256 mismatch'
}
$signature = Get-AuthenticodeSignature -LiteralPath $download
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'CN=Pyrsys B\.V\.') {
    throw 'Inno Setup publisher verification failed'
}
& '.ci\python\Scripts\python.exe' tools\install_ci_compiler.py $download $compiler
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $compiler 'ISCC.exe'))) {
    throw 'Portable Inno Setup staging failed'
}
Write-Host 'Inno Setup 7.1.1 x64 hash, publisher and portable staging verified.'

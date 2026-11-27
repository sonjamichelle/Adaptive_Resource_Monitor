# Jenkins

The Phantom Jenkins controller's Applications view contains the
[Adaptive Resource Monitor folder](https://phantom.zapto.org:8080/jenkins/job/Adaptive-Resource-Monitor/).
Both jobs use the existing inkiron-windows native Windows x64 agent through
its inkiron-windows-x64 label. The agent needs Windows Git, Python 3.12 x64,
trusted HTTPS, workspace write access and permission to create a private
Windows desktop for acceptance. The build stages a hash-pinned and
Authenticode-verified Inno Setup 7.1.1 portable compiler in the workspace.

- **Build and Archive** (Build-and-Archive) checks main with hashed five-minute SCM polling. It validates VERSION.md, checks dependencies, runs the test suite and isolated native test, builds native x64 packages, validates the binaries and archive, signs the update manifest and fingerprints the candidate. It retains 15 build records and six artifact sets.
- **Publish Release** (Publish-Release) is a manual job with 20 retained records. It validates an explicit build number, exact source commit and authoritative version. Verification-only mode is the default. It uses Copy Artifact to retrieve the chosen archive.

The ARM folder owns the arm-gitea-read checkout identity,
arm-ed25519-release signing credential and arm-gitea-release write credential.
The two Gitea service identities are scoped through repository access to ARM.
Source checkout uses the Git credential binding. The Ed25519 and publication
secrets are bound only for their respective stages. Workspace cleanup follows
both jobs. About reports the packaged Git revision and build time. BUILD.json
and the signed release receipt record the exact Jenkins build number.

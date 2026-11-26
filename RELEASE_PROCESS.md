# Release process

This application uses the existing [Adaptive_Resource_Monitor repository](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor)
for both source and public release attachments. Each release tag names the
exact archived source commit. The public attachments are the installer,
portable ZIP, SHA-256 manifest, signed release manifest, signed release notes
as a Markdown file, Ed25519 public key and build receipt. The product builds
never include private configuration, credentials or signing keys.

1. Wait for a successful ARM Build and Archive run. Record the numbered build,
   exact commit and VERSION.md value from its console and release-build.json.
2. Run Publish Release with those three values and **Verify only** enabled.
   Check that the job retrieved and verified the exact archived files.
3. After explicit release authorization, run Publish Release with the same
   values, turn **Verify only** off, and enable **Authorize publication**.
   The publish job reuses the archive without rebuilding.
4. The job verifies the changelog and trusted signature, checks both packages,
   uploads into a draft, checks downloaded bytes, and promotes the release.
   It then anonymously reads back the Git tag, release, artifacts, hashes and
   signature. A failed anonymous verification returns the release to draft
   where possible.

Existing version tags must point to the same commit. A public release for that
version is accepted only if its attachments match the pinned archive. Use a
new authorized application version for any change to its released bytes.

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

## Public download links

After anonymous verification succeeds, the publication job refreshes the
public version, badges, download links and package sizes in README.md if the
selected archive is the newest verified release. This uses the released
manifest and the verified public attachments. VERSION.md continues to govern
development and build versioning.

If the README change fails, the verified release stays available. Resolve the
documentation error, then retry authorized publication with the same pinned
build. The job verifies the existing attachments before refreshing the README.
A documentation-only update takes the checkout and version-validation path in
Build and Archive. It skips package creation, signing and archival. Review the [Wiki maintenance checklist](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/wiki/Wiki-Maintenance) after publication.

Before publishing a channel promotion, verify discovery and eligibility
with the already-shipped updater. The v0.6.2.1_alpha updater requires an
Alpha corrective release before it can discover Beta. Starting with
v0.6.2.2_alpha, a release can progress to a more mature channel at identical
numerical version counters. Production self-update acceptance and signed
fixture discovery are required before the promoted release is published.

Record the production executable version, process and profile fingerprints
before and after development validation. Run candidate launch tests from
isolated folders and profiles. Validate an installer in a disposable
environment that has no production installation with the same Windows
application ID. A production self-update starts from the current installed
application's update controls after publication. Retain its shutdown
acknowledgement, transaction log and restart receipt as acceptance evidence.

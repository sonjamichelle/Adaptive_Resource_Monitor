# ARM repository synchronization

[GitHub](https://github.com/sonjamichelle/Adaptive_Resource_Monitor) is the public entry point for [releases](https://github.com/sonjamichelle/Adaptive_Resource_Monitor/releases), [issues](https://github.com/sonjamichelle/Adaptive_Resource_Monitor/issues), [wiki documentation](https://github.com/sonjamichelle/Adaptive_Resource_Monitor/wiki), and [pull requests](https://github.com/sonjamichelle/Adaptive_Resource_Monitor/pulls). Development, signing, release authorization and production acceptance continue in [Gitea](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor). The released ARM updater continues to trust Gitea.

## Scope

The synchronization service on Phantom is `arm-repository-sync.service`. It is separate from ARM and Jenkins and is configured for this repository pair. It compares explicitly advertised source branches and tags and the native Wiki branches. GitHub's Wiki uses `master`; Gitea uses `main`. Both Wiki histories share an initial merge commit. A normal source or Wiki transfer is a checked fast-forward. Deletion or divergent history requires a maintainer decision. Pull requests and fork refs remain on their originating platforms. A reviewed GitHub merge is eligible to transfer back as a source commit.

Initial issue migration uses per-object repository IDs and stable issue and comment IDs. A protected SQLite database keeps per-platform object mappings, last synchronized fields, pending create operations and conflicts. Imported issues and comments retain original author and timestamp attribution in their metadata. GitHub assigns its own issue numbers and records the API actor as the importer. Plain issue references brought from the other platform are linked to their original project. Both platforms keep native issue forms. When changing a form, apply the same intent in both template directories. GitHub labels preserve supported names, colors and descriptions; Gitea's exclusive scopes are a Gitea feature.

Use the public [development board](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/projects/1), [support board](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/projects/2) and [milestones](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/milestones) for authoritative planning and cross-platform progress. Project boards and PR discussions have platform-specific API limits. [Issue lifecycle](ISSUE_MANAGEMENT.md)

## Releases and Jenkins

The public Gitea release remains the authority. Release replication verifies the pinned Ed25519 manifest, tag commit, package types and SHA-256 hashes, then verifies public readback against the same bytes. Published application packages and signed notes stay immutable under the sync policy. A GitHub-only or inconsistent release is quarantined in sync diagnostics and has no effect on the ARM updater. Signed release publication still requires the original [Jenkins workflow](RELEASE_PROCESS.md). GitHub Actions are disabled for this repository. Documentation and issue forms take the existing documentation-only Gitea build path.

The installed ARM's Report Issue and About documentation links retain their current behavior. The next approved Minor revision can switch compiled public links to GitHub through the centralized URL definitions. The trusted Gitea update endpoint remains separate.

## Maintainer operations

Use the native service status and journal on Phantom to inspect reconciliation time, rate limits, pending accepted events and unresolved conflicts. Signal `USR1` to request an immediate reconciliation. Periodic reconciliation covers missing deliveries and Wiki events. The receiver checks the per-platform HMAC signature, repository ID and delivery identity before recording a wakeup. The service does not execute issue, comment, PR or Wiki content.

Resolve branch divergence by reviewing both tips and making a merge that preserves both histories. Push a fast-forward from both sides and recheck equivalence. Resolve conflicting issue fields with the authors or update both versions deliberately. Leave deleted or redacted material in its originating platform's moderation workflow and report a sensitive exposure privately. The bridge does not propagate deletions.

The service uses a scoped GitHub credential and a restricted Gitea service identity. Credentials and the state database belong in the protected systemd credential and state directories. For approved rotation, prepare the scoped replacement using the respective platform, update the protected service credential, restart the unit and verify access and reconciliation. Treat a consistent SQLite backup and the state directory as recovery material. Restore under the stopped unit and verify the repository IDs and identity mappings before resuming. Use the maintainer status for actual capabilities and unresolved synchronization errors.

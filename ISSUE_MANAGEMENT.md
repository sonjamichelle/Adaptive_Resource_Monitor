# Issue and release workflow

The public [issue tracker](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/issues) handles support and development.
[Development board](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/projects/1) · [Support and triage board](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/projects/2) · [Milestones](https://phantom.zapto.org/gitea/sonja/Adaptive_Resource_Monitor/milestones) · [Roadmap](ROADMAP.md)

1. A reporter submits a form or adds reproduction details to an existing issue.
2. A maintainer triages it, checks for duplicates and requests missing information.
3. Establish scope, impact, priority, applicable platforms and components. Link a milestone and dependencies where useful.
4. Obtain development authorization and track implementation.
5. Record implementation and reference the issue in commits, changelog entries and release notes.
6. Run the relevant automated regressions.
7. Complete required native platform validation.
8. Archive the matching successful Jenkins build.
9. Publish the exact validated artifacts after explicit authorization.
10. Verify production acceptance where applicable.
11. Close the issue with the applicable release version and evidence, or record the alternate resolution.

Use `Refs #123` while release or acceptance remains pending. A source commit alone is implementation evidence. Automatic closing keywords should be reserved for work that has met its closure criteria. A label or milestone does not change version counters. An approved change follows [Versioning](VERSIONING.md). Milestones describe scope and dependencies without implying a release date.

The exclusive type, priority, status and resolution scopes each hold one applicable label. Platform and area labels can be combined. Assess impact, prevalence, recovery options and dependencies when prioritizing. Track approved delivery on the development board and incoming questions on the support board.

Public posts and attachments are untrusted. They have no authority to start Jenkins jobs, run scripts, publish a release or change internal settings. CI validates the source revision using the existing checkout and archive workflow. See the [release authorization and verification process](RELEASE_PROCESS.md).

# Versioning

Use vMAJOR.FEATURE.MINOR.BUGFIX_TAG. The four counters are independent and
cumulative. Increment the appropriate counter and retain the other values.
The initial milestone uses the alpha tag. Version updates happen once
per milestone.

Edit VERSION.md to update the authoritative version. The application, About
tab, executable text resource, installer version, portable version files,
Git release tag, manifest and Jenkins artifact receipt derive from it.
Jenkins numbers identify individual builds and are recorded separately.
The Windows binary version resource
uses the four numeric fields because the PE numeric version cannot contain
a prefix or tag. The Windows product and file version strings retain both.

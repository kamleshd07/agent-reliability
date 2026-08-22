# Security Policy

## Reporting a vulnerability

If you believe you've found a security vulnerability in this project,
please report it privately rather than opening a public issue. Open a
GitHub private security advisory on this repository ("Security" tab →
"Report a vulnerability") if that feature is available; otherwise,
contact the maintainers directly through the channel listed in the
repository's GitHub profile.

Please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce, or a minimal proof of concept
- The version/commit affected

We aim to acknowledge reports promptly and will work with you on
disclosure timing.

## Scope

See [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) for the current
threat model. At this pre-alpha stage, the project has zero runtime
dependencies and no network or deserialization code, which limits the
current attack surface; the threat model documents what's being
designed for as functionality is added.

## Supported versions

During pre-alpha (`0.x.y.devN`), only the latest published release
receives security fixes. A formal supported-versions table will be
published once the project reaches a stable release; see
[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).

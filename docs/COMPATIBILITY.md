# Compatibility & Versioning

## Package version

The project uses [Semantic Versioning](https://semver.org/). It starts
at `0.1.0.dev0`.

## Pre-alpha status

**No public API is stable during the `0.x.y.devN` / `0.x` pre-alpha and
alpha phase.** Anything exported from `agent_reliability` may change or
be removed between any two releases, including patch releases, without
a deprecation period. This is stated explicitly so that early adopters
do not mistake "importable" for "guaranteed."

## Stability tiers, once they exist

Once the project leaves pre-alpha, three tiers apply:

| Tier | Guarantee |
|---|---|
| Stable | Follows SemVer. Breaking changes require a major version bump and a documented deprecation window. |
| Experimental (`agent_reliability.experimental.*`) | May change or be removed in any release, including patch releases. Never silently promoted — promotion to stable is a deliberate, documented, reviewed step. |
| Internal (no leading-underscore convention assumed — anything not re-exported from a package's public `__all__`) | No compatibility guarantee whatsoever, at any project stage. |

## Telemetry contract stability

Emitted telemetry (event names, attribute keys, semantic conventions)
follows the same tiering, tracked separately in
[TELEMETRY_SPEC.md](TELEMETRY_SPEC.md), because a telemetry contract can
break downstream dashboards and alerts independently of the Python API
breaking anything. A change can be telemetry-breaking without being
API-breaking, or vice versa; both must be considered independently when
evaluating a change's compatibility impact.

## Supported Python versions

`>= 3.11` at project start. Support-window policy for newer Python
minor releases and eventual dropping of old ones will be documented once
the project reaches its first stable release; not fixed prematurely.

## Deprecation policy

Not yet defined in detail — deferred until the project has a stable
public API to deprecate anything from. Once defined, it will live in
this document.

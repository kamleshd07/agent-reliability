# Design and review records

This repository holds the library, its tests and its technical documentation. Internal design, review, verification and
decision records produced while building it are kept in a private archive, not here. Some earlier records
remain in this repository for now (for example the
`docs/P28_*` / `docs/P29_*` documents that tests, scripts or packaging rules still reference); they are history, not a
specification, and the user-facing contracts are the documents linked from the [documentation index](README.md).

Records that have been relocated are listed by name, size and SHA-256 digest in
`tests/fixtures/documentation/relocated-governance-records.json`, so the byte-for-byte baseline checks that cover
historical documents still pass without the files being present. A link in a retained document that used to point to a
relocated record now reads "(relocated; see docs/DESIGN_RECORDS.md)".

Security issues are reported privately through GitHub's "Report a vulnerability" (see [SECURITY.md](../SECURITY.md)).

Security-review records (checker-bypass cases, exporter reproductions, calibration and instrumentation reviews) were relocated in a
third step. Retained `docs/P28_*` documents are covered by the byte-for-byte historical baseline and are intentionally not edited, so
they may still name a relocated record in plain text; those names are historical references, not links.

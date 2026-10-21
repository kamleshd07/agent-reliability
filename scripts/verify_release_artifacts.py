"""Inspect and smoke-test wheel and sdist in isolated environments."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import tarfile
import tempfile
import venv
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(*arguments: str) -> str:
    completed = subprocess.run(
        list(arguments),
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {arguments!r}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed.stdout.replace("\r\n", "\n")


def _python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _create_environment(path: Path) -> Path:
    venv.EnvBuilder(with_pip=True, clear=True).create(path)
    return _python(path)


def _one_artifact(path: Path | None, pattern: str, description: str) -> Path:
    if path is not None:
        resolved = path.resolve()
        if not resolved.is_file():
            raise ValueError(f"{description} does not exist: {resolved}")
        return resolved
    matches = sorted((ROOT / "dist").glob(pattern))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {description} in dist/")
    return matches[0].resolve()


def _inspect_artifacts(wheel: Path, sdist: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
        metadata_name = next(
            name for name in wheel_names if name.endswith(".dist-info/METADATA")
        )
        metadata = BytesParser().parsebytes(archive.read(metadata_name))

    version = str(metadata["Version"])
    if metadata["Name"] != "agent-reliability":
        raise AssertionError("distribution name changed")
    if metadata["Requires-Python"] != ">=3.11":
        raise AssertionError("Python requirement changed")
    requirements = metadata.get_all("Requires-Dist", [])
    if any("extra ==" not in requirement for requirement in requirements):
        raise AssertionError("base wheel unexpectedly declares a dependency")
    required_wheel = {
        "agent_reliability/__init__.py",
        "agent_reliability/application/measurement_policy.py",
        "agent_reliability/domain/measurement_health.py",
        "agent_reliability/measurement/__init__.py",
        "agent_reliability/py.typed",
        f"agent_reliability-{version}.dist-info/licenses/LICENSE",
        "agent_reliability/experimental/judge/__init__.py",
        "agent_reliability/experimental/judge/schemas/calibration-case.schema.json",
        "agent_reliability/experimental/judge/schemas/calibration-report.schema.json",
        *(
            f"agent_reliability/experimental/judge/rubrics/{name}.json"
            for name in (
                "judge-answer-correctness",
                "judge-groundedness",
                "judge-instruction-adherence",
                "judge-safety-policy",
                "judge-task-completion-evidence",
            )
        ),
    }
    if not required_wheel <= wheel_names:
        raise AssertionError(f"wheel missing: {sorted(required_wheel - wheel_names)}")
    if any(
        name.startswith(("tests/", "examples/", "benchmarks/", ".git/"))
        for name in wheel_names
    ):
        raise AssertionError("wheel contains repository-only files")

    with tarfile.open(sdist, "r:gz") as archive:
        sdist_names = set(archive.getnames())
    prefix = f"agent_reliability-{version}/"
    required_sdist = {
        f"{prefix}LICENSE",
        f"{prefix}README.md",
        f"{prefix}pyproject.toml",
        f"{prefix}src/agent_reliability/__init__.py",
        f"{prefix}src/agent_reliability/py.typed",
    }
    if not required_sdist <= sdist_names:
        raise AssertionError(f"sdist missing: {sorted(required_sdist - sdist_names)}")
    forbidden_parts = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "dist",
        "htmlcov",
    }
    _assert_no_internal_files(wheel_names, sdist_names, prefix)
    for name in sdist_names:
        parts = set(Path(name).parts)
        if parts & forbidden_parts or Path(name).name.startswith(".coverage"):
            raise AssertionError(f"sdist contains local/generated path: {name}")
    _assert_no_private_keys(wheel, sdist)
    _assert_no_local_paths(wheel, sdist)
    print(f"artifact metadata and contents: ok ({version})")
    return version


_ALLOWED_PUBLIC_MILESTONE_DOCS = {
    "docs/P29_PILOT_REPORT_TEMPLATE.json",
    "docs/P29_PILOT_RUNBOOK.md",
    "docs/P29_PILOT_SAFEGUARDS.md",
}
_INTERNAL_NAME = re.compile(r"(^|/)(CLAUDE|AGENTS)\.md$")
_MILESTONE_DOC = re.compile(r"^docs/P\d\d_")


def _assert_no_internal_files(
    wheel_names: set[str], sdist_names: set[str], prefix: str
) -> None:
    """Agent instructions, internal milestone reports and evidence never ship.

    Any ``docs/P<nn>_*`` file in the sdist must be on the explicit public allowlist
    (an allowlist, so a new internal report cannot slip through by name).
    """

    leaked: list[str] = []
    for name in sorted(sdist_names):
        relative = name[len(prefix) :] if name.startswith(prefix) else name
        if (
            _INTERNAL_NAME.search(relative)
            or relative.startswith("docs/evidence/")
            or (
                _MILESTONE_DOC.match(relative)
                and relative not in _ALLOWED_PUBLIC_MILESTONE_DOCS
            )
        ):
            leaked.append(f"sdist:{name}")
    for name in sorted(wheel_names):
        if _INTERNAL_NAME.search(name) or name.startswith(("docs/", "tests/")):
            leaked.append(f"wheel:{name}")
    if leaked:
        raise AssertionError(f"internal files in artifacts: {leaked}")


_KEY_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".jks")
# Assembled so this script never contains the literal marker it searches for.
_PRIVATE_KEY_MARKER = b"PRIVATE" + b" KEY"  # PEM, PGP and OpenSSH blocks


# Local developer paths must not ship (assembled so this script never matches itself).
_LOCAL_PATH_MARKERS = (
    b"/Us" + b"ers/",
    b"/private" + b"/tmp/",
    b"/var/fol" + b"ders/",
    b"/ho" + b"me/",
)
# Windows user paths, matched case-insensitively, plain and JSON-escaped.
_WINDOWS_PATH_MARKERS = (
    b"c:\\us" + b"ers\\",
    b"c:\\\\us" + b"ers\\\\",
    b"c:/us" + b"ers/",
)


def _has_local_path(data: bytes) -> bool:
    lowered = data.lower()
    return any(marker in data for marker in _LOCAL_PATH_MARKERS) or any(
        marker in lowered for marker in _WINDOWS_PATH_MARKERS
    )


def _assert_no_local_paths(wheel: Path, sdist: Path) -> None:
    """No file in either artifact may embed a local developer path."""

    offenders: list[str] = []
    with zipfile.ZipFile(wheel) as archive:
        for info in archive.infolist():
            data = archive.read(info)
            if _has_local_path(data):
                offenders.append(f"wheel:{info.filename}")
    with tarfile.open(sdist, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            data = handle.read()
            if _has_local_path(data):
                offenders.append(f"sdist:{member.name}")
    if offenders:
        raise AssertionError(f"local developer paths in artifacts: {offenders}")


def _assert_no_private_keys(wheel: Path, sdist: Path) -> None:
    """No private-key file or PEM private-key block may ship in either artifact."""

    offenders: list[str] = []
    with zipfile.ZipFile(wheel) as archive:
        for info in archive.infolist():
            if info.filename.lower().endswith(
                _KEY_SUFFIXES
            ) or _PRIVATE_KEY_MARKER in archive.read(info):
                offenders.append(f"wheel:{info.filename}")
    with tarfile.open(sdist, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            if member.name.lower().endswith(_KEY_SUFFIXES):
                offenders.append(f"sdist:{member.name}")
                continue
            handle = archive.extractfile(member)
            if handle is not None and _PRIVATE_KEY_MARKER in handle.read():
                offenders.append(f"sdist:{member.name}")
    if offenders:
        raise AssertionError(f"private key material in artifacts: {offenders}")


def _probe(python: Path, expected_version: str, *, expect_otel: bool) -> None:
    probe = (
        "import importlib.resources, importlib.util, importlib.metadata; "
        "import agent_reliability; "
        "import agent_reliability.measurement as measurement; "
        f"assert agent_reliability.__version__ == {expected_version!r}; "
        "assert importlib.metadata.version('agent-reliability') == "
        "agent_reliability.__version__; "
        "assert agent_reliability.__all__ == ['__version__']; "
        "assert set(measurement.__all__) == "
        "{'MeasurementHealth', 'MeasurementHealthReason', "
        "'MeasurementHealthReport', 'MeasurementPolicy'}; "
        "assert importlib.resources.files('agent_reliability')"
        ".joinpath('py.typed').is_file(); "
        f"assert (importlib.util.find_spec('opentelemetry') is not None) is "
        f"{expect_otel!r}; "
        "print('installed metadata/import probe: ok')"
    )
    print(_run(str(python), "-c", probe), end="")


def _verify_base(python: Path, wheel: Path, version: str) -> None:
    _run(str(python), "-m", "pip", "install", "--no-deps", str(wheel))
    _probe(python, version, expect_otel=False)
    _run(
        str(python),
        "-c",
        "import importlib.util; "
        "from agent_reliability.sdk import AgentReliability; "
        "assert importlib.util.find_spec('httpx') is None",
    )
    _run(
        str(python),
        "-c",
        "from agent_reliability.experimental.judge import "
        "REFERENCE_RUBRIC_IDS, load_reference_rubric; "
        "assert len(REFERENCE_RUBRIC_IDS) == 5; "
        "assert all(load_reference_rubric(i).rubric_id == i "
        "for i in REFERENCE_RUBRIC_IDS)",
    )
    expected = {
        "basic_reliability.py": "Reliability: 75.00%",
        "async_agent.py": "Async reliability: 2/3 (MET)",
        "provenance_conflict.py": "evaluator_version_mismatch",
        "policy_fail_open.py": "This is application policy, not SDK policy.",
        "policy_fail_closed.py": "The application owns authorization",
        "policy_bounded_degradation.py": "UNAVAILABLE -> SENSITIVE_DISABLED",
    }
    for example, marker in expected.items():
        output = _run(str(python), str(ROOT / "examples" / example))
        if marker not in output:
            raise AssertionError(f"installed-wheel example changed: {example}")
    print("base wheel and offline examples: ok")


def _verify_sdist(python: Path, sdist: Path, version: str) -> None:
    _run(str(python), "-m", "pip", "install", "--no-deps", str(sdist))
    _probe(python, version, expect_otel=False)
    output = _run(str(python), str(ROOT / "examples" / "basic_reliability.py"))
    if "Budget remaining: 0.00%" not in output:
        raise AssertionError("sdist-installed quickstart changed")
    print("sdist installation and quickstart: ok")


def _verify_otel(python: Path, wheel: Path, version: str) -> None:
    _run(str(python), "-m", "pip", "install", f"{wheel}[otel]")
    _probe(python, version, expect_otel=True)
    output = _run(str(python), str(ROOT / "examples" / "opentelemetry_example.py"))
    if "host-owned OTel context" not in output:
        raise AssertionError("OTel installed-wheel example changed")
    print("OTel-extra wheel and example: ok")


def _verify_typing(python: Path, wheel: Path) -> None:
    _run(str(python), "-m", "pip", "install", "mypy>=1.11", str(wheel))
    output = _run(
        str(python),
        "-m",
        "mypy",
        "--config-file",
        str(ROOT / "tests" / "typing" / "mypy.ini"),
        str(ROOT / "tests" / "typing" / "installed_consumer.py"),
    )
    if "Success: no issues found" not in output:
        raise AssertionError("downstream strict typing failed")
    print("installed-wheel downstream strict mypy: ok")


def _verify_http(python: Path, wheel: Path, version: str) -> None:
    _run(str(python), "-m", "pip", "install", f"{wheel}[http]")
    _probe(python, version, expect_otel=False)
    probe = """
import json
from datetime import UTC, datetime
from uuid import UUID
import httpx
from agent_reliability.adapters.http_event_sink import HTTPEventSink
from agent_reliability.domain import AgentIdentity
from agent_reliability.ports.events import RunStarted

def handler(request):
    event = json.loads(request.content)
    return httpx.Response(201, json={
        "event_id": event["event_id"],
        "run_id": "00000000-0000-4000-8000-000000000007",
        "status": "accepted", "durability": "committed",
    })

agent = AgentIdentity("agent", "Agent", "1", "test")
sink = HTTPEventSink(
    allow_unrestricted_indicators=True,
    endpoint="https://example.com/api/v1/evidence/runs",
    credential_provider=lambda: "artifact-test-token",
    deployment_id=UUID("00000000-0000-4000-8000-000000000007"),
    expected_agent=agent, _transport=httpx.MockTransport(handler),
)
try:
    sink.emit(RunStarted("run-1", None, agent, datetime.now(UTC)))
    assert sink.flush(2).counts_by_disposition["committed"] == 1
finally:
    sink.close(0)
print("HTTP-extra installed-wheel mocked delivery: ok")
"""
    print(_run(str(python), "-c", probe), end="")


def verify(
    wheel: Path,
    sdist: Path,
    *,
    include_otel: bool,
    include_typing: bool,
) -> None:
    version = _inspect_artifacts(wheel, sdist)
    with tempfile.TemporaryDirectory(prefix="agent-reliability-release-") as temporary:
        root = Path(temporary)
        _verify_base(_create_environment(root / "base"), wheel, version)
        _verify_sdist(_create_environment(root / "sdist"), sdist, version)
        _verify_http(_create_environment(root / "http"), wheel, version)
        if include_otel:
            _verify_otel(_create_environment(root / "otel"), wheel, version)
        if include_typing:
            _verify_typing(_create_environment(root / "typing"), wheel)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--sdist", type=Path)
    parser.add_argument("--skip-otel", action="store_true")
    parser.add_argument("--skip-typing", action="store_true")
    arguments = parser.parse_args()
    verify(
        _one_artifact(arguments.wheel, "agent_reliability-*.whl", "wheel"),
        _one_artifact(arguments.sdist, "agent_reliability-*.tar.gz", "sdist"),
        include_otel=not arguments.skip_otel,
        include_typing=not arguments.skip_typing,
    )


if __name__ == "__main__":
    main()

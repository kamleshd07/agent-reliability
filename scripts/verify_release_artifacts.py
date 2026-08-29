"""Inspect and smoke-test wheel and sdist in isolated environments."""

from __future__ import annotations

import argparse
import os
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
    for name in sdist_names:
        parts = set(Path(name).parts)
        if parts & forbidden_parts or Path(name).name.startswith(".coverage"):
            raise AssertionError(f"sdist contains local/generated path: {name}")
    print(f"artifact metadata and contents: ok ({version})")
    return version


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
    expected = {
        "basic_reliability.py": "Reliability: 75.00%",
        "async_agent.py": "Async reliability: 2/3 (MET)",
        "provenance_conflict.py": "evaluator_version_mismatch",
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

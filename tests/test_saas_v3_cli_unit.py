"""Fast unit tests for ``synth_datagen.saas_v3.cli`` (P7 coverage hardening).

The existing ``test_saas_v3_cli.py`` runs the full v3 pipeline under
``@pytest.mark.slow`` (≈8s per run); even with it enabled the CLI module
coverage only reaches 41%. These tests cover the pure helpers and the
``ModuleNotFoundError`` runtime-dependency branches that the slow path
cannot reach, without invoking the engine.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from synth_datagen.saas_v3 import cli as cli_module
from synth_datagen.saas_v3.cli import (
    _echo_report,
    _load_runtime,
    _load_validate_runtime,
    _normalize_mode,
    _normalize_validate_mode,
    app,
)

runner = CliRunner()


# --------------------------------------------------------------------------- #
# Pure-function helpers
# --------------------------------------------------------------------------- #


class TestNormalizeMode:
    @pytest.mark.parametrize("value", ["clean", "dirty", "both"])
    def test_accepts_canonical_lowercase(self, value: str) -> None:
        assert _normalize_mode(value) == value

    @pytest.mark.parametrize(
        "value,expected",
        [("CLEAN", "clean"), (" Dirty ", "dirty"), ("BOTH", "both")],
    )
    def test_strips_and_lowercases(self, value: str, expected: str) -> None:
        assert _normalize_mode(value) == expected

    @pytest.mark.parametrize("value", ["unknown", "", "foo", "cleanish"])
    def test_rejects_invalid_with_bad_parameter(self, value: str) -> None:
        with pytest.raises(typer.BadParameter):
            _normalize_mode(value)


class TestNormalizeValidateMode:
    @pytest.mark.parametrize("value", ["clean", "dirty"])
    def test_accepts_canonical(self, value: str) -> None:
        assert _normalize_validate_mode(value) == value

    def test_rejects_both_for_validate(self) -> None:
        # Validate command does not accept "both" — that's the contract
        # difference vs ``_normalize_mode``.
        with pytest.raises(typer.BadParameter):
            _normalize_validate_mode("both")

    @pytest.mark.parametrize("value", ["", "foo", "CLEANED"])
    def test_rejects_invalid(self, value: str) -> None:
        with pytest.raises(typer.BadParameter):
            _normalize_validate_mode(value)


class TestEchoReport:
    def test_passing_report_prints_pass_status(self, capsys) -> None:
        report = SimpleNamespace(mode="clean", passed=True, issues=[])
        _echo_report(report)
        out = capsys.readouterr().out
        assert "clean: PASS" in out

    def test_failing_report_prints_fail_status(self, capsys) -> None:
        report = SimpleNamespace(mode="dirty", passed=False, issues=[])
        _echo_report(report)
        out = capsys.readouterr().out
        assert "dirty: FAIL" in out

    def test_issue_with_table_prefixed_in_output(self, capsys) -> None:
        issue = SimpleNamespace(table="accounts", code="E001", message="bad row")
        report = SimpleNamespace(mode="clean", passed=False, issues=[issue])
        _echo_report(report)
        out = capsys.readouterr().out
        assert "[accounts] E001: bad row" in out

    def test_issue_without_table_omits_brackets(self, capsys) -> None:
        issue = SimpleNamespace(table=None, code="E002", message="global")
        report = SimpleNamespace(mode="clean", passed=False, issues=[issue])
        _echo_report(report)
        out = capsys.readouterr().out
        assert "E002: global" in out
        assert "[" not in out.split("E002")[0].splitlines()[-1]


class TestLoadRuntime:
    """Pin the *identity* of what ``_load_runtime`` returns, not just
    callability. Classes are always callable, so a callable() check would
    happily accept a non-equivalent stub swapped in by a refactor."""

    def test_load_runtime_returns_canonical_5_tuple(self) -> None:
        from synth_datagen.saas_v3.config import OutputMode, load_config
        from synth_datagen.saas_v3.engine import SaaSV3Engine
        from synth_datagen.saas_v3.exporters import SaaSV3Exporter
        from synth_datagen.saas_v3.validate import validate_generated_dataset

        result = _load_runtime()
        assert len(result) == 5
        assert result == (
            OutputMode,
            load_config,
            SaaSV3Engine,
            SaaSV3Exporter,
            validate_generated_dataset,
        )

    def test_load_validate_runtime_returns_canonical_3_tuple(self) -> None:
        from synth_datagen.saas_v3.config import load_config
        from synth_datagen.saas_v3.exporters import SaaSV3Exporter
        from synth_datagen.saas_v3.validate import validate_exported_run

        result = _load_validate_runtime()
        assert result == (load_config, SaaSV3Exporter, validate_exported_run)


# --------------------------------------------------------------------------- #
# Typer surface — invocation paths that don't require the engine
# --------------------------------------------------------------------------- #


def _write_dummy_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("placeholder: true\n", encoding="utf-8")
    return cfg


class TestCliInvalidMode:
    """``--mode`` is rejected before any runtime import — pure typer path."""

    def test_generate_rejects_unknown_mode(self, tmp_path: Path) -> None:
        cfg = _write_dummy_config(tmp_path)
        result = runner.invoke(
            app, ["generate", "--config", str(cfg), "--mode", "unknown"]
        )
        assert result.exit_code != 0
        assert "Mode must be one of" in result.output

    def test_validate_rejects_unknown_mode(self, tmp_path: Path) -> None:
        cfg = _write_dummy_config(tmp_path)
        result = runner.invoke(
            app, ["validate", "--config", str(cfg), "--mode", "nope"]
        )
        assert result.exit_code != 0
        assert "Mode must be one of" in result.output


class TestCliMissingRuntimeDependency:
    """The ``except ModuleNotFoundError`` blocks (lines 47-51, 86-90, 118-122).

    Monkeypatch ``_load_runtime`` / ``_load_validate_runtime`` to raise a
    ``ModuleNotFoundError`` whose ``name`` is in ``RUNTIME_DEPENDENCIES`` so
    the friendly-error path is taken — exit code 1, message on stderr.
    """

    def _missing(self, name: str = "pyarrow"):
        def _raise(*_a: Any, **_k: Any):
            raise ModuleNotFoundError(f"No module named '{name}'", name=name)

        return _raise

    def test_generate_missing_runtime_dep_prints_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _write_dummy_config(tmp_path)
        monkeypatch.setattr(cli_module, "_load_runtime", self._missing("pyarrow"))
        result = runner.invoke(app, ["generate", "--config", str(cfg)])
        assert result.exit_code == 1
        assert "Missing runtime dependency 'pyarrow'" in result.output

    def test_validate_missing_runtime_dep_prints_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _write_dummy_config(tmp_path)
        monkeypatch.setattr(
            cli_module, "_load_validate_runtime", self._missing("pandas")
        )
        result = runner.invoke(app, ["validate", "--config", str(cfg)])
        assert result.exit_code == 1
        assert "Missing runtime dependency 'pandas'" in result.output

    def test_smoke_test_missing_runtime_dep_prints_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _write_dummy_config(tmp_path)
        monkeypatch.setattr(cli_module, "_load_runtime", self._missing("numpy"))
        result = runner.invoke(app, ["smoke-test", "--config", str(cfg)])
        assert result.exit_code == 1
        assert "Missing runtime dependency 'numpy'" in result.output

    def test_generate_unrelated_module_error_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ModuleNotFoundError for a non-runtime module must not be
        swallowed (line 51 ``raise``)."""
        cfg = _write_dummy_config(tmp_path)
        monkeypatch.setattr(
            cli_module, "_load_runtime", self._missing("not_a_real_dep")
        )
        result = runner.invoke(app, ["generate", "--config", str(cfg)])
        # Typer surfaces the un-handled exception as a non-zero exit.
        assert result.exit_code != 0
        assert isinstance(result.exception, ModuleNotFoundError)

    def test_validate_unrelated_module_error_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same contract for ``validate`` — line 90 ``raise``."""
        cfg = _write_dummy_config(tmp_path)
        monkeypatch.setattr(
            cli_module, "_load_validate_runtime", self._missing("not_a_real_dep")
        )
        result = runner.invoke(app, ["validate", "--config", str(cfg)])
        assert result.exit_code != 0
        assert isinstance(result.exception, ModuleNotFoundError)

    def test_smoke_test_unrelated_module_error_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """And ``smoke-test`` — line 122 ``raise``."""
        cfg = _write_dummy_config(tmp_path)
        monkeypatch.setattr(
            cli_module, "_load_runtime", self._missing("not_a_real_dep")
        )
        result = runner.invoke(app, ["smoke-test", "--config", str(cfg)])
        assert result.exit_code != 0
        assert isinstance(result.exception, ModuleNotFoundError)


class TestCliGenerateAndValidateHappyPath:
    """Drive ``generate`` / ``validate`` with stub runtime objects so no
    engine work happens — exercises lines 53-70 and 92-98."""

    def _stub_generate_runtime(
        self,
        clean_passed: bool = True,
        dirty: bool = True,
        dirty_passed: bool = True,
    ):
        captured: dict[str, Any] = {}

        class StubOutputMode:
            CLEAN = "clean"
            DIRTY = "dirty"
            BOTH = "both"

            def __init__(self, value: str) -> None:
                self.value = value

        def stub_load_config(path: Path):
            captured["config_path"] = path
            return SimpleNamespace(name="stub-cfg")

        class StubEngine:
            def __init__(self, cfg: Any, seed_override: int | None = None) -> None:
                self.config = cfg
                captured["seed"] = seed_override

            def generate(self, mode: Any) -> Any:
                captured["generate_mode"] = mode
                return SimpleNamespace(
                    clean=SimpleNamespace(),
                    dirty=SimpleNamespace() if dirty else None,
                )

        class StubExporter:
            def __init__(self, cfg: Any) -> None:
                self.cfg = cfg

            def export_result(
                self,
                result: Any,
                output_override: Path | None = None,
                config_source_path: Path | None = None,
            ) -> dict[str, Path]:
                captured["export_override"] = output_override
                captured["export_config_path"] = config_source_path
                return {"run_root": Path("/fake/run/root")}

            def resolve_run_root(self) -> Path:
                return Path("/fake/run/root")

        def stub_validate_dataset(data: Any, cfg: Any, mode: str):
            return SimpleNamespace(
                mode=mode,
                passed=(clean_passed if mode == "clean" else dirty_passed),
                issues=[],
            )

        return (
            (
                StubOutputMode,
                stub_load_config,
                StubEngine,
                StubExporter,
                stub_validate_dataset,
            ),
            captured,
        )

    def test_generate_happy_path_emits_run_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _write_dummy_config(tmp_path)
        runtime, captured = self._stub_generate_runtime()
        monkeypatch.setattr(cli_module, "_load_runtime", lambda: runtime)
        result = runner.invoke(
            app, ["generate", "--config", str(cfg), "--mode", "clean", "--seed", "7"]
        )
        assert result.exit_code == 0, result.output
        assert "run_root: " in result.output
        assert "clean: PASS" in result.output
        assert captured["seed"] == 7
        assert captured["config_path"] == cfg

    def test_generate_clean_failure_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _write_dummy_config(tmp_path)
        runtime, _ = self._stub_generate_runtime(clean_passed=False)
        monkeypatch.setattr(cli_module, "_load_runtime", lambda: runtime)
        result = runner.invoke(app, ["generate", "--config", str(cfg)])
        assert result.exit_code == 1
        assert "clean: FAIL" in result.output

    def test_generate_dirty_failure_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _write_dummy_config(tmp_path)
        runtime, _ = self._stub_generate_runtime(
            clean_passed=True, dirty=True, dirty_passed=False
        )
        monkeypatch.setattr(cli_module, "_load_runtime", lambda: runtime)
        result = runner.invoke(
            app, ["generate", "--config", str(cfg), "--mode", "both"]
        )
        assert result.exit_code == 1
        assert "dirty: FAIL" in result.output

    def test_generate_no_dirty_skips_dirty_validation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _write_dummy_config(tmp_path)
        runtime, _ = self._stub_generate_runtime(dirty=False)
        monkeypatch.setattr(cli_module, "_load_runtime", lambda: runtime)
        result = runner.invoke(
            app, ["generate", "--config", str(cfg), "--mode", "clean"]
        )
        assert result.exit_code == 0, result.output
        assert "dirty:" not in result.output

    def test_validate_happy_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _write_dummy_config(tmp_path)

        def stub_load_config(path: Path):
            return SimpleNamespace()

        class StubExporter:
            def __init__(self, cfg: Any) -> None:
                pass

            def resolve_run_root(self) -> Path:
                return Path("/fake/run")

        def stub_validate_run(root: Path, cfg: Any, mode: str):
            return SimpleNamespace(mode=mode, passed=True, issues=[])

        monkeypatch.setattr(
            cli_module,
            "_load_validate_runtime",
            lambda: (stub_load_config, StubExporter, stub_validate_run),
        )
        result = runner.invoke(
            app, ["validate", "--config", str(cfg), "--mode", "clean"]
        )
        assert result.exit_code == 0, result.output
        assert "clean: PASS" in result.output

    def test_validate_failure_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _write_dummy_config(tmp_path)

        def stub_load_config(path: Path):
            return SimpleNamespace()

        class StubExporter:
            def __init__(self, cfg: Any) -> None:
                pass

            def resolve_run_root(self) -> Path:
                return Path("/fake/run")

        def stub_validate_run(root: Path, cfg: Any, mode: str):
            return SimpleNamespace(mode=mode, passed=False, issues=[])

        monkeypatch.setattr(
            cli_module,
            "_load_validate_runtime",
            lambda: (stub_load_config, StubExporter, stub_validate_run),
        )
        result = runner.invoke(
            app, ["validate", "--config", str(cfg), "--mode", "dirty"]
        )
        assert result.exit_code == 1
        assert "dirty: FAIL" in result.output

    def test_smoke_test_happy_path_emits_run_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _write_dummy_config(tmp_path)
        runtime, captured = self._stub_generate_runtime()

        # smoke_test references ``cfg.output.root_dir`` when no --output is
        # given; provide a minimal stub config that survives that path.
        smoke_root = tmp_path / "smoke_root"

        def stub_load_config(path: Path):
            return SimpleNamespace(output=SimpleNamespace(root_dir=smoke_root))

        runtime = (runtime[0], stub_load_config, *runtime[2:])
        monkeypatch.setattr(cli_module, "_load_runtime", lambda: runtime)
        result = runner.invoke(app, ["smoke-test", "--config", str(cfg)])
        assert result.exit_code == 0, result.output
        assert "smoke_run_root: " in result.output

    def test_smoke_test_clean_failure_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _write_dummy_config(tmp_path)
        runtime, _ = self._stub_generate_runtime(clean_passed=False)

        def stub_load_config(path: Path):
            return SimpleNamespace(output=SimpleNamespace(root_dir=tmp_path / "x"))

        runtime = (runtime[0], stub_load_config, *runtime[2:])
        monkeypatch.setattr(cli_module, "_load_runtime", lambda: runtime)
        result = runner.invoke(
            app, ["smoke-test", "--config", str(cfg), "--output", str(tmp_path / "out")]
        )
        assert result.exit_code == 1
        assert "clean: FAIL" in result.output

    def test_validate_with_explicit_run_root_skips_resolve(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _write_dummy_config(tmp_path)
        explicit_root = tmp_path / "my_run_root"
        seen: dict[str, Any] = {}

        def stub_load_config(path: Path):
            return SimpleNamespace()

        class StubExporter:
            def __init__(self, cfg: Any) -> None:
                pass

            def resolve_run_root(self) -> Path:
                seen["resolve_called"] = True
                return Path("/never/used")

        def stub_validate_run(root: Path, cfg: Any, mode: str):
            seen["validated_root"] = root
            return SimpleNamespace(mode=mode, passed=True, issues=[])

        monkeypatch.setattr(
            cli_module,
            "_load_validate_runtime",
            lambda: (stub_load_config, StubExporter, stub_validate_run),
        )
        result = runner.invoke(
            app,
            [
                "validate",
                "--config",
                str(cfg),
                "--mode",
                "clean",
                "--run-root",
                str(explicit_root),
            ],
        )
        assert result.exit_code == 0, result.output
        assert seen["validated_root"] == explicit_root
        assert "resolve_called" not in seen

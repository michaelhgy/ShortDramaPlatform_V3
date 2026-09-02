from pathlib import Path

from server.jianying_preflight import JianyingPreflightStatus, require_jianying_ready, run_jianying_preflight


def _runtime(tmp_path: Path, *, draft: bool = True, font: bool = True) -> tuple[dict[str, object], dict[str, str]]:
    app = tmp_path / "JianyingPro" / "Apps" / "5.9.0.11632"
    executable = app / "JianyingPro.exe"; executable.parent.mkdir(parents=True); executable.write_bytes(b"test")
    for path in (app / "Resources" / "DefaultAdjustBundle" / "combine_adjust", app / "Resources" / "DefaultAdjustBundle" / "hsl_v1",
                 tmp_path / "JianyingPro" / "User Data" / "Cache" / "effect", tmp_path / "JianyingPro" / "User Data" / "Cache" / "artistEffect"):
        path.mkdir(parents=True)
    if font:
        (app / "Resources" / "Font" / "SystemFont").mkdir(parents=True)
        (app / "Resources" / "Font" / "SystemFont" / "zh-hans.ttf").write_bytes(b"test")
    draft_root = tmp_path / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft"
    if draft: draft_root.mkdir(parents=True)
    return {"jianying_executable": str(executable), "jianying_draft_root": str(draft_root)}, {"LOCALAPPDATA": str(tmp_path)}


def _run(settings, environ, *, version="5.9.0.11632"):
    return run_jianying_preflight(settings, environ=environ, is_windows=True,
                                  version_reader=lambda _: (version, "test"), interactive_checker=lambda: None,
                                  automation_checker=lambda: None)


def test_no_configuration_needs_configuration(tmp_path):
    assert _run({}, {"LOCALAPPDATA": str(tmp_path)}).status == JianyingPreflightStatus.NEED_CONFIGURATION


def test_invalid_configured_executable_is_not_replaced_by_candidate(tmp_path):
    settings, environ = _runtime(tmp_path)
    settings["jianying_executable"] = str(tmp_path / "other" / "JianyingPro.exe")
    assert _run(settings, environ).status == JianyingPreflightStatus.INVALID_CONFIGURATION


def test_missing_configured_draft_root_is_invalid_configuration(tmp_path):
    settings, environ = _runtime(tmp_path, draft=False)
    assert _run(settings, environ).status == JianyingPreflightStatus.INVALID_CONFIGURATION


def test_valid_59_runtime_is_ready(tmp_path):
    settings, environ = _runtime(tmp_path)
    result = _run(settings, environ)
    assert result.status == JianyingPreflightStatus.READY
    assert result.version == "5.9.0.11632"


def test_other_version_is_unverified(tmp_path):
    settings, environ = _runtime(tmp_path)
    assert _run(settings, environ, version="6.0.0").status == JianyingPreflightStatus.UNSUPPORTED_OR_UNVERIFIED_VERSION


def test_missing_required_resource_is_reported(tmp_path):
    settings, environ = _runtime(tmp_path, font=False)
    result = _run(settings, environ)
    assert result.status == JianyingPreflightStatus.MISSING_RESOURCE
    assert "zh-hans.ttf" in result.message


def test_require_raises_structured_error(tmp_path):
    settings, environ = _runtime(tmp_path, font=False)
    # The public task gate uses real environment checks; this assertion keeps the error contract focused.
    from server import jianying_preflight
    original = jianying_preflight.run_jianying_preflight
    try:
        jianying_preflight.run_jianying_preflight = lambda _: _run(settings, environ)  # type: ignore[assignment]
        try:
            require_jianying_ready(settings)
        except Exception as exc:
            assert getattr(exc, "result").status == JianyingPreflightStatus.MISSING_RESOURCE
        else:
            raise AssertionError("expected preflight error")
    finally:
        jianying_preflight.run_jianying_preflight = original  # type: ignore[assignment]

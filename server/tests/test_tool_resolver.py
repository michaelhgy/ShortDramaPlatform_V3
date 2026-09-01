import tempfile
import unittest
from pathlib import Path

from server.tool_resolver import ToolResolutionError, resolve_tool


class ToolResolverTests(unittest.TestCase):
    def _private_root(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        binary = Path(temporary.name) / "tools" / "ffmpeg" / "bin" / "ffprobe.exe"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"test")
        return temporary, binary

    def test_private_tool_is_used_without_path(self) -> None:
        temporary, binary = self._private_root()
        with temporary:
            actual = resolve_tool("ffprobe", resource_root=Path(temporary.name), frozen=True, which=lambda _name: None)
        self.assertEqual(binary, actual)

    def test_frozen_runtime_never_falls_back_to_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ToolResolutionError, "缺少受控"):
                resolve_tool("ffmpeg", resource_root=Path(temporary), frozen=True, which=lambda _name: "C:/PATH/ffmpeg.exe")

    def test_development_override_precedes_path_when_private_tool_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            override = Path(temporary) / "custom-ffmpeg.exe"; override.write_bytes(b"test")
            actual = resolve_tool("ffmpeg", resource_root=Path(temporary), frozen=False,
                                  environ={"V2_FFMPEG_PATH": str(override)}, which=lambda _name: "C:/PATH/ffmpeg.exe")
        self.assertEqual(override, actual)

    def test_development_path_fallback_remains_available(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            actual = resolve_tool("ffmpeg", resource_root=Path(temporary), frozen=False,
                                  environ={}, which=lambda _name: "C:/PATH/ffmpeg.exe")
        self.assertEqual(Path("C:/PATH/ffmpeg.exe"), actual)


if __name__ == "__main__":
    unittest.main()

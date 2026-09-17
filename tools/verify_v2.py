"""V2 一键验证：后端测试 + 前端类型检查。

用法（在项目根目录或双击 tools\\一键验证.bat）：
    py -3.12 tools\\verify_v2.py

安全保证：脚本会把 V2_WORKSPACE_ROOT 指向一个临时目录，
所以测试永远不会读写 D:\\短剧推广运营系统 里的真实业务数据。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 保证中文输出在各控制台都不乱码。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

# 已知失败（历史遗留的测试隔离缺陷，不是产品缺陷）：
KNOWN_FAILURES = {
    "server/tests/test_v2_task_center.py::V2TaskCenterExecutorOwnershipTests::"
    "test_observing_output_is_presented_as_an_active_export",
    "server/tests/test_v2_task_center.py::V2TaskCenterExecutorOwnershipTests::"
    "test_snapshot_keeps_a_complete_executor_payload",
}


def _run(title: str, command: list[str], env: dict[str, str]) -> bool:
    print(f"\n=== {title} ===", flush=True)
    print("$ " + " ".join(command), flush=True)
    try:
        result = subprocess.run(command, cwd=ROOT, env=env)
    except FileNotFoundError as error:
        print(f"[跳过] 找不到命令：{error}")
        return False
    return result.returncode == 0


def main() -> int:
    workspace = Path(tempfile.mkdtemp(prefix="v2_verify_"))
    env = dict(os.environ)
    env["V2_WORKSPACE_ROOT"] = str(workspace)
    env["PYTHONIOENCODING"] = "utf-8"

    print("V2 一键验证")
    print(f"项目目录：{ROOT}")
    print(f"临时工作区（隔离用，可随时删除）：{workspace}")
    print("真实业务数据不会被读写。")

    backend_ok = _run(
        "1/2 后端测试",
        [sys.executable, "-m", "pytest", "server/tests", "-q", "--no-header"],
        env,
    )

    npm = shutil.which("npm")
    frontend_ok = (
        _run("2/2 前端类型检查", [npm, "run", "lint"], env) if npm else False
    )
    if not npm:
        print("\n[跳过] 找不到 npm，无法做前端类型检查。")

    print("\n================ 结论 ================")
    print(f"后端测试：{'通过' if backend_ok else '有失败'}")
    print(f"前端类型检查：{'通过' if frontend_ok else '未通过/跳过'}")
    if not backend_ok:
        print("\n如果是下面这 2 个失败，属于已知的测试隔离缺陷，可忽略：")
        for name in sorted(KNOWN_FAILURES):
            print(f"  - {name.split('::')[-1]}")
    print("======================================")

    shutil.rmtree(workspace, ignore_errors=True)
    return 0 if (backend_ok and frontend_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())

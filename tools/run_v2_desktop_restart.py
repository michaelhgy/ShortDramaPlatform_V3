"""V3 compatibility entry: open the copied runtime without stopping V2."""

from __future__ import annotations

import os

from run_v2_desktop import StartupCancelled, main, report_startup_failure


if __name__ == "__main__":
    os.environ["V2_DESKTOP_TITLE"] = "短剧推广运营系统 V3（开发版）"
    try:
        main()
    except StartupCancelled:
        pass
    except Exception as exc:
        report_startup_failure(exc)
        raise SystemExit(1) from exc

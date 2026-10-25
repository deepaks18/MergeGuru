"""Canonical launcher for MergeGuru Lite v3."""

import os
import sys


def _self_test_report(args):
    """Return the requested report path without assuming bootloader argv length."""
    for index, argument in enumerate(args[1:], start=1):
        if argument == "--self-test":
            if index + 1 >= len(args) or not args[index + 1].strip():
                raise ValueError("--self-test requires a report path")
            return args[index + 1]
        if argument.startswith("--self-test="):
            report_path = argument.split("=", 1)[1].strip()
            if not report_path:
                raise ValueError("--self-test requires a report path")
            return report_path
    return None


def main(argv=None):
    args = list(sys.argv if argv is None else argv)
    try:
        report_path = os.environ.get("MERGEGURU_SELF_TEST_REPORT") or _self_test_report(args)
    except ValueError:
        return 2
    if report_path is not None:
        try:
            import pyi_splash
        except Exception:
            pyi_splash = None
        if pyi_splash is not None:
            try:
                pyi_splash.close()
            except RuntimeError:
                pass
        from mergeguru_diagnostics import run_self_test
        from mergeguru_lite_v3.app import MergeGuruLiteV3

        return run_self_test(report_path, MergeGuruLiteV3, None)
    from mergeguru_lite_v3.app import MergeGuruLiteV3

    MergeGuruLiteV3().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

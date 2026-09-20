"""PyInstaller entry point for the self-contained JaneConverter CLI engine."""

from pathlib import Path
import sys

from run_converter import main


def _remove_source_script_argument() -> None:
    """Accept the same argv shape as ``python run_converter.py ...``."""
    if len(sys.argv) > 1 and Path(sys.argv[1]).name.lower() == "run_converter.py":
        del sys.argv[1]


if __name__ == "__main__":
    _remove_source_script_argument()
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Interrupted by user.")
        sys.exit(130)
    except (RuntimeError, ValueError, FileNotFoundError) as error:
        print(f"\n[!] Error: {error}")
        sys.exit(1)

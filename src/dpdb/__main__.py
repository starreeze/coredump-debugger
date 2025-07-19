import importlib.util
import os
import shutil
import sys

from .core_dump import install_global_handler, load_core_dump
from .interface import debug_core_dump


def run_program_with_handler(program_path: str, args: list):
    """Run a Python program with global core dump handler installed."""
    # Install the global handler before running the program
    install_global_handler()

    # Save original sys.argv to restore later
    original_argv = sys.argv.copy()

    try:
        # Set sys.argv to include the program path and its arguments
        sys.argv = [program_path] + args

        # Load and run the program module
        spec = importlib.util.spec_from_file_location("__main__", program_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module from {program_path}")

        module = importlib.util.module_from_spec(spec)

        # Set the module's __name__ to "__main__" so it runs as the main module
        module.__name__ = "__main__"

        # Execute the module
        spec.loader.exec_module(module)

        return 0
    except KeyboardInterrupt:
        print("\nProgram interrupted by user")
        return 130
    except SystemExit as e:
        # Handle sys.exit() calls from the program
        if hasattr(e, "code") and e.code is not None:
            return e.code
        return 0
    except ImportError as e:
        print(f"Error loading program: {e}")
        return 1
    finally:
        # Restore original sys.argv
        sys.argv = original_argv


def find_script_path(script_name: str) -> str | None:
    """Find the full path of a script in the system PATH."""
    # First try to find it as-is
    script_path = shutil.which(script_name)
    if script_path:
        return script_path

    # Try with .py extension
    script_path = shutil.which(f"{script_name}.py")
    if script_path:
        return script_path

    # Try without extension but looking for Python scripts
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not path_dir:
            continue
        potential_path = os.path.join(path_dir, script_name)
        if os.path.isfile(potential_path):
            # Check if it's a Python script by reading the first line
            try:
                with open(potential_path, "rb") as f:
                    first_line = f.readline().decode("utf-8", errors="ignore")
                    if first_line.startswith("#!") and "python" in first_line.lower():
                        return potential_path
            except (OSError, IOError, UnicodeDecodeError):
                continue

    return None


def main():
    """Main entry point for the dpdb console script."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  dpdb <dump_file>                    # Debug an existing core dump")
        print("  dpdb <program.py> [args...]         # Run program with core dump handler")
        print("  dpdb <command> [args...]            # Run system command with core dump handler")
        sys.exit(1)

    # Handle help flag
    if sys.argv[1] in ["--help", "-h"]:
        print("Usage:")
        print("  dpdb <dump_file>                    # Debug an existing core dump")
        print("  dpdb <program.py> [args...]         # Run program with core dump handler")
        print("  dpdb <command> [args...]            # Run system command with core dump handler")
        print()
        print("Examples:")
        print("  dpdb crash_dump.pkl                 # Debug a core dump file")
        print("  dpdb my_program.py arg1 arg2        # Run program with core dump handler")
        print("  dpdb accelerate config               # Run accelerate with core dump handler")
        sys.exit(0)

    # Check if the first argument is a Python file
    program_path = sys.argv[1]

    if program_path.endswith(".pkl"):
        # Mode 1: Debug existing core dump (original functionality)
        if len(sys.argv) == 2:
            if not os.path.isfile(program_path):
                print(f"Error: File '{program_path}' not found or not a file")
                sys.exit(1)
            dump = load_core_dump(sys.argv[1])
            debug_core_dump(dump)
        else:
            print("Usage: dpdb <dump_file>")
            sys.exit(1)
    else:
        # Mode 2: Run program/command with global handler
        program_args = sys.argv[2:]

        # Check if it's a file path first
        if os.path.isfile(program_path):
            # It's a file, run it directly
            exit_code = run_program_with_handler(program_path, program_args)
            sys.exit(exit_code)
        else:
            # Try to find it as a system command
            script_path = find_script_path(program_path)
            if script_path:
                # Found a script in PATH, run it
                exit_code = run_program_with_handler(script_path, program_args)
                sys.exit(exit_code)
            else:
                print(f"Error: '{program_path}' not found as a file or Python script in PATH")
                print("Note: dpdb only supports Python scripts, not binary executables")
                sys.exit(1)


if __name__ == "__main__":
    main()

"""
Python Core Dump System for Post-Mortem Debugging

This module provides functionality to create "core dumps" of Python execution
state, similar to C++ core dumps, which can be loaded later for post-mortem
debugging with pdb-like capabilities.
"""

import datetime
import inspect
import os
import pickle
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class FrameInfo:
    """Information about a single frame in the call stack."""

    filename: str
    function_name: str
    line_number: int
    code_context: List[str]
    locals_dict: Dict[str, Any]
    globals_dict: Dict[str, Any]
    frame_id: int
    context_start_line: int = 0  # Line number where code_context starts


@dataclass
class CoreDump:
    """Complete core dump containing all execution state."""

    timestamp: str
    exception_info: Optional[Tuple[str, str, Any]]  # Changed to strings to avoid pickle issues
    traceback_text: str
    frames: List[FrameInfo]
    current_frame_id: int
    python_version: str
    working_directory: str
    command_line: List[str]
    environment_vars: Dict[str, str] = field(default_factory=dict)


class CoreDumpGenerator:
    """Generates core dumps from Python execution state."""

    @staticmethod
    def _serialize_object(obj: Any) -> Any:
        """
        Safely serialize an object, handling non-serializable types.
        """
        # Handle functions and methods specially
        if callable(obj) and hasattr(obj, "__name__"):
            return f"<function {obj.__name__} at {hex(id(obj))}>"

        # Handle modules
        if hasattr(obj, "__file__") and hasattr(obj, "__name__"):
            return f"<module '{obj.__name__}' from '{obj.__file__}'>"

        try:
            # Test if object is pickle-able
            pickle.dumps(obj)
            return obj
        except (TypeError, pickle.PicklingError, AttributeError):
            # For non-serializable objects, store a representation
            try:
                if hasattr(obj, "__dict__"):
                    return f"<{type(obj).__name__} object at {hex(id(obj))}>"
                else:
                    return repr(obj)
            except Exception:
                return f"<unprintable {type(obj).__name__} object>"

    @staticmethod
    def _clean_dict(d: Dict[str, Any]) -> Dict[str, Any]:
        """Clean a dictionary by serializing all values safely."""
        cleaned = {}
        for key, value in d.items():
            try:
                cleaned[key] = CoreDumpGenerator._serialize_object(value)
            except Exception:
                cleaned[key] = f"<failed to serialize {type(value).__name__}>"
        return cleaned

    @classmethod
    def create_from_exception(cls, exc_type: type, exc_value: BaseException, exc_traceback) -> CoreDump:
        """Create a core dump from an exception's traceback."""
        frames = []
        frame_id = 0

        # Walk through the traceback
        tb = exc_traceback
        while tb is not None:
            frame = tb.tb_frame

            # Skip frames from core_dump.py to avoid including core dump generation in the stack
            if frame.f_code.co_filename.endswith("core_dump.py"):
                tb = tb.tb_next
                continue

            # Get code context
            try:
                # Read the file directly for more reliable context
                # Try different encodings to handle various file types
                all_lines = None
                try:
                    with open(frame.f_code.co_filename, "r", encoding="utf-8") as f:
                        all_lines = f.readlines()
                except (UnicodeDecodeError, UnicodeError):
                    continue

                if all_lines is None:
                    # If all encodings fail, fall back to binary mode and decode with errors='replace'
                    with open(frame.f_code.co_filename, "rb") as f:
                        content = f.read()
                    all_lines = content.decode("utf-8", errors="replace").splitlines(keepends=True)

                current_line = tb.tb_lineno
                # Get context around the current line (3 lines before and after)
                context_start = max(0, current_line - 4)  # -4 because line numbers are 1-based
                context_end = min(len(all_lines), current_line + 3)
                code_context = [line.rstrip() for line in all_lines[context_start:context_end]]
                # Calculate the actual line number where the context starts
                context_start_line = context_start + 1  # +1 because line numbers are 1-based
            except (OSError, IOError):
                code_context = ["<source not available>"]
                context_start_line = tb.tb_lineno

            # Create frame info
            frame_info = FrameInfo(
                filename=frame.f_code.co_filename,
                function_name=frame.f_code.co_name,
                line_number=tb.tb_lineno,
                code_context=code_context,
                locals_dict=cls._clean_dict(frame.f_locals),
                globals_dict=cls._clean_dict(
                    {
                        k: v
                        for k, v in frame.f_globals.items()
                        if not k.startswith("__") or k in ["__name__", "__file__"]
                    }
                ),
                frame_id=frame_id,
                context_start_line=context_start_line,
            )
            frames.append(frame_info)

            tb = tb.tb_next
            frame_id += 1

        # Create the core dump
        # Store exception info as strings to avoid pickle issues
        exception_info_safe = None
        if exc_type and exc_value:
            exception_info_safe = (exc_type.__name__, str(exc_value), None)

        return CoreDump(
            timestamp=datetime.datetime.now().isoformat(),
            exception_info=exception_info_safe,
            traceback_text="".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
            frames=frames,
            current_frame_id=(
                len(frames) - 1 if frames else 0
            ),  # Start at newest frame (where exception occurred)
            python_version=sys.version,
            working_directory=os.getcwd(),
            command_line=sys.argv,
            environment_vars={k: v for k, v in os.environ.items() if not k.startswith("_")},
        )

    @classmethod
    def create_from_current_stack(cls) -> CoreDump:
        """Create a core dump from the current call stack."""
        frames = []
        frame_id = 0

        # Get current frame and walk up the stack
        current_frame = inspect.currentframe()
        # Skip this function's frame
        if current_frame is not None:
            current_frame = current_frame.f_back

        while current_frame is not None:
            # Skip frames from core_dump.py to avoid including core dump generation in the stack
            if current_frame.f_code.co_filename.endswith("core_dump.py"):
                current_frame = current_frame.f_back
                continue

            # Get code context
            try:
                # Read the file directly for more reliable context
                # Try different encodings to handle various file types
                all_lines = None
                for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                    try:
                        with open(current_frame.f_code.co_filename, "r", encoding=encoding) as f:
                            all_lines = f.readlines()
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue

                if all_lines is None:
                    # If all encodings fail, fall back to binary mode and decode with errors='replace'
                    with open(current_frame.f_code.co_filename, "rb") as f:
                        content = f.read()
                    all_lines = content.decode("utf-8", errors="replace").splitlines(keepends=True)

                current_line = current_frame.f_lineno
                # Get context around the current line (3 lines before and after)
                context_start = max(0, current_line - 4)  # -4 because line numbers are 1-based
                context_end = min(len(all_lines), current_line + 3)
                code_context = [line.rstrip() for line in all_lines[context_start:context_end]]
                # Calculate the actual line number where the context starts
                context_start_line = context_start + 1  # +1 because line numbers are 1-based
            except (OSError, IOError):
                code_context = ["<source not available>"]
                context_start_line = current_frame.f_lineno

            # Create frame info
            frame_info = FrameInfo(
                filename=current_frame.f_code.co_filename,
                function_name=current_frame.f_code.co_name,
                line_number=current_frame.f_lineno,
                code_context=code_context,
                locals_dict=cls._clean_dict(current_frame.f_locals),
                globals_dict=cls._clean_dict(
                    {
                        k: v
                        for k, v in current_frame.f_globals.items()
                        if not k.startswith("__") or k in ["__name__", "__file__"]
                    }
                ),
                frame_id=frame_id,
                context_start_line=context_start_line,
            )
            frames.append(frame_info)

            current_frame = current_frame.f_back
            frame_id += 1

        return CoreDump(
            timestamp=datetime.datetime.now().isoformat(),
            exception_info=None,
            traceback_text="<Manual core dump - no exception>",
            frames=frames,
            current_frame_id=0,
            python_version=sys.version,
            working_directory=os.getcwd(),
            command_line=sys.argv,
        )


def save_core_dump(core_dump: CoreDump, filename: str):
    """Save a core dump to a file."""
    with open(filename, "wb") as f:
        pickle.dump(core_dump, f)
    print(f"Core dump saved to: {filename}")


def load_core_dump(filename: str) -> CoreDump:
    """Load a core dump from a file."""
    with open(filename, "rb") as f:
        return pickle.load(f)


def install_exception_handler(dump_filename: str = "core_dump.pkl"):
    """Install a global exception handler that creates core dumps."""

    def exception_handler(exc_type, exc_value, exc_traceback):
        # Don't create core dump for KeyboardInterrupt or signal-related exceptions
        if exc_type == KeyboardInterrupt:
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        # Check for signal-related exceptions
        # SystemExit can be raised by signal handlers or sys.exit()
        if exc_type == SystemExit:
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        # Check if this is a signal-related exception by examining the exception value
        if exc_value is not None:
            # Some signal handlers might raise custom exceptions with signal info
            exc_str = str(exc_value).lower()
            if any(signal_name in exc_str for signal_name in ["sigterm", "sigint", "sigkill", "signal"]):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return

        print("\nUnhandled exception occurred. Creating core dump...")
        core_dump = CoreDumpGenerator.create_from_exception(exc_type, exc_value, exc_traceback)
        save_core_dump(core_dump, dump_filename)

        # Still print the original traceback
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = exception_handler


def _core_dump_wrapper(target, process_name, *args, **kwargs):
    """Wrapper function that creates core dumps on exceptions."""
    try:
        # Run the target function
        return target(*args, **kwargs)
    except (KeyboardInterrupt, SystemExit):
        # Don't create core dumps for signal-related exceptions
        raise
    except Exception:
        # Check if this is a signal-related exception
        exc_type, exc_value, exc_traceback = sys.exc_info()

        if exc_value is not None:
            # Check if this is a signal-related exception by examining the exception value
            exc_str = str(exc_value).lower()
            if any(signal_name in exc_str for signal_name in ["sigterm", "sigint", "sigkill", "signal"]):
                raise  # Re-raise signal-related exceptions without creating core dumps

        # Create core dump on any other unhandled exception
        print(f"\nUnhandled exception in {process_name}. Creating core dump...")

        if exc_type and exc_value and exc_traceback:
            dump_filename = f"{process_name}_crash.pkl"
            core_dump = CoreDumpGenerator.create_from_exception(exc_type, exc_value, exc_traceback)
            save_core_dump(core_dump, dump_filename)

        # Re-raise the exception to maintain normal error behavior
        raise


# Global flag to track if monkey patching is installed
_monkey_patch_installed = False
_original_process_init: Optional[Any] = None


class _WrappedTarget:
    """Picklable wrapper for target functions with core dump handling."""

    def __init__(self, target, process_name):
        self.target = target
        self.process_name = process_name

    def __call__(self, *args, **kwargs):
        return _core_dump_wrapper(self.target, self.process_name, *args, **kwargs)


def _patched_process_init(self, group=None, target=None, name=None, args=(), kwargs=None, *, daemon=None):
    """Patched Process.__init__ that automatically wraps target with core dump handling."""
    if kwargs is None:
        kwargs = {}

    # If target is provided, wrap it with core dump handling
    if target is not None:
        process_name = name or f"Process-{id(target)}"
        target = _WrappedTarget(target, process_name)

    # Call the original __init__ method
    if _original_process_init is not None:
        _original_process_init(
            self, group=group, target=target, name=name, args=args, kwargs=kwargs, daemon=daemon
        )


def install_global_handler():
    """
    Install global core dump handler that automatically applies to all processes.

    This function monkey patches the multiprocessing.Process class to automatically
    wrap all process targets with core dump handling. This provides better compatibility
    with existing code and frameworks like accelerate that control process creation.
    """
    global _monkey_patch_installed, _original_process_init

    if _monkey_patch_installed:
        return

    # Install handler for current process
    install_exception_handler(f"main_process_{os.getpid()}_crash.pkl")

    # Monkey patch multiprocessing.Process
    import multiprocessing as mp

    # Store original __init__ method
    if _original_process_init is None:
        _original_process_init = mp.Process.__init__
        mp.Process.__init__ = _patched_process_init

    _monkey_patch_installed = True
    print(
        "Global core dump handler installed - all processes will automatically generate core dumps on crashes"
    )


def uninstall_global_handler():
    """Uninstall the global core dump handler and restore original multiprocessing behavior."""
    global _monkey_patch_installed, _original_process_init

    if not _monkey_patch_installed:
        return

    import multiprocessing as mp

    # Restore original __init__ method
    if _original_process_init is not None:
        mp.Process.__init__ = _original_process_init
        _original_process_init = None

    # Restore original exception handler
    sys.excepthook = sys.__excepthook__

    _monkey_patch_installed = False
    print("Global core dump handler uninstalled")

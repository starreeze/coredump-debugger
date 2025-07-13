"""
Post-mortem debugger interface that mimics pdb behavior.

This module provides an interactive debugging interface for core dumps,
with commands and behavior similar to Python's built-in pdb debugger.
"""

import cmd
import inspect
import os
from typing import Any, Dict, Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from .core_dump import CoreDump, FrameInfo

# Try to import term_background for better terminal background detection
try:
    import term_background  # type: ignore

    HAS_TERM_BACKGROUND = True
except ImportError:
    HAS_TERM_BACKGROUND = False


class PostMortemDebugger(cmd.Cmd):
    """Interactive debugger for core dumps, mimicking pdb interface."""

    intro = "Post-mortem debugger (similar to pdb). Type help or ? to list commands.\n"
    prompt = "(Dpdb) "

    def __init__(self, core_dump: CoreDump):
        super().__init__()
        self.core_dump = core_dump
        self.current_frame_index = core_dump.current_frame_id  # Use frame from core dump
        self.frames = core_dump.frames
        self.console = Console()

        # Detect terminal background and set appropriate theme
        self._setup_theme()

        # Create mutable namespaces for each frame to persist variables
        self.frame_namespaces = []
        for frame in self.frames:
            # Create a combined namespace for each frame
            namespace = frame.globals_dict.copy()
            namespace.update(frame.locals_dict)
            self.frame_namespaces.append(namespace)

        if not self.frames:
            self.console.print(
                f"[{self.colors['error']}]No frames available in core dump[/{self.colors['error']}]"
            )
            return

        # Display initial information with adaptive formatting
        self.console.print(
            f"[{self.colors['info']}]Core dump from {core_dump.timestamp}[/{self.colors['info']}]"
        )
        if core_dump.exception_info:
            self.console.print(
                f"[{self.colors['error']}]Exception: {core_dump.exception_info[0]}: {core_dump.exception_info[1]}[/{self.colors['error']}]"
            )
        self.console.print(
            f"[{self.colors['success']}]Total frames: {len(self.frames)}[/{self.colors['success']}]"
        )
        self._show_current_frame()

    def _setup_theme(self):
        """Setup colors and theme based on terminal background using multiple detection methods."""
        # Try to detect if we're on a light background using multiple methods
        is_light_bg = self._detect_light_background()

        if is_light_bg:
            # Light background color scheme
            self.colors = {
                "error": "red",
                "warning": "dark_orange",
                "success": "dark_green",
                "info": "blue",
                "highlight": "purple",
                "filename": "blue",
                "line_number": "dark_orange",
                "function": "dark_green",
                "variable_name": "blue",
                "variable_type": "purple",
                "variable_value": "dark_green",
                "frame_border": "blue",
                "table_border": "blue",
            }
            self.syntax_theme = "github-light"
        else:
            # Dark background color scheme (default)
            self.colors = {
                "error": "red",
                "warning": "yellow",
                "success": "green",
                "info": "cyan",
                "highlight": "magenta",
                "filename": "cyan",
                "line_number": "yellow",
                "function": "green",
                "variable_name": "cyan",
                "variable_type": "magenta",
                "variable_value": "green",
                "frame_border": "blue",
                "table_border": "blue",
            }
            self.syntax_theme = "monokai"

    def _detect_light_background(self):
        """Attempt to detect if terminal has a light background using multiple methods."""
        # Method 1: Check for explicit environment variable override first
        theme_override = os.environ.get("DPDB_THEME", "").lower()
        if theme_override == "light":
            return True
        elif theme_override == "dark":
            return False

        # Method 2: Use term_background library if available (most reliable)
        if HAS_TERM_BACKGROUND:
            try:
                return not term_background.is_dark_background()
            except Exception:
                # If term_background fails, continue to other methods
                pass

        # Method 3: Use Rich's color system detection combined with environment hints
        color_system = self.console._color_system

        # Check environment variables that might indicate light themes
        terminal_program = os.environ.get("TERM_PROGRAM", "").lower()
        colorterm = os.environ.get("COLORTERM", "").lower()

        # Some terminals/programs that commonly use light backgrounds by default
        light_terminals = ["apple_terminal", "terminal.app", "iterm.app", "hyper"]

        # Check for explicit light theme indicators
        if any(term in terminal_program for term in light_terminals):
            return True

        # Method 4: Check COLORFGBG environment variable
        # Format is usually "foreground;background" where higher numbers = lighter
        colorfgbg = os.environ.get("COLORFGBG", "")
        if colorfgbg:
            try:
                parts = colorfgbg.split(";")
                if len(parts) >= 2:
                    bg_color = int(parts[-1])  # Background is typically the last part
                    # In COLORFGBG, higher numbers typically indicate lighter colors
                    # 15 is typically white, 0 is typically black
                    if bg_color >= 7:  # 7 is typically light gray or white
                        return True
            except (ValueError, IndexError):
                pass

        # Method 5: Check for light-themed terminal emulators based on TERM
        term = os.environ.get("TERM", "").lower()
        if "light" in term:
            return True

        # Method 6: Check for Windows Terminal with light theme
        if os.name == "nt":
            wt_profile = os.environ.get("WT_PROFILE_ID", "")
            if wt_profile:
                # Windows Terminal is present, but we can't easily detect theme
                # Default to dark unless other indicators suggest light
                pass

        # Method 7: Check for common light theme environment variables
        light_theme_vars = ["LIGHT_THEME", "THEME_LIGHT", "BACKGROUND_LIGHT"]

        for var in light_theme_vars:
            if os.environ.get(var, "").lower() in ("1", "true", "yes", "on"):
                return True

        # Method 8: Fallback - try to use Rich's terminal detection capabilities
        # If we have truecolor support, we might be able to make a better guess
        if color_system and hasattr(color_system, "name"):
            # This is a heuristic: some modern terminals default to light themes
            if self.console.is_terminal and not self.console.is_dumb_terminal:
                # Check if we're in a modern terminal environment
                if colorterm in ("truecolor", "24bit"):
                    # Modern terminals - could be either, default to dark
                    pass

        # Default to dark theme if we can't detect reliably
        return False

    def _show_current_frame(self):
        """Display information about the current frame with rich formatting."""
        if not self.frames or self.current_frame_index >= len(self.frames):
            self.console.print(f"[{self.colors['error']}]No current frame[/{self.colors['error']}]")
            return

        frame = self.frames[self.current_frame_index]

        # Create a panel with frame information
        filename = os.path.basename(frame.filename)
        frame_info = f"[{self.colors['filename']}]{filename}[/{self.colors['filename']}]:[{self.colors['line_number']}]{frame.line_number}[/{self.colors['line_number']}] in [{self.colors['function']}]{frame.function_name}[/{self.colors['function']}]()"

        panel = Panel(
            frame_info,
            title=f"Frame {self.current_frame_index}",
            border_style=self.colors["frame_border"],
            box=box.ROUNDED,
        )
        self.console.print(panel)

        if frame.code_context:
            self._display_code_context(frame)

    def _display_code_context(self, frame: FrameInfo):
        """Display code context with syntax highlighting."""
        if not frame.code_context:
            return

        # Prepare code with line numbers
        code_lines = []
        for i, line in enumerate(frame.code_context):
            line_number = frame.context_start_line + i
            marker = "→" if line_number == frame.line_number else " "
            code_lines.append(f"{marker} {line}")

        # Join lines for syntax highlighting
        code_text = "\n".join(code_lines)

        # Create syntax highlighted code
        syntax = Syntax(
            code_text,
            "python",
            theme=self.syntax_theme,
            line_numbers=True,
            start_line=frame.context_start_line,
            highlight_lines={frame.line_number},
        )

        self.console.print(syntax)

    def _get_current_frame(self) -> Optional[FrameInfo]:
        """Get the current frame info."""
        if not self.frames or self.current_frame_index >= len(self.frames):
            return None
        return self.frames[self.current_frame_index]

    def _get_namespace(self) -> Dict[str, Any]:
        """Get the mutable namespace for the current frame."""
        if self.current_frame_index >= len(self.frame_namespaces):
            return {}
        return self.frame_namespaces[self.current_frame_index]

    def default(self, line: str):
        """Handle non-command input - execute as Python code."""
        line = line.strip()
        if not line:
            return

        try:
            self._execute_code(line)
        except Exception as e:
            self.console.print(
                f"[{self.colors['error']}]*** {type(e).__name__}: {e}[/{self.colors['error']}]"
            )

    def _execute_code(self, code: str):
        """Execute Python code in the context of the current frame."""
        frame = self._get_current_frame()
        if not frame:
            self.console.print(f"[{self.colors['error']}]No current frame[/{self.colors['error']}]")
            return

        namespace = self._get_namespace()

        try:
            # Try to compile as an expression first
            compiled = compile(code, "<debugger>", "eval")
            result = eval(compiled, namespace)
            if result is not None:
                # Use rich's pretty printing for results
                self.console.print(result)
        except SyntaxError:
            # If it fails as expression, try as statement(s)
            try:
                compiled = compile(code, "<debugger>", "exec")
                exec(compiled, namespace)
                # After execution, the namespace is automatically updated
                # because we're using the same dictionary reference
            except Exception as e:
                raise e
        except Exception as e:
            raise e

    # Navigation commands
    def do_up(self, arg: str):
        """u(p) [count]
        Move the current frame count (default one) levels up in the stack trace
        (to an older frame).
        """
        try:
            count = int(arg) if arg else 1
        except ValueError:
            self.console.print(f"[{self.colors['error']}]*** Invalid number[/{self.colors['error']}]")
            return

        new_index = self.current_frame_index - count
        if new_index < 0:
            self.console.print(f"[{self.colors['warning']}]*** Oldest frame[/{self.colors['warning']}]")
        else:
            self.current_frame_index = new_index
            self._show_current_frame()

    def do_u(self, arg: str):
        """Alias for up."""
        self.do_up(arg)

    def do_down(self, arg: str):
        """d(own) [count]
        Move the current frame count (default one) levels down in the stack trace
        (to a newer frame).
        """
        try:
            count = int(arg) if arg else 1
        except ValueError:
            self.console.print(f"[{self.colors['error']}]*** Invalid number[/{self.colors['error']}]")
            return

        new_index = self.current_frame_index + count
        if new_index >= len(self.frames):
            self.console.print(f"[{self.colors['warning']}]*** Newest frame[/{self.colors['warning']}]")
        else:
            self.current_frame_index = new_index
            self._show_current_frame()

    def do_d(self, arg: str):
        """Alias for down."""
        self.do_down(arg)

    def do_where(self, arg: str):
        """w(here)
        Print a stack trace, with the most recent frame at the bottom.
        An arrow indicates the current frame, which determines the context of most commands.
        """
        table = Table(title="Stack Trace", box=box.ROUNDED)
        table.add_column("Frame", style=self.colors["info"], no_wrap=True)
        table.add_column("File", style=self.colors["filename"])
        table.add_column("Line", style=self.colors["line_number"], justify="right")
        table.add_column("Function", style=self.colors["function"])

        for i, frame in enumerate(reversed(self.frames)):
            frame_idx = len(self.frames) - 1 - i
            marker = "→" if frame_idx == self.current_frame_index else " "

            filename = os.path.basename(frame.filename)

            table.add_row(f"{marker} {frame_idx}", filename, str(frame.line_number), frame.function_name)

        self.console.print(table)

    def do_w(self, arg: str):
        """Alias for where."""
        self.do_where(arg)

    def do_bt(self, arg: str):
        """Alias for where."""
        self.do_where(arg)

    def do_frames(self, arg: str):
        """frames
        Print a detailed list of all frames in the call stack.
        Shows frame number, filename, line number, and function name.
        """
        if not self.frames:
            self.console.print(f"[{self.colors['error']}]No frames available[/{self.colors['error']}]")
            return

        table = Table(title="Detailed Frame Information", box=box.ROUNDED)
        table.add_column("Frame", style=self.colors["info"], no_wrap=True)
        table.add_column("File", style=self.colors["filename"])
        table.add_column("Line", style=self.colors["line_number"], justify="right")
        table.add_column("Function", style=self.colors["function"])
        table.add_column("Code", style="white")

        for i, frame in enumerate(reversed(self.frames)):
            frame_idx = len(self.frames) - 1 - i
            marker = "→" if frame_idx == self.current_frame_index else " "

            # Get relative path for cleaner display
            filename = os.path.basename(frame.filename)

            # Get the executing line of code
            code_line = ""
            if frame.code_context and len(frame.code_context) > 0:
                context_line_idx = frame.line_number - frame.context_start_line
                if 0 <= context_line_idx < len(frame.code_context):
                    code_line = frame.code_context[context_line_idx].strip()

            table.add_row(
                f"{marker} {frame_idx}",
                filename,
                str(frame.line_number),
                frame.function_name,
                code_line[:50] + "..." if len(code_line) > 50 else code_line,
            )

        self.console.print(table)

    def do_f(self, arg: str):
        """f(rame) [frame_number]
        Select a frame by number. Without argument, print current frame info.
        """
        if not arg:
            self._show_current_frame()
            return

        try:
            frame_num = int(arg)
            if frame_num < 0 or frame_num >= len(self.frames):
                self.console.print(
                    f"[{self.colors['error']}]*** Frame number must be between 0 and {len(self.frames) - 1}[/{self.colors['error']}]"
                )
                return

            self.current_frame_index = frame_num
            self._show_current_frame()
        except ValueError:
            self.console.print(f"[{self.colors['error']}]*** Invalid frame number[/{self.colors['error']}]")

    def do_frame(self, arg: str):
        """Alias for f."""
        self.do_f(arg)

    # Information commands
    def do_list(self, arg: str):
        """l(ist) [first [, last]]
        List source code for the current file. Without arguments, list 11 lines
        around the current line or continue the previous listing.
        """
        frame = self._get_current_frame()
        if not frame or not frame.code_context:
            self.console.print(
                f"[{self.colors['error']}]*** No source code available[/{self.colors['error']}]"
            )
            return

        self._display_code_context(frame)

    def do_l(self, arg: str):
        """Alias for list."""
        self.do_list(arg)

    def do_locals(self, arg: str):
        """locals
        Print the local variables of the current frame.
        """
        frame = self._get_current_frame()
        if not frame:
            self.console.print(f"[{self.colors['error']}]No current frame[/{self.colors['error']}]")
            return

        # Show current state of the namespace (including any new variables)
        namespace = self._get_namespace()
        locals_vars = {k: v for k, v in namespace.items() if k in frame.locals_dict or not k.startswith("__")}

        if not locals_vars:
            self.console.print(f"[{self.colors['warning']}]*** No local variables[/{self.colors['warning']}]")
        else:
            table = Table(title="Local Variables", box=box.ROUNDED)
            table.add_column("Name", style=self.colors["variable_name"])
            table.add_column("Type", style=self.colors["variable_type"])
            table.add_column("Value", style=self.colors["variable_value"])

            for name, value in locals_vars.items():
                value_str = repr(value)
                if len(value_str) > 60:
                    value_str = value_str[:57] + "..."

                table.add_row(name, type(value).__name__, value_str)

            self.console.print(table)

    def do_globals(self, arg: str):
        """globals
        Print the global variables of the current frame.
        """
        frame = self._get_current_frame()
        if not frame:
            self.console.print(f"[{self.colors['error']}]No current frame[/{self.colors['error']}]")
            return

        # Show original globals (don't include new variables here)
        if not frame.globals_dict:
            self.console.print(
                f"[{self.colors['warning']}]*** No global variables[/{self.colors['warning']}]"
            )
        else:
            # Filter out built-ins for readability
            filtered_globals = {
                k: v
                for k, v in frame.globals_dict.items()
                if not k.startswith("__") or k in ["__name__", "__file__"]
            }

            table = Table(title="Global Variables", box=box.ROUNDED)
            table.add_column("Name", style=self.colors["variable_name"])
            table.add_column("Type", style=self.colors["variable_type"])
            table.add_column("Value", style=self.colors["variable_value"])

            for name, value in filtered_globals.items():
                value_str = repr(value)
                if len(value_str) > 60:
                    value_str = value_str[:57] + "..."

                table.add_row(name, type(value).__name__, value_str)

            self.console.print(table)

    def do_args(self, arg: str):
        """a(rgs)
        Print the argument list of the current function.
        """
        frame = self._get_current_frame()
        if not frame:
            self.console.print(f"[{self.colors['error']}]No current frame[/{self.colors['error']}]")
            return

        # Try to extract function arguments from locals
        # This is a best-effort approach since we don't store function signature info
        if frame.locals_dict:
            # Common argument names to look for
            potential_args = {}
            for name, value in frame.locals_dict.items():
                if not name.startswith("_") and name not in ["self", "cls"]:
                    potential_args[name] = value

            if potential_args:
                table = Table(title="Function Arguments", box=box.ROUNDED)
                table.add_column("Argument", style=self.colors["variable_name"])
                table.add_column("Type", style=self.colors["variable_type"])
                table.add_column("Value", style=self.colors["variable_value"])

                for arg_name, arg_value in potential_args.items():
                    value_str = repr(arg_value)
                    if len(value_str) > 60:
                        value_str = value_str[:57] + "..."

                    table.add_row(arg_name, type(arg_value).__name__, value_str)

                self.console.print(table)
            else:
                self.console.print(
                    f"[{self.colors['warning']}]*** No arguments found[/{self.colors['warning']}]"
                )
        else:
            self.console.print(
                f"[{self.colors['warning']}]*** No local variables available[/{self.colors['warning']}]"
            )

    def do_a(self, arg: str):
        """Alias for args."""
        self.do_args(arg)

    # Print commands (pdb-style)
    def do_p(self, arg: str):
        """p expression
        Evaluate the expression in the current context and print its value.
        """
        if not arg:
            self.console.print(f"[{self.colors['error']}]*** Missing expression[/{self.colors['error']}]")
            return

        try:
            self._execute_code(arg)
        except Exception as e:
            self.console.print(
                f"[{self.colors['error']}]*** {type(e).__name__}: {e}[/{self.colors['error']}]"
            )

    def do_pp(self, arg: str):
        """pp expression
        Like the p command, except the value of the expression is pretty-printed
        using the pprint module.
        """
        if not arg:
            self.console.print(f"[{self.colors['error']}]*** Missing expression[/{self.colors['error']}]")
            return

        namespace = self._get_namespace()

        try:
            result = eval(arg, namespace)
            # Use rich's pretty printing
            self.console.print(result)
        except Exception as e:
            self.console.print(
                f"[{self.colors['error']}]*** {type(e).__name__}: {e}[/{self.colors['error']}]"
            )

    def do_whatis(self, arg: str):
        """whatis expression
        Print the type of the expression.
        """
        if not arg:
            self.console.print(f"[{self.colors['error']}]*** Missing expression[/{self.colors['error']}]")
            return

        namespace = self._get_namespace()

        try:
            result = eval(arg, namespace)
            self.console.print(
                f"[{self.colors['info']}]{arg}[/{self.colors['info']}] is [{self.colors['highlight']}]{type(result).__name__}[/{self.colors['highlight']}]"
            )
            if hasattr(result, "__doc__") and result.__doc__:
                doc = result.__doc__[:100] + "..." if len(result.__doc__) > 100 else result.__doc__
                self.console.print(f"[dim]Documentation: {doc}[/dim]")
        except Exception as e:
            self.console.print(
                f"[{self.colors['error']}]*** {type(e).__name__}: {e}[/{self.colors['error']}]"
            )

    def do_source(self, arg: str):
        """source [object]
        Try to get source code for the given object.
        """
        if not arg:
            # Show source for current function
            frame = self._get_current_frame()
            if frame and frame.code_context:
                self.console.print(
                    f"[{self.colors['info']}]Source context for {frame.function_name}:[/{self.colors['info']}]"
                )
                self._display_code_context(frame)
            else:
                self.console.print(
                    f"[{self.colors['error']}]*** No source available[/{self.colors['error']}]"
                )
            return

        namespace = self._get_namespace()
        try:
            obj = eval(arg, namespace)
            try:
                source = inspect.getsource(obj)
                syntax = Syntax(source, "python", theme=self.syntax_theme, line_numbers=True)
                self.console.print(
                    Panel(syntax, title=f"Source for {arg}", border_style=self.colors["success"])
                )
            except (OSError, TypeError):
                self.console.print(
                    f"[{self.colors['error']}]*** Could not get source for {arg}[/{self.colors['error']}]"
                )
        except Exception as e:
            self.console.print(
                f"[{self.colors['error']}]*** {type(e).__name__}: {e}[/{self.colors['error']}]"
            )

    def do_display(self, arg: str):
        """display expression
        Add an expression to the display list. The expression will be evaluated
        and displayed each time execution stops.
        """
        if not arg:
            self.console.print(f"[{self.colors['error']}]*** Missing expression[/{self.colors['error']}]")
            return

        if not hasattr(self, "_display_list"):
            self._display_list = []

        self._display_list.append(arg)
        self.console.print(
            f"[{self.colors['success']}]Display expression added: {arg}[/{self.colors['success']}]"
        )

    def do_undisplay(self, arg: str):
        """undisplay [expression]
        Remove expression from display list. Without argument, remove all.
        """
        if not hasattr(self, "_display_list"):
            self._display_list = []

        if not arg:
            self._display_list.clear()
            self.console.print(
                f"[{self.colors['success']}]All display expressions removed[/{self.colors['success']}]"
            )
        else:
            try:
                self._display_list.remove(arg)
                self.console.print(
                    f"[{self.colors['success']}]Display expression removed: {arg}[/{self.colors['success']}]"
                )
            except ValueError:
                self.console.print(
                    f"[{self.colors['error']}]*** Expression not in display list: {arg}[/{self.colors['error']}]"
                )

    def do_longlist(self, arg: str):
        """ll | longlist
        List the whole source code for the current function or frame.
        """
        frame = self._get_current_frame()
        if not frame:
            self.console.print(f"[{self.colors['error']}]No current frame[/{self.colors['error']}]")
            return

        try:
            # Try to get more context from the file
            with open(frame.filename, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Find function definition
            current_line = frame.line_number
            start_line = max(0, current_line - 20)
            end_line = min(len(lines), current_line + 20)

            # Create extended source view
            extended_source = "".join(lines[start_line:end_line])
            syntax = Syntax(
                extended_source,
                "python",
                theme=self.syntax_theme,
                line_numbers=True,
                start_line=start_line + 1,
                highlight_lines={current_line},
            )

            panel = Panel(
                syntax,
                title=f"Extended source for {frame.function_name} in {frame.filename}",
                border_style=self.colors["success"],
            )
            self.console.print(panel)

        except (OSError, IOError):
            self.console.print(
                f"[{self.colors['error']}]*** Could not read source file[/{self.colors['error']}]"
            )
            # Fall back to context we have
            if frame.code_context:
                self._display_code_context(frame)

    def do_ll(self, arg: str):
        """Alias for longlist."""
        self.do_longlist(arg)

    def do_interact(self, arg: str):
        """interact
        Start an interactive Python interpreter with the current frame's namespace.
        """
        frame = self._get_current_frame()
        if not frame:
            self.console.print(f"[{self.colors['error']}]No current frame[/{self.colors['error']}]")
            return

        namespace = self._get_namespace()

        self.console.print(
            f"[{self.colors['info']}]Starting interactive interpreter...[/{self.colors['info']}]"
        )
        self.console.print("[dim]Use 'exit()' or Ctrl+D to return to debugger[/dim]")
        self.console.print(
            f"[{self.colors['success']}]Available variables: {list(namespace.keys())}[/{self.colors['success']}]"
        )

        import code

        try:
            console = code.InteractiveConsole(namespace)
            console.interact(banner="", exitmsg="Returning to debugger...")
        except SystemExit:
            pass

    # Information about the core dump
    def do_info(self, arg: str):
        """info
        Show information about the core dump.
        """
        table = Table(title="Core Dump Information", box=box.ROUNDED)
        table.add_column("Property", style=self.colors["info"])
        table.add_column("Value", style=self.colors["success"])

        table.add_row("Timestamp", self.core_dump.timestamp)

        if self.core_dump.exception_info:
            exc = self.core_dump.exception_info
            table.add_row("Exception", f"{exc[0]}: {exc[1]}")

        table.add_row("Total frames", str(len(self.frames)))
        table.add_row("Current frame", str(self.current_frame_index))
        table.add_row("Python version", self.core_dump.python_version.split()[0])
        table.add_row("Working directory", self.core_dump.working_directory)

        self.console.print(table)

    # Control commands
    def do_quit(self, arg: str):
        """q(uit)
        Quit the debugger.
        """
        self.console.print(f"[{self.colors['info']}]Exiting debugger...[/{self.colors['info']}]")
        return True

    def do_q(self, arg: str):
        """Alias for quit."""
        return self.do_quit(arg)

    def do_exit(self, arg: str):
        """Alias for quit."""
        return self.do_quit(arg)

    def do_EOF(self, arg: str):
        """Handle EOF (Ctrl+D)."""
        print()
        return self.do_quit(arg)

    # Help system
    def do_help(self, arg: str):
        """h(elp) [command]
        Without argument, print the list of available commands.
        With a command as argument, print help about that command.
        """
        if arg:
            super().do_help(arg)
        else:
            help_text = f"""
[{self.colors['info']}]Available commands (similar to pdb):[/{self.colors['info']}]

[{self.colors['highlight']}]Navigation:[/{self.colors['highlight']}]
  u(p) [count]     - Move up in stack trace
  d(own) [count]   - Move down in stack trace
  w(here)/bt       - Show stack trace
  f(rame) [num]    - Select frame by number
  frames           - List all frames with details

[{self.colors['highlight']}]Information:[/{self.colors['highlight']}]
  l(ist)           - Show source code context
  ll/longlist      - Show extended source code
  locals           - Show local variables
  globals          - Show global variables
  a(rgs)           - Show function arguments
  info             - Show core dump information
  source [obj]     - Show source code for object

[{self.colors['highlight']}]Evaluation:[/{self.colors['highlight']}]
  p <expr>         - Print expression value
  pp <expr>        - Pretty-print expression value
  whatis <expr>    - Show expression type
  <statement>      - Execute Python code

[{self.colors['highlight']}]Display:[/{self.colors['highlight']}]
  display <expr>   - Add expression to auto-display list
  undisplay [expr] - Remove from auto-display list

[{self.colors['highlight']}]Advanced:[/{self.colors['highlight']}]
  interact         - Start interactive Python interpreter

[{self.colors['highlight']}]Control:[/{self.colors['highlight']}]
  q(uit)/exit      - Exit debugger
  h(elp) [cmd]     - Show help
"""
            self.console.print(help_text)

    def do_h(self, arg: str):
        """Alias for help."""
        self.do_help(arg)


def debug_core_dump(core_dump: CoreDump):
    """Start interactive debugging session for a core dump."""
    debugger = PostMortemDebugger(core_dump)
    try:
        debugger.cmdloop()
    except KeyboardInterrupt:
        print("\nExiting debugger...")

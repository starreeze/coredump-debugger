# Dpdb - Python Core Dump System

A comprehensive Python "core dump" system that captures execution state (variables, frames, stack traces) for post-mortem debugging, similar to C++ core dumps.

## Features

- **Automatic Core Dumps**: Automatically create core dumps when unhandled exceptions occur
- **Manual Core Dumps**: Create core dumps at any point in your code
- **Post-Mortem Debugger**: Interactive debugger to analyze core dumps with rich terminal UI
- **Adaptive Theme Detection**: Automatically detects light/dark terminal themes for optimal color schemes
- **Complete State Capture**: Captures local variables, global variables, stack frames, and code context
- **Persistent Storage**: Core dumps are saved as pickle files for later analysis
- **pdb-like Interface**: Familiar debugging commands for easy use

## Quick Start

### 0. Installation

Requirements:

- Python 3.8+
- **Rich** - For terminal UI and formatting
- **term_background** (optional) - For improved terminal theme detection


```bash
# Basic installation
pip install coredump-debugger

# With optional dependencies for better theme detection
pip install coredump-debugger[dev]
```

The debugger will work without `term_background` but will have more accurate theme detection when it's available.


### 1. Basic Usage

Just add `dpdb.install_exception_handler("path/to/core_dump.pkl")` to your code, and a core dump will be created and saved automatically when an exception occurs.

```python
import dpdb

# Install automatic core dump generation
dpdb.install_exception_handler("my_app_crash.pkl")

# Your application code here
def my_function():
    x = 42
    y = "hello"
    # This will create a core dump if an exception occurs
    result = 1 / 0  # ZeroDivisionError

my_function()
```

### 2. Manual Core Dumps

```python
import dpdb

def debug_point():
    local_var = "debug info"
    data = [1, 2, 3, 4, 5]
    
    # Create a manual core dump
    dump = dpdb.CoreDumpGenerator.create_from_current_stack()
    dpdb.save_core_dump(dump, "debug_dump.pkl")

debug_point()
```

### 3. Post-Mortem Debugging

Attach Dpdb to a core dump file:

```bash
# Debug a core dump file
python -m dpdb my_app_crash.pkl
```

## Post-Mortem Debugger Commands

The interactive debugger provides the following commands with rich terminal formatting:

### Navigation Commands
- `up [count]` or `u [count]` - Move up the stack (towards caller)
- `down [count]` or `d [count]` - Move down the stack (towards callee)
- `where` or `w` or `bt` - Show stack trace with current frame indicator
- `frame [num]` or `f [num]` - Select frame by number
- `frames` - Show detailed frame information

### Information Commands
- `list` or `l` - Show source code context for current frame
- `longlist` or `ll` - Show extended source code for current frame
- `locals` - Show local variables in current frame
- `globals` - Show global variables in current frame
- `args` or `a` - Show function arguments
- `info` - Show core dump information (timestamp, Python version, etc.)
- `source [object]` - Show source code for object

### Evaluation Commands
- `p <expression>` - Print expression value
- `pp <expression>` - Pretty-print expression value
- `whatis <expression>` - Show expression type
- `<statement>` - Execute Python code directly

### Display Commands
- `display <expression>` - Add expression to auto-display list
- `undisplay [expression]` - Remove from auto-display list

### Advanced Commands
- `interact` - Start interactive Python interpreter

### Control Commands
- `help` or `h` - Show help information
- `quit` or `q` - Exit the debugger

## Theme Detection and Customization

The debugger automatically detects your terminal's theme (light or dark) and adjusts colors accordingly for optimal readability. The detection uses multiple methods:

### Automatic Detection Methods
1. **term_background library** - Most reliable method when available
2. **Rich's color system detection** - Leverages Rich's built-in terminal capabilities
3. **COLORFGBG environment variable** - Standard terminal background indicator
4. **Terminal program identification** - Detects known terminals with light defaults
5. **Various theme environment variables** - Checks for theme-related settings

### Manual Theme Override
You can override the automatic detection by setting an environment variable:

```bash
# Force light theme
export DPDB_THEME=light

# Force dark theme  
export DPDB_THEME=dark

# Let the system auto-detect (default)
unset DPDB_THEME
```

### Color Schemes
- **Dark theme**: Uses bright colors (cyan, yellow, green, magenta) on dark backgrounds
- **Light theme**: Uses darker colors (blue, dark_orange, dark_green, purple) on light backgrounds

## API Reference

### CoreDumpGenerator

- `create_from_exception(exc_type, exc_value, exc_traceback)` - Create core dump from exception
- `create_from_current_stack()` - Create core dump from current call stack

### Functions

- `save_core_dump(core_dump, filename)` - Save core dump to file
- `load_core_dump(filename)` - Load core dump from file
- `install_exception_handler(dump_filename)` - Install automatic exception handler
- `install_global_handler()` - Install global handler for all processes
- `uninstall_global_handler()` - Uninstall global handler and restore normal behavior

### PostMortemDebugger

- `__init__(core_dump)` - Initialize with a core dump
- `run()` - Start interactive debugging session

## Multiprocessing Support

The core dump system provides excellent support for multiprocessing applications through a global handler that automatically applies core dump handling to ALL processes, including those created by frameworks you can't modify:

```python
import dpdb
import multiprocessing as mp

# Install global handler once at the start of your program
dpdb.install_global_handler()

# Now ALL processes will automatically generate core dumps on crashes
# No code modification needed!

def worker_function(data):
    # Your worker code here
    result = process_data(data)
    return result

# Standard multiprocessing - no changes needed
process = mp.Process(target=worker_function, args=(data,))
process.start()
process.join()

# Works with frameworks like accelerate, torch.distributed, etc.
# that control process creation
```

### Framework Compatibility

The global handler works seamlessly with existing frameworks:

```python
import dpdb

# Install once at the start of your program
dpdb.install_global_handler()

# Now accelerate, torch.distributed, etc. will automatically
# generate core dumps for crashed processes
from accelerate import Accelerator
accelerator = Accelerator()
# All processes launched by accelerate will have core dump support
```

## Limitations

- Some objects cannot be serialized (e.g., file handles, network connections)
- Very large objects may consume significant disk space
- Core dumps capture state at the time of creation, not live debugging
- Thread-local storage may not be fully captured in multi-threaded applications

## Security Considerations

Core dumps may contain sensitive information (passwords, tokens, etc.), so
- Store core dump files securely
- Be cautious when sharing core dump files

## License

This code is provided under GPLv3.

from datetime import datetime

from .core_dump import (  # noqa: F401
    CoreDumpGenerator,
    install_global_handler,
    save_core_dump,
    uninstall_global_handler,
)

__version__ = "0.0.3"


def dump(path: str | None = None):
    d = CoreDumpGenerator.create_from_current_stack()
    if path is None:
        path = f"core_dump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl"
    save_core_dump(d, path)

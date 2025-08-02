import os
import warnings
from datetime import datetime

from .core_dump import (  # noqa: F401
    CoreDumpGenerator,
    install_global_handler,
    save_core_dump,
    uninstall_global_handler,
)

__version__ = "0.0.4"


def dump(path: str | None = None, dump_one_process_only: bool = True):
    d = CoreDumpGenerator.create_from_current_stack()
    if path is None:
        path = f"./core_dump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl"
    if dump_one_process_only:
        lock_file = os.path.join(os.path.dirname(path), "dpdb.lock")
        if os.path.exists(lock_file):
            warnings.warn(f"Another process is already dumping core dump. Skip process {os.getpid()}")
            return
        open(lock_file, "w").close()
    save_core_dump(d, path)
    os.remove(lock_file)

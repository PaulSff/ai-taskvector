# wrap_run.py
import logging
import runpy
from multiprocessing import resource_tracker

logging.basicConfig(level=logging.DEBUG)
_orig_register = resource_tracker.register


def _dbg_register(name, rtype):
    logging.debug("resource_tracker.register called: name=%r type=%r", name, rtype)
    return _orig_register(name, rtype)


resource_tracker.register = _dbg_register

runpy.run_path("gui/main.py", run_name="__main__")

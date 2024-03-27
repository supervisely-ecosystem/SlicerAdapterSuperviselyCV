import functools
import logging

# ------------------------------------- Decorators ------------------------------------- #


def log_method_call(func):
    @functools.wraps(func)
    def wrapper(self):
        logging.debug(f"Called method: {func.__name__}")
        return func(self)

    return wrapper


def log_method_call_args(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        logging.debug(f"Called method: {func.__name__}")
        return func(self, *args, **kwargs)

    return wrapper

import functools
import logging

import slicer

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


def import_supervisely(module):
    from moduleLib import SuperviselyDialog

    try:
        import supervisely

        module.ready_to_start = True
    except ModuleNotFoundError:
        SuperviselyDialog(
            """
This module requires Python package <a href='https://pypi.org/project/supervisely/'>supervisely</a> to be installed.
It will be installed automatically now.

Slicer will be restarted after installation.
""",
            type="delay",
            delay=4000,
        )

        from importlib.metadata import version

        import requests
        from packaging.requirements import Requirement
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version

        def get_installed_version(package_name):
            try:
                return version(package_name)
            except:
                return None

        response = requests.get("https://pypi.org/pypi/supervisely/json")
        data = response.json()

        supervisely_deps = [Requirement(dep) for dep in data["info"]["requires_dist"]]

        message = ""
        for dep in supervisely_deps:
            dep_name = dep.name
            dep_spec = str(dep.specifier)
            installed_version = get_installed_version(dep_name)
            if (
                installed_version
                and dep_spec
                and not Version(installed_version) in SpecifierSet(dep_spec)
            ):
                message = (
                    message
                    + f" - [{dep_name}] installed: {installed_version}, required: {dep_spec}\n"
                )

        if message:
            if SuperviselyDialog(
                f"""Conflicting dependencies required by <a href='https://pypi.org/project/supervisely/'>supervisely</a>:\n
{message}
Do you want to try to install <a href='https://pypi.org/project/supervisely/'>supervisely</a> package anyway?\n""",
                "confirm",
            ):
                try:
                    slicer.util.pip_install("supervisely==6.73.58")
                    slicer.util.restart()
                except Exception:
                    SuperviselyDialog(
                        """\nFailed to install <a href='https://pypi.org/project/supervisely/'>supervisely</a> package.
Please install it manually before opening the module or contact us for help.
3D Slicer will be restarted now.
\n<a href='https://supervisely.com/slack/'>Supervisely Slack community</a>""",
                        "error",
                    )
                    slicer.util.restart()
            else:
                SuperviselyDialog(
                    "If you need help with the installation, please contact us.\n\n<a href='https://supervisely.com/slack/'>Supervisely Slack community</a>"
                )
        else:
            slicer.util.pip_install("supervisely==6.73.58")
            slicer.util.restart()

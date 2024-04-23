import functools
import json
import logging
import os
from importlib.metadata import distributions
from pathlib import Path

import slicer

RESTORE_LIB_FILE = os.path.join(Path.home(), "supervisely_slicer_installed_packages.json")

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


def timer_decorator(func):
    import time

    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f"Function {func.__name__} took {end_time - start_time} seconds to run.")
        return result

    return wrapper


def get_installed_libraries_info():
    installed_packages = [(d.metadata["Name"], d.version) for d in distributions()]
    installed_packages_dict = dict(installed_packages)
    return installed_packages_dict


def backup_installed_libraries_info(before_installation, after_installation):
    updated_libraries = {
        lib: {"old_version": before_installation[lib], "new_version": after_installation[lib]}
        for lib in after_installation
        if lib in before_installation and before_installation[lib] != after_installation[lib]
    }

    with open(RESTORE_LIB_FILE, "w") as f:
        json.dump(
            {
                "before_installation": before_installation,
                "after_installation": after_installation,
                "updated_libraries": updated_libraries,
            },
            f,
        )


def restore_libraries(button):
    from moduleLib import SuperviselyDialog

    with open(RESTORE_LIB_FILE, "r") as f:
        backup_info = json.load(f)
    updated_libraries = backup_info.get("updated_libraries", {})
    libraries_list = "\n".join(
        [
            f"- [{lib}] Previous version: {updated_libraries[lib]['old_version']}, Current version: {updated_libraries[lib]['new_version']}"
            for lib in updated_libraries
        ]
    )
    if SuperviselyDialog(
        f"""The following Python libraries will be restored to the previous versions:
{libraries_list}

Because of this, the <a href='https://pypi.org/project/supervisely/'>Supervisely</a> library will be uninstalled to avoid conflicts and the extension will be disabled.
After the process is complete, 3D Slicer will be restarted.
\nDo you want to proceed?""",
        "confirm",
    ):
        slicer.util.pip_uninstall("supervisely")
        slicer_packages = backup_info.get("before_installation", {})
        installed_packages = [(d.metadata["Name"], d.version) for d in distributions()]

        for package_name, package_version in installed_packages:
            if package_name in slicer_packages:
                if slicer_packages[package_name] != package_version:
                    try:
                        slicer.util.pip_install(f"{package_name}=={slicer_packages[package_name]}")
                    except Exception as e:
                        logging.error(
                            f"Failed to restore {package_name} to {slicer_packages[package_name]} version: {e}"
                        )
        os.remove(RESTORE_LIB_FILE)
        slicer.util.restart()
        button.enabled = False


def import_supervisely(module):
    from moduleLib import SuperviselyDialog

    try:
        from supervisely import Api
    except ModuleNotFoundError:

        from importlib.metadata import version

        from packaging.requirements import Requirement
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
        from requests import get

        def get_installed_version(package_name):
            try:
                return version(package_name)
            except Exception:
                return None

        response = get("https://pypi.org/pypi/supervisely/json")
        data = response.json()

        supervisely_deps = [
            Requirement(dep) for dep in data["info"]["requires_dist"] if "extra" not in dep
        ]

        message = ""
        for dep in supervisely_deps:
            dep_name = dep.name
            dep_spec = str(dep.specifier)
            installed_version = get_installed_version(dep_name)
            if (
                installed_version
                and dep_spec
                and not Version(installed_version) in SpecifierSet(dep_spec, prereleases=True)
            ):
                dep_spec = dep_spec.replace("<", "&lt;").replace(">", "&gt;")
                message = (
                    message
                    + f" - [{dep_name}] installed: {installed_version}, required: {dep_spec}\n"
                )

        if message:
            if SuperviselyDialog(
                f"""
This module requires Python package <a href='https://pypi.org/project/supervisely/'>Supervisely</a> to be installed.
But it has conflicting dependencies with the installed packages:
\n{message}
Do you want to to install <a href='https://pypi.org/project/supervisely/'>Supervisely</a> package anyway?\n""",
                "confirm",
            ):
                try:
                    before_installation = get_installed_libraries_info()
                    slicer.util.pip_install("supervisely==6.73.58")
                    after_installation = get_installed_libraries_info()
                    backup_installed_libraries_info(before_installation, after_installation)
                    slicer.util.restart()
                except Exception:
                    SuperviselyDialog(
                        """
Failed to install <a href='https://pypi.org/project/supervisely/'>Supervisely</a> package.
\nPlease install it manually and resolve conflicts with the dependencies before opening the module or contact us for help.
<a href='https://supervisely.com/slack/'>Supervisely Slack community</a>

\n3D Slicer will be restarted now automatically.""",
                        "error",
                    )
                    slicer.util.restart()
            else:
                SuperviselyDialog(
                    """
If you need help with the installation, please contact us.
<a href='https://supervisely.com/slack/'>Supervisely Slack community</a>"""
                )
        else:
            SuperviselyDialog(
                """
This module requires Python package <a href='https://pypi.org/project/supervisely/'>Supervisely</a> to be installed.
It will be installed automatically now.

3D Slicer will be restarted after installation.
""",
                type="info",
            )
            try:
                slicer.util.pip_install("supervisely==6.73.58")
                slicer.util.restart()
            except Exception:
                SuperviselyDialog(
                    """\nFailed to install <a href='https://pypi.org/project/supervisely/'>Supervisely</a> package.
3D Slicer will be restarted now and the installation will be retried.
\nIf the problem persists, please install the package manually or contact us for help.
<a href='https://supervisely.com/slack/'>Supervisely Slack community</a>""",
                    "error",
                )
                slicer.util.restart()
    else:
        module.ready_to_start = True

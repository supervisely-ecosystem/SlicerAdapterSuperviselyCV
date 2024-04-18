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


def check_and_restore_libraries():
    from moduleLib import SuperviselyDialog

    if os.path.exists(RESTORE_LIB_FILE):
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
            f"""Previously installed libraries were updated during the installation of the Supervisely package.
\n{libraries_list}\n
Do you want to restore the previous version of the libraries?
\nSupervisely package will be uninstalled on restore. 3D Slicer will be restarted after the process is finished.""",
            "confirm",
        ):
            slicer.util.pip_uninstall("supervisely")

            slicer_packages = backup_info.get("before_installation", {})
            installed_packages = [(d.metadata["Name"], d.version) for d in distributions()]

            for package_name, package_version in installed_packages:
                if package_name in slicer_packages:
                    if slicer_packages[package_name] != package_version:
                        try:
                            slicer.util.pip_install(
                                f"{package_name}=={slicer_packages[package_name]}"
                            )
                        except Exception as e:
                            logging.error(
                                f"Failed to restore {package_name} to {slicer_packages[package_name]} version: {e}"
                            )
            os.remove(RESTORE_LIB_FILE)
            slicer.util.restart()
        os.remove(RESTORE_LIB_FILE)


def import_supervisely(module):
    from moduleLib import SuperviselyDialog

    try:
        import supervisely
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
            except Exception:
                return None

        response = requests.get("https://pypi.org/pypi/supervisely/json")
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
                f"""Conflicting dependencies required by <a href='https://pypi.org/project/supervisely/'>supervisely</a>:
\n{message}
Do you want to try to install <a href='https://pypi.org/project/supervisely/'>supervisely</a> package anyway?\n""",
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
            try:
                slicer.util.pip_install("supervisely==6.73.58")
            except Exception:
                SuperviselyDialog(
                    """\nFailed to install <a href='https://pypi.org/project/supervisely/'>supervisely</a> package.
3D Slicer will be restarted now and the installation will be retried.
If the problem persists, please install the package manually or contact us for help.
\n<a href='https://supervisely.com/slack/'>Supervisely Slack community</a>""",
                    "error",
                )
                slicer.util.restart()
    else:
        module.ready_to_start = True

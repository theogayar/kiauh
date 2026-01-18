# ======================================================================= #
#  Copyright (C) 2020 - 2026 Dominik Willner <th33xitus@gmail.com>        #
#                                                                         #
#  This file is part of KIAUH - Klipper Installation And Update Helper    #
#  https://github.com/dw-0/kiauh                                          #
#                                                                         #
#  This file may be distributed under the terms of the GNU GPLv3 license  #
# ======================================================================= #
from components.klipper.klipper import Klipper
from core.instance_manager.instance_manager import InstanceManager
from core.logger import DialogType, Logger
from extensions.base_extension import BaseExtension
from extensions.tmc_autotune import (
    KLIPPER_DIR,
    KLIPPER_EXTRAS,
    TMCA_DIR,
    TMCA_REPO,
)
from utils.fs_utils import check_file_exist, create_symlink, run_remove_routines
from utils.git_utils import git_clone_wrapper, git_pull_wrapper
from utils.input_utils import get_confirm
from utils.instance_utils import get_instances


# noinspection PyMethodMayBeStatic
class TmcAutotuneExtension(BaseExtension):
    def install_extension(self, **kwargs) -> None:
        Logger.print_status("Installing Klipper TMC Autotune...")

        # Upstreams checks for python 3 over python 2.
        # We can safely assume python > 3.8 is already installed as kiauh won't run without it.
        # In the same way, git is a requirement for kiauh itself.

        # Upstream also checks for klipper plugins at /klippy/plugins first.
        # However, klipper has been using the extras directory at /klippy/extras
        # for its extension modules since at least 2017.
        klipper_dir_exists = check_file_exist(KLIPPER_DIR) and check_file_exist(
            KLIPPER_EXTRAS
        )

        if not klipper_dir_exists:
            Logger.print_warn("No Klipper (or extras) directory found! Aborting.")
            return

        # TODO: Maybe there is a better way?
        tmca_exists = check_file_exist(TMCA_DIR) and check_file_exist(
            KLIPPER_EXTRAS.joinpath("autotune_tmc.py")
        )

        overwrite = True
        if tmca_exists:
            overwrite = get_confirm(
                question="Extension seems to be installed already. Overwrite?",
                default_choice=True,
                allow_go_back=False,
            )

            if not overwrite:
                Logger.print_warn("Installation aborted due to user request.")
                return

        # TODO: find a way to check if klipper is running in any instance
        instances = get_instances(Klipper)
        if instances:
            Logger.print_dialog(
                DialogType.ATTENTION,
                [
                    "Do NOT continue if there are ongoing prints running!",
                    "All Klipper instances will be restarted during the install process and "
                    "ongoing prints WILL FAIL.",
                ],
            )
            stop_klipper = get_confirm(
                question="Stop Klipper now?",
                default_choice=False,
                allow_go_back=True,
            )

            if stop_klipper:
                InstanceManager.stop_all(instances)

            else:
                Logger.print_warn("Installation aborted due to user request.")
                return

        try:
            # Clone the repo into the target directory
            git_clone_wrapper(TMCA_REPO, TMCA_DIR)

            # Link the extension into klipper's extras folder
            Logger.print_info("Creating symlinks in Klipper extras directory...")
            create_symlink(
                TMCA_DIR.joinpath("autotune_tmc.py"),
                KLIPPER_EXTRAS.joinpath("autotune_tmc.py"),
            )
            create_symlink(
                TMCA_DIR.joinpath("motor_constants.py"),
                KLIPPER_EXTRAS.joinpath("motor_constants.py"),
            )
            create_symlink(
                TMCA_DIR.joinpath("motor_database.cfg"),
                KLIPPER_EXTRAS.joinpath("motor_database.cfg"),
            )

        except Exception as e:
            Logger.print_error(f"Error during Klipper TMC Autotune installation: {e}")

            if instances:
                Logger.print_info("Restarting Klipper...")
                InstanceManager.start_all(instances)
            return

        # Restart klipper after installation
        if instances:
            InstanceManager.start_all(instances)

        Logger.print_ok("Klipper TMC Autotune installed successfully!")

    def update_extension(self, **kwargs) -> None:
        raise NotImplementedError("Update not implemented yet.")
        Logger.print_status("Updating Klipper TMC Autotune...")
        try:
            git_pull_wrapper(TMCA_DIR)

            # TODO: manage backup of config files if changed upstream

        except Exception as e:
            Logger.print_error(f"Error during Klipper TMC Autotune update: {e}")

    def remove_extension(self, **kwargs) -> None:
        raise NotImplementedError("Removal not implemented yet.")
        try:
            Logger.print_status("Removing Klipper TMC Autotune...")

            # remove tmc autotune dir
            run_remove_routines(TMCA_DIR)

            # todo: remove symlinks from klipper config
            # interactively ask if the user want to keep config and remove if required

            # restart klipper service to unload the extension
            # warn the user interactively about ongoing prints

            Logger.print_ok("Klipper TMC Autotune removed successfully.")

        except Exception as e:
            Logger.print_error(f"Error during Klipper TMC Autotune removal: {e}")

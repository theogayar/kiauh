# ======================================================================= #
#  Copyright (C) 2020 - 2026 Dominik Willner <th33xitus@gmail.com>        #
#                                                                         #
#  This file is part of KIAUH - Klipper Installation And Update Helper    #
#  https://github.com/dw-0/kiauh                                          #
#                                                                         #
#  This file may be distributed under the terms of the GNU GPLv3 license  #
# ======================================================================= #
import shutil
from datetime import datetime
from typing import List

from components.klipper.klipper import Klipper
from components.moonraker.moonraker import Moonraker
from core.instance_manager.instance_manager import InstanceManager
from core.logger import DialogType, Logger
from core.services.backup_service import BackupService
from core.submodules.simple_config_parser.src.simple_config_parser.simple_config_parser import (
    SimpleConfigParser,
)
from extensions.base_extension import BaseExtension
from extensions.tmc_autotune import (
    KLIPPER_DIR,
    KLIPPER_EXTRAS,
    TMCA_DIR,
    TMCA_EXEMPLE_CONFIG,
    TMCA_MOONRAKER_UPDATER_NAME,
    TMCA_REPO,
)
from utils.config_utils import add_config_section, remove_config_section
from utils.fs_utils import check_file_exist, create_symlink, run_remove_routines
from utils.git_utils import git_clone_wrapper, git_pull_wrapper
from utils.input_utils import get_confirm
from utils.instance_utils import get_instances
from utils.sys_utils import check_python_version


# noinspection PyMethodMayBeStatic
class TmcAutotuneExtension(BaseExtension):
    def install_extension(self, **kwargs) -> None:
        Logger.print_status("Installing Klipper TMC Autotune...")

        # Check for Python 3.x, aligned with upstream install script
        if not check_python_version(3, 0):
            return

        # Upstream checks for klipper plugins at /klippy/plugins first. Not sure why, but
        # we default to /klippy/extras here. Since Klipper has supposedly been installed via KIAUH,
        # we can assume that the extras directory exists if klipper is installed.
        klipper_dir_exists = check_file_exist(KLIPPER_DIR)
        if not klipper_dir_exists:
            Logger.print_warn(
                "No Klipper directory found! Unable to install extension."
            )
            return

        tmca_exists = (
            check_file_exist(TMCA_DIR)
            and check_file_exist(KLIPPER_EXTRAS.joinpath("autotune_tmc.py"))
            and check_file_exist(KLIPPER_EXTRAS.joinpath("motor_constants.py"))
            and check_file_exist(KLIPPER_EXTRAS.joinpath("motor_database.cfg"))
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

        # TODO: confirm this means that klipper is running (not just that it is installed)
        kl_instances = get_instances(Klipper)
        if kl_instances:
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
                InstanceManager.stop_all(kl_instances)

            else:
                Logger.print_warn("Installation aborted due to user request.")
                return

        try:
            # Clone the repo into the target directory
            git_clone_wrapper(TMCA_REPO, TMCA_DIR, force=True)

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
            Logger.print_ok(
                "Symlinks created successfully for all instances.", end="\n\n"
            )

            # TODO: confirm placement of this interaction
            if get_confirm(
                question="Create an example autotune_tmc.cfg in each printer config directory?",
                default_choice=True,
                allow_go_back=False,
            ):
                self.install_example_cfg(kl_instances)
            else:
                Logger.print_info(
                    "Skipping example config creation as per user request."
                )
                Logger.print_warn(
                    "Make sure to create and include an autotune_tmc.cfg in your printer.cfg in order to use the extension!"
                )

            # TODO: confirm placement of this interaction
            if get_confirm(
                question="Add Klipper TMC Autotune to Moonraker update manager(s)?",
                default_choice=True,
                allow_go_back=False,
            ):
                mr_instances = get_instances(Moonraker)
                self.add_moonraker_update_manager_section(mr_instances)
            else:
                Logger.print_info(
                    "Skipping update section creation as per user request."
                )
                Logger.print_warn(
                    "Make sure to create the corresponding section in your moonraker.conf in order to have it appear in your frontend update manager!"
                )

        except Exception as e:
            Logger.print_error(f"Error during Klipper TMC Autotune installation: {e}")

            if kl_instances:
                Logger.print_info("Restarting Klipper...")
                InstanceManager.start_all(kl_instances)
            return

        # Restart klipper after installation
        if kl_instances:
            InstanceManager.start_all(kl_instances)

        Logger.print_ok("Klipper TMC Autotune installed successfully!")

    def update_extension(self, **kwargs) -> None:
        # TODO: consider warning the user if klipper is running, as update might affect ongoing prints
        
        extension_installed = check_file_exist(TMCA_DIR)
        if not extension_installed:
            Logger.print_info("Extension does not seem to be installed! Skipping ...")
            return

        Logger.print_status("Updating Klipper TMC Autotune...")
        try:
            # TODO: decide on backup strategy here
            # Option 1:
            # settings = KiauhSettings()
            # if settings.kiauh.backup_before_update:
            #     backup_tmca_dir()

            # Option 2:
            if get_confirm(
                question="Backup Klipper TMC Autotune directory before update?",
                default_choice=True,
                allow_go_back=True,
            ):
                Logger.print_status("Backing up Klipper TMC Autotune directory...")
                svc = BackupService()
                svc.backup_directory(
                    source_path=TMCA_DIR,
                    backup_name="klipper_tmc_autotune",
                )
                Logger.print_ok("Backup completed successfully.")

            git_pull_wrapper(TMCA_DIR)

            Logger.print_ok("Klipper TMC Autotune updated successfully.", end="\n\n")

        except Exception as e:
            Logger.print_error(f"Error during Klipper TMC Autotune update:\n{e}")

    def remove_extension(self, **kwargs) -> None:
        extension_installed = check_file_exist(TMCA_DIR)
        if not extension_installed:
            Logger.print_info("Extension does not seem to be installed! Skipping ...")
            return

        kl_instances = get_instances(Klipper)
        if kl_instances:
            Logger.print_dialog(
                DialogType.ATTENTION,
                [
                    "Do NOT continue if there are ongoing prints running!",
                    "All Klipper instances will be restarted during the removal process and "
                    "ongoing prints WILL FAIL.",
                ],
            )
            stop_klipper = get_confirm(
                question="Stop Klipper now and proceed with removal of extension?",
                default_choice=False,
                allow_go_back=True,
            )

            if stop_klipper:
                InstanceManager.stop_all(kl_instances)
            else:
                Logger.print_warn("Removal aborted due to user request.")
                return

        try:
            # remove symlinks and extension directory
            Logger.print_info("Removing Klipper TMC Autotune extension ...")
            run_remove_routines(TMCA_DIR)
            Logger.print_info("Removing symlinks from Klipper extras directory ...")
            run_remove_routines(KLIPPER_EXTRAS.joinpath("autotune_tmc.py"))
            run_remove_routines(KLIPPER_EXTRAS.joinpath("motor_constants.py"))
            run_remove_routines(KLIPPER_EXTRAS.joinpath("motor_database.cfg"))

            # Remove from moonraker update manager if moonraker is installed
            mr_instances: List[Moonraker] = get_instances(Moonraker)
            if mr_instances:
                Logger.print_status("Removing Klipper TMC Autotune from update manager ...")
                BackupService().backup_moonraker_conf()
                remove_config_section("update_manager klipper_tmc_autotune", mr_instances)
                Logger.print_ok(
                    "Klipper TMC Autotune successfully removed from update manager!"
                )

            Logger.print_warn("PLEASE NOTE:")
            Logger.print_warn(
                "1. Remaining tmc_autotune section will cause Klipper to throw an error."
            )
            Logger.print_warn("   Make sure to remove them from the printer.cfg!")
            Logger.print_warn("2. Removal of the tmc_autotune.cfg file is NOT performed automatically.")

        except Exception as e:
            Logger.print_error(f"Unable to remove extension: {e}")

            if kl_instances:
                Logger.print_info("Restarting Klipper...")
                InstanceManager.start_all(kl_instances)
            return

        # Restart klipper after removal
        if kl_instances:
            InstanceManager.start_all(kl_instances)

        Logger.print_ok("Klipper TMC Autotune removed successfully.")

    def install_example_cfg(self, kl_instances: List[Klipper]):
        cfg_dirs = [instance.base.cfg_dir for instance in kl_instances]

        # copy extension to config directories
        for cfg_dir in cfg_dirs:
            Logger.print_status(f"Create autotune_tmc.cfg in '{cfg_dir}' ...")
            if check_file_exist(cfg_dir.joinpath("autotune_tmc.cfg")):
                Logger.print_info("File already exists! Skipping ...")
                continue
            try:
                shutil.copy(TMCA_EXEMPLE_CONFIG, cfg_dir.joinpath("autotune_tmc.cfg"))
                Logger.print_ok("Done!")
            except OSError as e:
                Logger.print_error(f"Unable to create example config: {e}")

        # backup each printer.cfg before modification
        svc = BackupService()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for instance in kl_instances:
            svc.backup_file(
                source_path=instance.cfg_file,
                target_path=f"{instance.data_dir.name}/printer-{timestamp}.cfg",
                target_name=instance.cfg_file.name,
            )

        # add section to printer.cfg if not already defined
        section = "include autotune_tmc.cfg"
        cfg_files = [instance.cfg_file for instance in kl_instances]
        for cfg_file in cfg_files:
            Logger.print_status(f"Include autotune_tmc.cfg in '{cfg_file}' ...")
            scp = SimpleConfigParser()
            scp.read_file(cfg_file)
            if scp.has_section(section):
                Logger.print_info("Section already defined! Skipping ...")
                continue
            scp.add_section(section)
            scp.write_file(cfg_file)
            Logger.print_ok("Done!")

    def add_moonraker_update_manager_section(
        self, mr_instances: List[Moonraker]
    ) -> None:
        # check for moonraker instances and warn if none found
        if not mr_instances:
            Logger.print_dialog(
                DialogType.WARNING,
                [
                    "Moonraker not found! Klipper TMC Autotune update manager support "
                    "for Moonraker will not be added to moonraker.conf.",
                ],
            )
            if not get_confirm(
                "Continue Klipper TMC Autotune installation?",
                default_choice=False,
                allow_go_back=True,
            ):
                Logger.print_info("Installation aborted due to user request.")
                return
            
        # backup any existing moonraker.conf before modification
        BackupService().backup_moonraker_conf()

        # add update_manager section to moonraker.conf
        add_config_section(
            section=TMCA_MOONRAKER_UPDATER_NAME,
            instances=mr_instances,
            options=[
                ("type", "git_repo"),
                ("channel", "dev"),
                ("path", TMCA_DIR.as_posix()),
                ("origin", TMCA_REPO),
                ("managed_services", "klipper"),
                ("primary_branch", "main"),
                # ("install_script", "install.sh"), # Shouldn't be necessary as soft links are already created
            ],
        )

        # restart instances after patching
        InstanceManager.restart_all(mr_instances)

        Logger.print_ok(
            "Klipper TMC Autotune successfully added to each Moonraker update manager!"
        )


# TODO: add a PR for an option to call install_example_cfg without installing the whole app
# TODO: add a PR for a copy helper function in kiauh/utils/fs_utils.py
# TODO: add a PR for an defined test environment / apt check ? 

# TODO: fix the remove function : 
# - currently not removing the section from printer.cfg
# - the whole update manager section is currently removing / adding klipper screen
# - symlinks removal could be improved with a helper function
# - the interactive part is not working either, and it goes straight through



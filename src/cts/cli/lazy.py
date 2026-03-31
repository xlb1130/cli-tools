from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cts.app import CTSApp
else:
    def CTSApp(*args, **kwargs):
        from cts.app import CTSApp as impl

        return impl(*args, **kwargs)


def build_app(*args, **kwargs):
    from cts.app import build_app as impl

    return impl(*args, **kwargs)


def _config_edit_error(message: str):
    from cts.config.editor import ConfigEditError

    return ConfigEditError(message)


def apply_assignment(*args, **kwargs):
    from cts.config.editor import apply_assignment as impl

    return impl(*args, **kwargs)


def apply_update(*args, **kwargs):
    from cts.config.editor import apply_update as impl

    return impl(*args, **kwargs)


def conflict_signatures(*args, **kwargs):
    from cts.config.editor import conflict_signatures as impl

    return impl(*args, **kwargs)


def ensure_list(*args, **kwargs):
    from cts.config.editor import ensure_list as impl

    return impl(*args, **kwargs)


def ensure_mapping(*args, **kwargs):
    from cts.config.editor import ensure_mapping as impl

    return impl(*args, **kwargs)


def parse_assignment(*args, **kwargs):
    from cts.config.editor import parse_assignment as impl

    return impl(*args, **kwargs)


def parse_string_map_item(*args, **kwargs):
    from cts.config.editor import parse_string_map_item as impl

    return impl(*args, **kwargs)


def prepare_edit_session(*args, **kwargs):
    from cts.config.editor import prepare_edit_session as impl

    return impl(*args, **kwargs)


def lint_loaded_config(*args, **kwargs):
    from cts.config.lint import lint_loaded_config as impl

    return impl(*args, **kwargs)


def build_generated_mount(*args, **kwargs):
    from cts.app import build_generated_mount as impl

    return impl(*args, **kwargs)


def build_mount_record(*args, **kwargs):
    from cts.app import build_mount_record as impl

    return impl(*args, **kwargs)


def operation_matches_select(*args, **kwargs):
    from cts.app import operation_matches_select as impl

    return impl(*args, **kwargs)


def synthesize_operation(*args, **kwargs):
    from cts.app import synthesize_operation as impl

    return impl(*args, **kwargs)


def tokenize_identifier(*args, **kwargs):
    from cts.app import tokenize_identifier as impl

    return impl(*args, **kwargs)


def build_click_params(*args, **kwargs):
    from cts.execution.help_compiler import build_click_params as impl

    return impl(*args, **kwargs)


def compile_command_help(*args, **kwargs):
    from cts.execution.help_compiler import compile_command_help as impl

    return impl(*args, **kwargs)


def extract_request_args(*args, **kwargs):
    from cts.execution.help_compiler import extract_request_args as impl

    return impl(*args, **kwargs)


def import_cli_completion(*args, **kwargs):
    from cts.importers import import_cli_completion as impl

    return impl(*args, **kwargs)


def import_cli_help(*args, **kwargs):
    from cts.importers import import_cli_help as impl

    return impl(*args, **kwargs)


def import_cli_manpage(*args, **kwargs):
    from cts.importers import import_cli_manpage as impl

    return impl(*args, **kwargs)


def import_cli_schema(*args, **kwargs):
    from cts.importers import import_cli_schema as impl

    return impl(*args, **kwargs)


def inspect_cli_help(*args, **kwargs):
    from cts.importers import inspect_cli_help as impl

    return impl(*args, **kwargs)


def summarize_help_text(*args, **kwargs):
    from cts.importers import summarize_help_text as impl

    return impl(*args, **kwargs)


def merge_operation_into_manifest(*args, **kwargs):
    from cts.importers import merge_operation_into_manifest as impl

    return impl(*args, **kwargs)


def write_manifest_operations(*args, **kwargs):
    from cts.importers import write_manifest_operations as impl

    return impl(*args, **kwargs)


def build_error_envelope(*args, **kwargs):
    from cts.execution.runtime import build_error_envelope as impl

    return impl(*args, **kwargs)


def explain_mount(*args, **kwargs):
    from cts.execution.runtime import explain_mount as impl

    return impl(*args, **kwargs)


def invoke_mount(*args, **kwargs):
    from cts.execution.runtime import invoke_mount as impl

    return impl(*args, **kwargs)


def render_payload(*args, **kwargs):
    from cts.execution.runtime import render_payload as impl

    return impl(*args, **kwargs)


def build_app_summary(*args, **kwargs):
    from cts.presentation import build_app_summary as impl

    return impl(*args, **kwargs)


def build_auth_inventory(*args, **kwargs):
    from cts.presentation import build_auth_inventory as impl

    return impl(*args, **kwargs)


def build_auth_profile(*args, **kwargs):
    from cts.presentation import build_auth_profile as impl

    return impl(*args, **kwargs)


def build_mount_details(*args, **kwargs):
    from cts.presentation import build_mount_details as impl

    return impl(*args, **kwargs)


def build_mount_help(*args, **kwargs):
    from cts.presentation import build_mount_help as impl

    return impl(*args, **kwargs)


def build_reliability_status(*args, **kwargs):
    from cts.presentation import build_reliability_status as impl

    return impl(*args, **kwargs)


def build_secret_detail(*args, **kwargs):
    from cts.presentation import build_secret_detail as impl

    return impl(*args, **kwargs)


def build_secret_inventory(*args, **kwargs):
    from cts.presentation import build_secret_inventory as impl

    return impl(*args, **kwargs)


def build_source_check_result(*args, **kwargs):
    from cts.presentation import build_source_check_result as impl

    return impl(*args, **kwargs)


def build_source_details(*args, **kwargs):
    from cts.presentation import build_source_details as impl

    return impl(*args, **kwargs)


def build_source_summary(*args, **kwargs):
    from cts.presentation import build_source_summary as impl

    return impl(*args, **kwargs)


def load_manifest(*args, **kwargs):
    from cts.providers.cli import load_manifest as impl

    return impl(*args, **kwargs)


def manifest_operations_from_data(*args, **kwargs):
    from cts.providers.cli import manifest_operations_from_data as impl

    return impl(*args, **kwargs)


def operation_from_config(*args, **kwargs):
    from cts.providers.cli import operation_from_config as impl

    return impl(*args, **kwargs)


def create_http_server(*args, **kwargs):
    from cts.surfaces.http import create_http_server as impl

    return impl(*args, **kwargs)


def default_ui_dist_dir(*args, **kwargs):
    from cts.surfaces.http import default_ui_dist_dir as impl

    return impl(*args, **kwargs)

from __future__ import annotations

from typing import Any, Dict, List

from cts.imports.models import ImportArgumentDescriptor, ImportWizardField
from cts.operation_select import normalize_operation_select


def build_operation_select(values: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_operation_select(
        {
            "include": values.get("include"),
            "exclude": values.get("exclude"),
            "tags": values.get("tags"),
        }
    )


def import_operation_select_arguments() -> List[ImportArgumentDescriptor]:
    return [
        ImportArgumentDescriptor(
            name="include",
            kind="option",
            value_type="string",
            repeated=True,
            flags=["--include", "include"],
            help="Only import operations matching these glob patterns.",
        ),
        ImportArgumentDescriptor(
            name="exclude",
            kind="option",
            value_type="string",
            repeated=True,
            flags=["--exclude", "exclude"],
            help="Skip operations matching these glob patterns.",
        ),
        ImportArgumentDescriptor(
            name="tags",
            kind="option",
            value_type="string",
            repeated=True,
            flags=["--tag", "tags"],
            help="Only import operations carrying these tags.",
        ),
    ]


def import_operation_select_wizard_fields() -> List[ImportWizardField]:
    return [
        ImportWizardField(name="include", label="Include patterns", multiple=True, help="Glob patterns to keep."),
        ImportWizardField(name="exclude", label="Exclude patterns", multiple=True, help="Glob patterns to skip."),
        ImportWizardField(name="tags", label="Tags", multiple=True, help="Only import operations with these tags."),
    ]

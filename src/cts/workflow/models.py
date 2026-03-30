"""Workflow configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class StepConditionType(str, Enum):
    """Types of step conditions."""
    SUCCESS = "success"
    FAILURE = "failure"
    ALWAYS = "always"
    CONDITION = "condition"


@dataclass
class StepCondition:
    """Condition for step execution."""
    type: StepConditionType = StepConditionType.SUCCESS
    expression: Optional[str] = None  # Jinja2-like expression for CONDITION type


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    id: str
    mount_id: Optional[str] = None  # Reference to existing mount
    operation_ref: Optional[str] = None  # Source.operation_id reference
    args: Dict[str, Any] = field(default_factory=dict)
    input_from: Optional[str] = None  # Reference to previous step output: step_id.field
    run_when: StepCondition = field(default_factory=StepCondition)
    retry_on_failure: bool = False
    timeout_seconds: Optional[int] = None
    description: Optional[str] = None
    # For inline operation definition
    inline_operation: Optional[Dict[str, Any]] = None


@dataclass
class WorkflowStepResult:
    """Result of a workflow step execution."""
    step_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None
    duration_ms: Optional[int] = None


@dataclass
class WorkflowResult:
    """Result of a workflow execution."""
    workflow_id: str
    success: bool
    steps: List[WorkflowStepResult] = field(default_factory=list)
    output: Any = None
    error: Optional[str] = None
    run_id: Optional[str] = None
    trace_id: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class WorkflowConfig:
    """Configuration for a workflow/composite operation."""
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    steps: List[WorkflowStep] = field(default_factory=list)
    
    # Mount configuration for the workflow as a callable mount
    mount_as: Optional[str] = None  # mount_id to register this workflow
    command_path: List[str] = field(default_factory=list)
    stable_name: Optional[str] = None
    
    # Input schema for the workflow
    input_schema: Dict[str, Any] = field(default_factory=dict)
    
    # Output configuration
    output_from: Optional[str] = None  # Which step's output to use as workflow output
    
    # Execution options
    parallel_groups: List[List[str]] = field(default_factory=list)  # Groups of step IDs to run in parallel
    fail_fast: bool = True  # Stop on first failure
    continue_on_error: List[str] = field(default_factory=list)  # Step IDs to continue past
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    risk: str = "read"  # read, write, destructive - defaults to safest
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowConfig:
        """Create WorkflowConfig from dictionary."""
        steps = []
        for step_data in data.get("steps", []):
            run_when = StepCondition()
            if "run_when" in step_data:
                rw = step_data["run_when"]
                if isinstance(rw, str):
                    run_when = StepCondition(type=StepConditionType(rw))
                elif isinstance(rw, dict):
                    run_when = StepCondition(
                        type=StepConditionType(rw.get("type", "success")),
                        expression=rw.get("expression"),
                    )
            
            steps.append(WorkflowStep(
                id=step_data["id"],
                mount_id=step_data.get("mount_id"),
                operation_ref=step_data.get("operation_ref"),
                args=step_data.get("args", {}),
                input_from=step_data.get("input_from"),
                run_when=run_when,
                retry_on_failure=step_data.get("retry_on_failure", False),
                timeout_seconds=step_data.get("timeout_seconds"),
                description=step_data.get("description"),
                inline_operation=step_data.get("operation"),
            ))
        
        return cls(
            id=data["id"],
            name=data.get("name"),
            description=data.get("description"),
            steps=steps,
            mount_as=data.get("mount_as"),
            command_path=data.get("command_path", []),
            stable_name=data.get("stable_name"),
            input_schema=data.get("input_schema", {}),
            output_from=data.get("output_from"),
            parallel_groups=data.get("parallel_groups", []),
            fail_fast=data.get("fail_fast", True),
            continue_on_error=data.get("continue_on_error", []),
            tags=data.get("tags", []),
            risk=data.get("risk", "read"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [
                {
                    "id": step.id,
                    "mount_id": step.mount_id,
                    "operation_ref": step.operation_ref,
                    "args": step.args,
                    "input_from": step.input_from,
                    "run_when": {"type": step.run_when.type.value, "expression": step.run_when.expression},
                    "retry_on_failure": step.retry_on_failure,
                    "timeout_seconds": step.timeout_seconds,
                    "description": step.description,
                }
                for step in self.steps
            ],
            "mount_as": self.mount_as,
            "command_path": self.command_path,
            "stable_name": self.stable_name,
            "input_schema": self.input_schema,
            "output_from": self.output_from,
            "parallel_groups": self.parallel_groups,
            "fail_fast": self.fail_fast,
            "continue_on_error": self.continue_on_error,
            "tags": self.tags,
            "risk": self.risk,
        }

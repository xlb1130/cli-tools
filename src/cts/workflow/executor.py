"""Workflow executor for running multi-step operations."""

from __future__ import annotations

import re
import time
import uuid
from concurrent.futures import TimeoutError as FutureTimeoutError
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set

from cts.app import CTSApp
from cts.execution.logging import emit_app_event, utc_now_iso
from cts.execution.runtime import invoke_mount
from cts.reliability import RetryExecutor, RetryPolicy, RiskLevel
from cts.workflow.models import (
    StepConditionType,
    WorkflowConfig,
    WorkflowResult,
    WorkflowStep,
    WorkflowStepResult,
)


class WorkflowExecutor:
    """Executes workflows with step orchestration."""
    
    def __init__(self, app: CTSApp):
        self.app = app
        self._step_outputs: Dict[str, Any] = {}
    
    def execute(
        self,
        workflow: WorkflowConfig,
        args: Dict[str, Any],
        *,
        run_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> WorkflowResult:
        """Execute a workflow with the given arguments."""
        run_id = run_id or str(uuid.uuid4())
        trace_id = trace_id or str(uuid.uuid4())
        started_at = utc_now_iso()
        
        emit_app_event(
            self.app,
            event="workflow_start",
            data={
                "workflow_id": workflow.id,
                "run_id": run_id,
                "trace_id": trace_id,
                "step_count": len(workflow.steps),
                "args": args,
            },
        )
        
        self._step_outputs = {"input": args}
        step_by_id = {step.id: step for step in workflow.steps}
        step_results: List[WorkflowStepResult] = []
        failed_step_ids: Set[str] = set()
        success = True
        error: Optional[str] = None

        for batch in self._resolve_execution_batches(workflow):
            executable_steps: List[WorkflowStep] = []

            for step_id in batch:
                step = step_by_id.get(step_id)
                if not step:
                    continue

                should_run, skip_reason = self._should_run_step(
                    step, step_results, failed_step_ids, workflow.fail_fast
                )

                if not should_run:
                    step_results.append(
                        WorkflowStepResult(
                            step_id=step_id,
                            success=True,
                            skipped=True,
                            skip_reason=skip_reason,
                        )
                    )
                    continue

                executable_steps.append(step)

            if not executable_steps:
                continue

            batch_results: Dict[str, WorkflowStepResult] = {}
            if len(executable_steps) == 1:
                step = executable_steps[0]
                batch_results[step.id] = self._execute_step(
                    step,
                    args,
                    dry_run=dry_run,
                    run_id=run_id,
                    trace_id=trace_id,
                )
            else:
                with ThreadPoolExecutor(max_workers=len(executable_steps)) as executor:
                    future_map = {
                        step.id: executor.submit(
                            self._execute_step,
                            step,
                            args,
                            dry_run=dry_run,
                            run_id=run_id,
                            trace_id=trace_id,
                        )
                        for step in executable_steps
                    }
                    for step in executable_steps:
                        batch_results[step.id] = future_map[step.id].result()

            for step in executable_steps:
                step_result = batch_results[step.id]
                step_results.append(step_result)

                if step_result.success:
                    self._step_outputs[step.id] = step_result.output
                    continue

                failed_step_ids.add(step.id)
                if workflow.fail_fast and step.id not in workflow.continue_on_error:
                    success = False
                    error = f"Step '{step.id}' failed: {step_result.error}"

            if not success:
                break
        
        # Determine workflow output
        output = None
        if workflow.output_from:
            output = self._step_outputs.get(workflow.output_from)
        elif step_results and step_results[-1].success:
            output = step_results[-1].output
        
        completed_at = utc_now_iso()
        
        result = WorkflowResult(
            workflow_id=workflow.id,
            success=success,
            steps=step_results,
            output=output,
            error=error,
            run_id=run_id,
            trace_id=trace_id,
            started_at=started_at,
            completed_at=completed_at,
        )
        
        emit_app_event(
            self.app,
            event="workflow_complete" if success else "workflow_error",
            data={
                "workflow_id": workflow.id,
                "run_id": run_id,
                "trace_id": trace_id,
                "success": success,
                "step_count": len(step_results),
                "failed_count": len(failed_step_ids),
            },
        )
        
        return result
    
    def _resolve_step_order(self, workflow: WorkflowConfig) -> List[str]:
        """Resolve the order of step execution based on dependencies."""
        steps = list(workflow.steps)
        step_ids = [step.id for step in steps]
        step_id_set = set(step_ids)
        order_index = {step.id: index for index, step in enumerate(steps)}
        dependencies = self._build_step_dependencies(workflow, step_id_set)

        in_degree = {step_id: 0 for step_id in step_ids}
        dependents: Dict[str, Set[str]] = {step_id: set() for step_id in step_ids}
        for step_id, deps in dependencies.items():
            in_degree[step_id] = len(deps)
            for dep in deps:
                dependents.setdefault(dep, set()).add(step_id)

        ready = sorted([step_id for step_id in step_ids if in_degree[step_id] == 0], key=order_index.get)
        resolved: List[str] = []

        while ready:
            current = ready.pop(0)
            resolved.append(current)
            for dependent in sorted(dependents.get(current, ()), key=order_index.get):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    ready.append(dependent)
                    ready.sort(key=order_index.get)

        if len(resolved) != len(step_ids):
            unresolved = [step_id for step_id in step_ids if step_id not in resolved]
            raise ValueError(f"Workflow contains cyclic or unresolved dependencies: {', '.join(unresolved)}")

        return resolved

    def _resolve_execution_batches(self, workflow: WorkflowConfig) -> List[List[str]]:
        """Resolve execution batches, grouping only explicitly parallel steps."""
        order = self._resolve_step_order(workflow)
        dependencies = self._build_step_dependencies(workflow, set(order))
        parallel_group_map = self._build_parallel_group_map(workflow, dependencies)
        batches: List[List[str]] = []
        completed: Set[str] = set()
        remaining = set(order)
        order_index = {step_id: index for index, step_id in enumerate(order)}

        while remaining:
            ready = [
                step_id
                for step_id in order
                if step_id in remaining and dependencies.get(step_id, set()).issubset(completed)
            ]
            if not ready:
                unresolved = sorted(remaining, key=order_index.get)
                raise ValueError(f"Workflow cannot make progress; unresolved steps: {', '.join(unresolved)}")

            head = ready[0]
            parallel_group = parallel_group_map.get(head)
            if parallel_group:
                batch = [step_id for step_id in order if step_id in remaining and step_id in parallel_group]
            else:
                batch = [head]

            batches.append(batch)
            for step_id in batch:
                remaining.remove(step_id)
                completed.add(step_id)

        return batches
    
    def _should_run_step(
        self,
        step: WorkflowStep,
        previous_results: List[WorkflowStepResult],
        failed_step_ids: Set[str],
        fail_fast: bool,
    ) -> tuple[bool, Optional[str]]:
        """Determine if a step should run based on conditions."""
        condition = step.run_when
        
        if condition.type == StepConditionType.ALWAYS:
            return True, None
        
        if condition.type == StepConditionType.FAILURE:
            # Run only if there were failures
            if failed_step_ids:
                return True, None
            return False, "No previous failures to handle"
        
        if condition.type == StepConditionType.CONDITION:
            # Evaluate expression
            if condition.expression:
                try:
                    result = self._evaluate_condition(condition.expression)
                    if result:
                        return True, None
                    return False, f"Condition not met: {condition.expression}"
                except Exception as e:
                    return False, f"Condition evaluation error: {e}"
            return True, None
        
        # Default: SUCCESS condition
        if failed_step_ids:
            return False, f"Previous steps failed: {failed_step_ids}"
        return True, None
    
    def _evaluate_condition(self, expression: str) -> bool:
        """Evaluate a condition expression."""
        # Simple expression evaluation
        # Supports: step_id.field == value, step_id.field != value
        # Also supports Jinja2-like {{ step_id.field }} references
        
        # Resolve variable references
        resolved = self._resolve_expression(expression)
        
        # Evaluate comparison
        if "==" in resolved:
            left, right = resolved.split("==", 1)
            return left.strip() == right.strip()
        if "!=" in resolved:
            left, right = resolved.split("!=", 1)
            return left.strip() != right.strip()
        
        # Treat as boolean
        return bool(resolved.strip())
    
    def _resolve_expression(self, expression: str) -> str:
        """Resolve variable references in an expression."""
        # Replace {{ step_id.field }} with actual values
        pattern = r"\{\{\s*(\w+)(?:\.([\w\.]+))?\s*\}\}"
        
        def replacer(match):
            step_id = match.group(1)
            path = match.group(2)
            if step_id not in self._step_outputs:
                return ""
            value = self._step_outputs[step_id]
            if not path:
                return str(value)
            resolved = self._resolve_nested_value(value, path)
            return "" if resolved is None else str(resolved)
        
        return re.sub(pattern, replacer, expression)
    
    def _execute_step(
        self,
        step: WorkflowStep,
        workflow_args: Dict[str, Any],
        *,
        dry_run: bool,
        run_id: str,
        trace_id: str,
    ) -> WorkflowStepResult:
        """Execute a single workflow step."""
        start_time = time.time()

        emit_app_event(
            self.app,
            event="workflow_step_start",
            data={
                "step_id": step.id,
                "mount_id": step.mount_id,
                "operation_ref": step.operation_ref,
                "timeout_seconds": step.timeout_seconds,
                "retry_on_failure": step.retry_on_failure,
            },
        )

        try:
            step_args = self._build_step_args(step, workflow_args)
            if dry_run:
                return WorkflowStepResult(
                    step_id=step.id,
                    success=True,
                    output={"dry_run": True, "args": step_args},
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            result = self._execute_step_with_reliability(
                step,
                step_args,
                run_id=run_id,
                trace_id=trace_id,
            )

            duration_ms = int((time.time() - start_time) * 1000)
            emit_app_event(
                self.app,
                event="workflow_step_complete",
                data={"step_id": step.id, "success": result.get("ok", False)},
            )

            return WorkflowStepResult(
                step_id=step.id,
                success=result.get("ok", False),
                output=result.get("data") or result,
                error=result.get("error", {}).get("message") if not result.get("ok") else None,
                duration_ms=duration_ms,
            )
        
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            emit_app_event(
                self.app,
                event="workflow_step_error",
                data={"step_id": step.id, "error": str(e)},
            )
            return WorkflowStepResult(
                step_id=step.id,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )

    def _execute_step_with_reliability(
        self,
        step: WorkflowStep,
        step_args: Dict[str, Any],
        *,
        run_id: str,
        trace_id: str,
    ) -> Dict[str, Any]:
        def do_execute() -> Dict[str, Any]:
            return self._execute_step_once(
                step,
                step_args,
                run_id=run_id,
                trace_id=trace_id,
            )

        if not step.retry_on_failure:
            return self._run_step_with_timeout(step, do_execute)

        policy = self._workflow_retry_policy()
        policy.max_attempts = max(policy.max_attempts, 2)
        executor = RetryExecutor(
            policy=policy,
            risk=self._resolve_step_risk(step),
            is_idempotent=self._is_step_idempotent(step),
        )

        def on_retry(retry_ctx) -> None:
            emit_app_event(
                self.app,
                event="workflow_step_retry_scheduled",
                data={
                    "step_id": step.id,
                    "attempt": retry_ctx.attempt,
                    "delay_ms": retry_ctx.last_delay_ms,
                    "next_attempt": retry_ctx.attempt + 1,
                },
            )

        retry_result = executor.execute_sync(
            lambda: self._run_step_with_timeout(step, do_execute),
            on_retry=on_retry,
        )
        if retry_result.success:
            return retry_result.result
        raise retry_result.error or RuntimeError(f"Step '{step.id}' failed")

    def _run_step_with_timeout(
        self,
        step: WorkflowStep,
        func,
    ) -> Dict[str, Any]:
        if not step.timeout_seconds or step.timeout_seconds <= 0:
            return func()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func)
            try:
                return future.result(timeout=step.timeout_seconds)
            except FutureTimeoutError as exc:
                emit_app_event(
                    self.app,
                    event="workflow_step_timeout",
                    data={"step_id": step.id, "timeout_seconds": step.timeout_seconds},
                )
                raise TimeoutError(
                    f"Step '{step.id}' timed out after {step.timeout_seconds} seconds"
                ) from exc

    def _execute_step_once(
        self,
        step: WorkflowStep,
        step_args: Dict[str, Any],
        *,
        run_id: str,
        trace_id: str,
    ) -> Dict[str, Any]:
        if step.mount_id:
            return self._execute_via_mount(
                step.mount_id,
                step_args,
                run_id=run_id,
                trace_id=trace_id,
            )
        if step.operation_ref:
            return self._execute_via_operation_ref(
                step.operation_ref,
                step_args,
                run_id=run_id,
                trace_id=trace_id,
            )
        if step.inline_operation:
            return self._execute_inline_operation(
                step.inline_operation,
                step_args,
                run_id=run_id,
                trace_id=trace_id,
            )
        raise ValueError(f"Step '{step.id}' has no mount_id, operation_ref, or inline operation")

    def _workflow_retry_policy(self) -> RetryPolicy:
        if hasattr(self.app, "config") and self.app.config:
            defaults = self.app.config.get_reliability_defaults()
            return defaults.retry.model_copy(deep=True)
        return RetryPolicy()

    def _resolve_step_risk(self, step: WorkflowStep) -> RiskLevel:
        mount = None
        if step.mount_id and hasattr(self.app, "catalog"):
            mount = self.app.catalog.find_by_id(step.mount_id)
        elif step.operation_ref and "." in step.operation_ref and hasattr(self.app, "catalog"):
            source_name, operation_id = step.operation_ref.split(".", 1)
            mount = self.app.catalog.find_by_source_and_operation(source_name, operation_id)

        risk = getattr(getattr(mount, "operation", None), "risk", "read")
        try:
            return RiskLevel(str(risk))
        except ValueError:
            return RiskLevel.READ

    def _is_step_idempotent(self, step: WorkflowStep) -> bool:
        mount = None
        if step.mount_id and hasattr(self.app, "catalog"):
            mount = self.app.catalog.find_by_id(step.mount_id)
        elif step.operation_ref and "." in step.operation_ref and hasattr(self.app, "catalog"):
            source_name, operation_id = step.operation_ref.split(".", 1)
            mount = self.app.catalog.find_by_source_and_operation(source_name, operation_id)

        reliability = getattr(getattr(mount, "mount_config", None), "reliability", None) or {}
        idempotency = reliability.get("idempotency", {}) if isinstance(reliability, dict) else {}
        return bool(idempotency.get("required"))
    
    def _build_step_args(self, step: WorkflowStep, workflow_args: Dict[str, Any]) -> Dict[str, Any]:
        """Build arguments for a step, resolving references."""
        args = dict(step.args)
        
        # Merge with workflow input
        for key, value in workflow_args.items():
            if key not in args:
                args[key] = value
        
        # Resolve input_from references
        if step.input_from:
            ref_value = self._resolve_input_ref(step.input_from)
            if ref_value is not None:
                # If input_from references a whole step output, use it as base
                if "." not in step.input_from:
                    if isinstance(ref_value, dict):
                        args.update(ref_value)
                else:
                    # Reference to specific field
                    field_name = step.input_from.split(".")[-1]
                    args[field_name] = ref_value
        
        return args
    
    def _resolve_input_ref(self, ref: str) -> Any:
        """Resolve an input reference like 'step_id.field'."""
        parts = ref.split(".", 1)
        step_id = parts[0]
        
        if step_id not in self._step_outputs:
            return None
        
        obj = self._step_outputs[step_id]
        
        if len(parts) == 1:
            return obj
        
        return self._resolve_nested_value(obj, parts[1])

    def _resolve_nested_value(self, value: Any, path: str) -> Any:
        current = value
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
                continue
            return None
        return current

    def _build_step_dependencies(self, workflow: WorkflowConfig, step_ids: Set[str]) -> Dict[str, Set[str]]:
        dependencies: Dict[str, Set[str]] = {step.id: set() for step in workflow.steps}

        for step in workflow.steps:
            if step.input_from:
                ref_step = step.input_from.split(".", 1)[0]
                if ref_step != "input":
                    if ref_step not in step_ids:
                        raise ValueError(f"Step '{step.id}' references unknown input source '{ref_step}'")
                    dependencies[step.id].add(ref_step)

            expression = step.run_when.expression
            if expression:
                for ref_step in self._extract_expression_step_ids(expression):
                    if ref_step == "input":
                        continue
                    if ref_step not in step_ids:
                        raise ValueError(f"Step '{step.id}' condition references unknown step '{ref_step}'")
                    dependencies[step.id].add(ref_step)

        return dependencies

    def _build_parallel_group_map(
        self,
        workflow: WorkflowConfig,
        dependencies: Dict[str, Set[str]],
    ) -> Dict[str, Set[str]]:
        step_ids = {step.id for step in workflow.steps}
        parallel_group_map: Dict[str, Set[str]] = {}

        for group in workflow.parallel_groups:
            members = {step_id for step_id in group if step_id}
            if len(members) < 2:
                continue

            unknown = sorted(members - step_ids)
            if unknown:
                raise ValueError(f"Parallel group references unknown steps: {', '.join(unknown)}")

            for member in members:
                if member in parallel_group_map:
                    raise ValueError(f"Step '{member}' is declared in multiple parallel groups")

            baseline = None
            for member in sorted(members):
                member_deps = dependencies.get(member, set()) - members
                if dependencies.get(member, set()) & members:
                    raise ValueError(f"Parallel step '{member}' cannot depend on another step in the same group")
                if baseline is None:
                    baseline = member_deps
                elif member_deps != baseline:
                    raise ValueError(
                        "Parallel group members must share the same upstream dependencies: "
                        + ", ".join(sorted(members))
                    )

            for member in members:
                parallel_group_map[member] = set(members)

        return parallel_group_map

    def _extract_expression_step_ids(self, expression: str) -> Set[str]:
        pattern = r"\{\{\s*(\w+)(?:\.[\w\.]+)?\s*\}\}"
        return {match.group(1) for match in re.finditer(pattern, expression)}
    
    def _execute_via_mount(
        self,
        mount_id: str,
        args: Dict[str, Any],
        *,
        run_id: str,
        trace_id: str,
    ) -> Dict[str, Any]:
        """Execute a step via mount reference."""
        mount = self.app.catalog.find_by_id(mount_id)
        if not mount:
            raise ValueError(f"Mount not found: {mount_id}")
        
        runtime = {
            "run_id": run_id,
            "trace_id": trace_id,
            "dry_run": False,
        }
        
        return invoke_mount(self.app, mount, args, runtime)
    
    def _execute_via_operation_ref(
        self,
        operation_ref: str,
        args: Dict[str, Any],
        *,
        run_id: str,
        trace_id: str,
    ) -> Dict[str, Any]:
        """Execute a step via source.operation reference."""
        # Parse source.operation_id format
        if "." not in operation_ref:
            raise ValueError(f"Invalid operation_ref format: {operation_ref}")
        
        source_name, operation_id = operation_ref.split(".", 1)
        
        # Find mount for this operation
        mount = self.app.catalog.find_by_source_and_operation(source_name, operation_id)
        if not mount:
            raise ValueError(f"No mount found for operation: {operation_ref}")
        
        runtime = {
            "run_id": run_id,
            "trace_id": trace_id,
            "dry_run": False,
        }
        
        return invoke_mount(self.app, mount, args, runtime)
    
    def _execute_inline_operation(
        self,
        operation: Dict[str, Any],
        args: Dict[str, Any],
        *,
        run_id: str,
        trace_id: str,
    ) -> Dict[str, Any]:
        """Execute an inline operation definition."""
        # For inline operations, we create a temporary mount
        # This is useful for simple inline commands
        source_name = operation.get("source")
        if not source_name:
            raise ValueError("Inline operation must specify source")
        
        operation_id = operation.get("operation_id")
        if not operation_id:
            raise ValueError("Inline operation must specify operation_id")
        
        # Find mount or create temporary reference
        mount = self.app.catalog.find_by_source_and_operation(source_name, operation_id)
        if not mount:
            raise ValueError(f"No mount found for inline operation: {source_name}.{operation_id}")
        
        # Merge inline args with step args
        merged_args = dict(operation.get("args", {}))
        merged_args.update(args)
        
        runtime = {
            "run_id": run_id,
            "trace_id": trace_id,
            "dry_run": False,
        }
        
        return invoke_mount(self.app, mount, merged_args, runtime)

"""Serializable summary of one augmentation run."""

from __future__ import annotations

from dataclasses import dataclass, field

from albumentationsx_plugin.core import (
    RUN_EXECUTION_STATUS_COMPLETED,
    RUN_EXECUTION_STATUS_DRY_RUN,
    JSONDict,
)
from albumentationsx_plugin.core.contracts.runs import terminal_execution_status
from albumentationsx_plugin.hosts.fiftyone.output_metadata import (
    metadata_policy_output_fields,
)


@dataclass(frozen=True, slots=True)
class FixedAugmentationExecutionResult:
    """User-facing summary of one fixed-transform augmentation run."""

    run_key: str
    processed_count: int
    created_count: int
    skipped_count: int
    error_count: int
    dry_run: bool
    output_tag: str
    output_dir: str
    execution_status: str = RUN_EXECUTION_STATUS_COMPLETED
    source_scope: str = ""
    manifest_path: str = ""
    fiftyone_run_key: str = ""
    errors: tuple[JSONDict, ...] = ()
    metadata_policy: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.execution_status == RUN_EXECUTION_STATUS_COMPLETED:
            object.__setattr__(
                self,
                "execution_status",
                terminal_execution_status(
                    succeeded=self.created_count,
                    errors=self.error_count,
                    success_status=RUN_EXECUTION_STATUS_DRY_RUN if self.dry_run else RUN_EXECUTION_STATUS_COMPLETED,
                ),
            )

    def to_dict(self) -> JSONDict:
        """Serialize the summary for FiftyOne operator output."""

        return {
            "run_key": self.run_key,
            "source_scope": self.source_scope,
            "processed_count": self.processed_count,
            "created_count": self.created_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "dry_run": self.dry_run,
            "execution_status": self.execution_status,
            "output_tag": self.output_tag,
            "output_dir": self.output_dir,
            "manifest_path": self.manifest_path,
            "fiftyone_run_key": self.fiftyone_run_key,
            "errors": [dict(error) for error in self.errors],
            **metadata_policy_output_fields(self.metadata_policy),
        }

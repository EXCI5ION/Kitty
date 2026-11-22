from __future__ import annotations

from dataclasses import dataclass

from kitty.matrix_io import PreparedMatrix


@dataclass
class SampleRecord:
    internal_id: str
    original_name: str
    display_name: str
    class_name: str = ""
    individual: str = ""
    included: bool = True


@dataclass
class VariableRecord:
    internal_id: str
    original_name: str
    display_name: str
    included: bool = True


@dataclass
class ProjectState:
    matrix: PreparedMatrix
    samples: list[SampleRecord]
    variables: list[VariableRecord]

    @classmethod
    def from_prepared(
        cls,
        matrix: PreparedMatrix,
        previous: ProjectState | None = None,
    ) -> ProjectState:
        previous_samples = {
            (sample.internal_id, sample.original_name): sample
            for sample in previous.samples
        } if previous is not None else {}
        previous_variables = {
            (variable.internal_id, variable.original_name): variable
            for variable in previous.variables
        } if previous is not None else {}

        samples: list[SampleRecord] = []
        for sample in matrix.samples:
            old = previous_samples.get((sample.internal_id, sample.original_name))
            samples.append(
                SampleRecord(
                    internal_id=sample.internal_id,
                    original_name=sample.original_name,
                    display_name=old.display_name if old else sample.display_name,
                    class_name=old.class_name if old else "",
                    individual=old.individual if old else "",
                    included=old.included if old else True,
                )
            )

        variables: list[VariableRecord] = []
        for variable in matrix.variables:
            old = previous_variables.get((variable.internal_id, variable.original_name))
            variables.append(
                VariableRecord(
                    internal_id=variable.internal_id,
                    original_name=variable.original_name,
                    display_name=old.display_name if old else variable.display_name,
                    included=old.included if old else True,
                )
            )
        return cls(matrix=matrix, samples=samples, variables=variables)

    def class_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for sample in self.samples:
            if not sample.included or not sample.class_name:
                continue
            counts[sample.class_name] = counts.get(sample.class_name, 0) + 1
        return counts

    def included_sample_count(self) -> int:
        return sum(sample.included for sample in self.samples)

    def included_variable_count(self) -> int:
        return sum(variable.included for variable in self.variables)


"""Stable extension contracts for levels and optimization algorithms."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any


@dataclass(frozen=True)
class ExperimentRequest:
    level_id: str
    algorithm_id: str
    config_path: Path
    item_count: int
    container_count: int
    environment: str = "local"
    random_seed: int | None = None
    algorithm_parameters: dict[str, Any] | None = None


@dataclass(frozen=True)
class LocalizedText:
    vi: str
    en: str

    def resolve(self, language: str) -> str:
        if language == "vi":
            return self.vi
        if language == "en":
            return self.en
        raise ValueError(f"Unsupported language: {language!r}")


@dataclass(frozen=True)
class VariableDefinition:
    symbol: str
    latex: str
    variable_type: LocalizedText
    indices: LocalizedText
    meaning: LocalizedText
    code_mapping: str


@dataclass(frozen=True)
class MathematicalExpression:
    expression_id: str
    title: LocalizedText
    latex: str
    explanation: LocalizedText
    code_mapping: str


@dataclass(frozen=True)
class ConstraintDefinition:
    constraint_id: str
    name: LocalizedText
    latex: str
    meaning: LocalizedText
    code_mapping: str


@dataclass(frozen=True)
class LevelContract:
    title: LocalizedText
    problem: LocalizedText
    notation: tuple[MathematicalExpression, ...]
    objective: MathematicalExpression
    variables: tuple[VariableDefinition, ...]
    active_constraints: tuple[ConstraintDefinition, ...]
    inactive_constraints: tuple[LocalizedText, ...]
    assumptions: tuple[LocalizedText, ...]
    limitations: tuple[LocalizedText, ...]
    solution_claim: LocalizedText


@dataclass(frozen=True)
class AlgorithmDefinition:
    algorithm_id: str
    family: str
    description: str
    supported_levels: tuple[str, ...]
    local_friendly: bool
    gpu_recommended: bool = False
    display_name: LocalizedText | None = None
    localized_description: LocalizedText | None = None

    def name_for(self, language: str) -> str:
        return self.algorithm_id if self.display_name is None else self.display_name.resolve(language)

    def description_for(self, language: str) -> str:
        return self.description if self.localized_description is None else self.localized_description.resolve(language)


@dataclass(frozen=True)
class LevelDefinition:
    level_id: str
    description: str
    default_config: Path
    supported_algorithms: tuple[str, ...]
    run: Callable[[ExperimentRequest], Any]
    prepare: Callable[[ExperimentRequest], dict[str, Any]]
    validate_run: Callable[[Path], Any]
    contract: LevelContract

"""Evaluation questions. Files named <dataset>_*.jsonl form one dataset."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

DATASET_DIR = Path(__file__).resolve().parent / "datasets"
DIFFICULTIES = ("easy", "medium", "hard")

Difficulty = Literal["easy", "medium", "hard"]


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    difficulty: Difficulty
    tags: tuple[str, ...]
    question: str
    gold_sql: str
    ordered: bool = False


def load_dataset(name: str, directory: Path = DATASET_DIR) -> list[Question]:
    questions = [
        Question.model_validate_json(line)
        for path in sorted(directory.glob(f"{name}_*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not questions:
        raise ValueError(f"No questions found for dataset {name}.")
    ids = [question.id for question in questions]
    if len(set(ids)) != len(ids):
        raise ValueError(f"Dataset {name} has duplicate question IDs.")
    return questions

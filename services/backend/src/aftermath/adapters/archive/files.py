"""Development answer archive. Append-only JSON files, no database migration."""

import json
import os
import re
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

from aftermath.core.errors import DomainError
from aftermath.core.review import ActivityIndex, ArchivedAnswer, AssessmentRecord

NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
T = TypeVar("T", bound=BaseModel)


class FileAnswerArchive:
    def __init__(self, root: Path):
        self.root = (root / "answer-archive").expanduser().resolve()
        self._lock = threading.Lock()

    def answers(self, workspace: UUID, corpus: str) -> list[ArchivedAnswer]:
        return self._read(workspace, corpus, "answers.json", ArchivedAnswer)

    def add_answer(self, record: ArchivedAnswer) -> None:
        with self._lock:
            current = self._read(
                record.workspace_id, record.corpus_id, "answers.json", ArchivedAnswer
            )
            if any(item.answer_id == record.answer_id for item in current):
                return
            current.append(record)
            self._write(record.workspace_id, record.corpus_id, "answers.json", current)

    def assessments(self, workspace: UUID, corpus: str) -> list[AssessmentRecord]:
        return self._read(workspace, corpus, "assessments.json", AssessmentRecord)

    def add_assessment(self, record: AssessmentRecord) -> None:
        with self._lock:
            current = self._read(
                record.workspace_id, record.corpus_id, "assessments.json", AssessmentRecord
            )
            if any(item.assessment_id == record.assessment_id for item in current):
                return
            current.append(record)
            self._write(record.workspace_id, record.corpus_id, "assessments.json", current)

    def activities(self, workspace: UUID, corpus: str) -> list[ActivityIndex]:
        return self._read(workspace, corpus, "activity.json", ActivityIndex)

    def add_activity(self, record: ActivityIndex) -> None:
        with self._lock:
            current = self._read(
                record.workspace_id, record.corpus_id, "activity.json", ActivityIndex
            )
            current = [item for item in current if item.delivery_id != record.delivery_id]
            current.append(record)
            self._write(record.workspace_id, record.corpus_id, "activity.json", current)

    def _directory(self, workspace: UUID, corpus: str) -> Path:
        if not NAME.fullmatch(corpus):
            raise DomainError("INVALID_INPUT", "Invalid corpus id")
        path = (self.root / str(workspace) / corpus).resolve()
        if not path.is_relative_to(self.root):
            raise DomainError("UNSAFE_OBJECT_PATH", "Archive path is unsafe")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _read(self, workspace: UUID, corpus: str, name: str, model: type[T]) -> list[T]:
        path = self._directory(workspace, corpus) / name
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise DomainError("STORAGE_FAILURE", "Answer archive could not be read", 503) from None
        if not isinstance(payload, list):
            raise DomainError("STORAGE_FAILURE", "Answer archive could not be read", 503)
        return [model.model_validate(item) for item in payload]

    def _write(self, workspace: UUID, corpus: str, name: str, records: Sequence[BaseModel]) -> None:
        path = self._directory(workspace, corpus) / name
        data = json.dumps([item.model_dump(mode="json") for item in records], indent=2)
        temporary = path.with_suffix(".tmp")
        try:
            temporary.write_text(data, encoding="utf-8")
            os.replace(temporary, path)
        except OSError:
            raise DomainError(
                "STORAGE_FAILURE", "Answer archive could not be written", 503
            ) from None

from __future__ import annotations

import uuid
from datetime import date, datetime
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import joinedload
from app.repositories.base import BaseRepository
from app.models.task_continuity import (
    TaskRisk,
    TaskPauseHistory,
    TaskTransferHistory,
    TaskDelegation,
    ManagerDecision,
)
from app.models.task import Task
from app.models.task_assignment import TaskAssignment


class TaskContinuityRepository(BaseRepository):

    def get_risk_by_id(self, id: uuid.UUID) -> TaskRisk | None:
        stmt = (
            select(TaskRisk)
            .options(
                joinedload(TaskRisk.task),
                joinedload(TaskRisk.project),
                joinedload(TaskRisk.assignment),
                joinedload(TaskRisk.employee),
                joinedload(TaskRisk.leave_request),
            )
            .where(TaskRisk.id == id)
        )
        return self.db.scalars(stmt).first()

    def get_risk_by_assignment_and_leave(
        self, assignment_id: uuid.UUID, leave_request_id: uuid.UUID
    ) -> TaskRisk | None:
        stmt = select(TaskRisk).where(
            TaskRisk.assignment_id == assignment_id,
            TaskRisk.leave_request_id == leave_request_id,
        )
        return self.db.scalars(stmt).first()

    def get_all_risks(self, status: str | None = None) -> list[TaskRisk]:
        stmt = select(TaskRisk).options(
            joinedload(TaskRisk.task),
            joinedload(TaskRisk.project),
            joinedload(TaskRisk.assignment),
            joinedload(TaskRisk.employee),
            joinedload(TaskRisk.leave_request),
        )
        if status:
            stmt = stmt.where(TaskRisk.status == status)
        stmt = stmt.order_by(TaskRisk.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def create_risk(self, data: dict) -> TaskRisk:
        risk = TaskRisk(**data)
        self.db.add(risk)
        self.db.flush()
        return risk

    def create_decision(self, data: dict) -> ManagerDecision:
        decision = ManagerDecision(**data)
        self.db.add(decision)
        self.db.flush()
        return decision

    def create_pause_history(self, data: dict) -> TaskPauseHistory:
        history = TaskPauseHistory(**data)
        self.db.add(history)
        self.db.flush()
        return history

    def get_active_pause_history(self, task_id: uuid.UUID) -> TaskPauseHistory | None:
        stmt = (
            select(TaskPauseHistory)
            .where(
                TaskPauseHistory.task_id == task_id,
                TaskPauseHistory.is_active == True,
            )
            .order_by(TaskPauseHistory.paused_at.desc())
        )
        return self.db.scalars(stmt).first()

    def get_active_pauses_for_tasks(self, task_ids: list[uuid.UUID]) -> list[TaskPauseHistory]:
        if not task_ids:
            return []
        stmt = select(TaskPauseHistory).where(
            TaskPauseHistory.task_id.in_(task_ids),
            TaskPauseHistory.is_active == True,
        )
        return list(self.db.scalars(stmt).all())

    def create_transfer_history(self, data: dict) -> TaskTransferHistory:
        history = TaskTransferHistory(**data)
        self.db.add(history)
        self.db.flush()
        return history

    def get_transfer_history_by_task(self, task_id: uuid.UUID) -> list[TaskTransferHistory]:
        stmt = (
            select(TaskTransferHistory)
            .options(
                joinedload(TaskTransferHistory.from_employee),
                joinedload(TaskTransferHistory.to_employee),
                joinedload(TaskTransferHistory.manager),
            )
            .where(TaskTransferHistory.task_id == task_id)
            .order_by(TaskTransferHistory.transfer_date.desc())
        )
        return list(self.db.scalars(stmt).all())

    def create_delegation(self, data: dict) -> TaskDelegation:
        delegation = TaskDelegation(**data)
        self.db.add(delegation)
        self.db.flush()
        return delegation

    def get_delegation_by_id(self, id: uuid.UUID) -> TaskDelegation | None:
        stmt = (
            select(TaskDelegation)
            .options(
                joinedload(TaskDelegation.task),
                joinedload(TaskDelegation.owner),
                joinedload(TaskDelegation.delegate),
                joinedload(TaskDelegation.delegator),
            )
            .where(TaskDelegation.id == id)
        )
        return self.db.scalars(stmt).first()

    def get_active_delegation(self, task_id: uuid.UUID) -> TaskDelegation | None:
        stmt = (
            select(TaskDelegation)
            .where(
                TaskDelegation.task_id == task_id,
                TaskDelegation.status == "ACTIVE",
            )
            .order_by(TaskDelegation.created_at.desc())
        )
        return self.db.scalars(stmt).first()

    def get_active_delegation_by_assignment(self, assignment_id: uuid.UUID) -> TaskDelegation | None:
        # Find active delegation for the task where delegate assignment is target
        # Join TaskDelegation to TaskAssignment
        stmt = (
            select(TaskDelegation)
            .join(Task, Task.id == TaskDelegation.task_id)
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.id == assignment_id,
                TaskDelegation.status == "ACTIVE",
            )
        )
        return self.db.scalars(stmt).first()

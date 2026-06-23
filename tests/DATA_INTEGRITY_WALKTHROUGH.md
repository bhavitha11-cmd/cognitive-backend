# Data Integrity Walkthrough: Batch Create Flow

## End-to-End Trace: Frontend → Backend → Database

### 1. Frontend: WeeklyTimesheetPage.tsx:222-274 (`handleSave`)

The save flow categorizes each cell into one of three actions:

```
for each (task, dayCell):
  value = cellValues[task.id][dateKey]
  existing = existingEntries.get(`${task.id}|${dateKey}`)

  if (no value && existing exists) → DELETE   (toDelete.push(existing.id))
  if (value && existing && changed > 0.01)   → UPDATE (toUpdate.push({id, hoursSpent}))
  if (value && !existing && hours > 0)        → CREATE (toCreate.push({taskId, date, hoursSpent}))
```

Execution order: DELETE → UPDATE → CREATE/batch

### 2. Frontend → Backend: POST /time-entries/batch

Payload shape (`WeeklyTimesheetPage.tsx:264`):
```json
{
  "entries": [
    { "taskId": "uuid", "date": "2026-06-15", "hoursSpent": 4.0 },
    { "taskId": "uuid", "date": "2026-06-16", "hoursSpent": 2.5 }
  ]
}
```

### 3. Backend Router: time_entry.py:105-122 (`batch_create_time_entries`)

- Validates via Pydantic `TimeEntryCreateBatch` schema (`max_length=50`)
- Calls `service.create_batch(data.entries)`
- Wraps ValueError → HTTP 404 ("not found") or 400 (other)
- Returns `{success, message, data: {time_entries: [...]}}`

### 4. Backend Service: time_entry_service.py:28-81 (`create_batch`)

**Validation order per entry (transactional):**
1. Resolve `employee_id` (defaults to `current_user_id`)
2. **Duplicate check (in-memory):** `seen_keys` set → prevents same (employee, task, date) within batch
3. **Duplicate check (DB):** `SELECT COUNT(*) FROM time_entries WHERE employee_id=?, task_id=?, date=?` → prevents existing duplicates
4. Employee exists check
5. Task exists && `is_active == True` check
6. Project exists (via `task.project_id`)

**Creation:**
- `TimeEntry` ORM instance created with `status="DRAFT"`
- `db.add(entry)` + `db.flush()` per entry (gets UUID from DB)
- After all entries processed: `db.commit()` (single transaction)
- For each unique `task_id`: calls `_recompute_task_actual_hours(tid)`
- Audit log: `BATCH_CREATE` with count and task_ids

### 5. Database: `_recompute_task_actual_hours` (line 446-457)

```sql
SELECT COALESCE(SUM(hours_spent), 0)
FROM time_entries
WHERE task_id = ? AND status NOT IN ('REJECTED')
```
Updates `task.actual_hours = <sum>` and commits.

### 6. Response back to Frontend

Frontend receives `{time_entries: [...]}`, calls `refetchEntries()` to refresh the grid.

## Integrity Guarantees

| Property | How Enforced |
|---|---|
| **Atomicity** | Single `db.commit()` at end; any ValueError rolls back entire batch |
| **No duplicates** | `seen_keys` (in-memory) + `SELECT COUNT` (DB check) before insert |
| **Valid references** | FK checks: employee, task (active), project all verified |
| **Self-only** | `employee_id` forced to `current_user_id`; rejects cross-user entries |
| **Recomputation** | `_recompute_task_actual_hours` called once per unique task_id after commit |
| **Audit trail** | `BATCH_CREATE` audit log with entry count and task IDs |
| **Input limits** | Pydantic: `max_length=50` per batch, `hours_spent: gt=0, le=24`, `max_length=2000` on description |

## Failure Scenarios

| Scenario | Behavior | Test Coverage |
|---|---|---|
| Empty batch list | `min_length=1` in Pydantic → 422 | `test_batch_rejects_empty_list` |
| Invalid entry (hours > 24) | Pydantic validation → 422 | `test_batch_rejects_invalid_entry` |
| Entry for other user | `ValueError` → 400 | `test_raises_if_any_entry_for_other_user` |
| Nonexistent task | `ValueError("Referenced task not found")` → 404 | — (implicit in single-create tests) |
| Inactive task | `ValueError("Cannot log...inactive task")` → 400 | — (implicit in single-create tests) |
| Duplicate within batch | `ValueError` in `seen_keys` check → 400 | — (new security fix, test pending) |
| Duplicate vs existing DB entry | `ValueError` in `SELECT COUNT` check → 400 | — (new security fix, test pending) |

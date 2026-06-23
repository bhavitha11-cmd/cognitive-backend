# Manual Testing Plan: Weekly Timesheet Grid

## Prerequisites
- Backend running: `venv\Scripts\Activate.ps1; uvicorn app.main:app --reload`
- Frontend running: `npm run dev`
- Logged in as a user with assigned tasks

## Test Cases

### 1. Weekly Grid Navigation

| Step | Expected |
|---|---|
| Click **←** (prev week) | Grid shifts to previous Mon-Sun, entries reloaded |
| Click **→** (next week) | Grid shifts to next Mon-Sun, entries reloaded |
| Click **Today** icon | Grid resets to current week |
| Verify week range label | Shows correct "Mon, Jun 15 — Sun, Jun 21, 2026" format |
| Switch weeks with unsaved changes | No data loss (note: currently changes are **not** auto-saved on nav) |

### 2. Task Display

| Step | Expected |
|---|---|
| Page loads | Table shows tasks assigned to current user (rows) × 7 days (columns) |
| Department chip | CAD/CAM/GEN chip visible in "Scope" column per task |
| Existing entries | Cells show saved hours; status indicator below cell (✓/⏳/✗ for APPROVED/SUBMITTED/REJECTED) |
| Task search | Type in search box → task list filters in real-time |
| Pagination | When >15 tasks, pagination controls appear at bottom |

### 3. Hour Entry (Create)

| Step | Expected |
|---|---|
| Click empty cell | Typing "4" shows 4.00 |
| Type "3.5" | Accepts decimal values |
| Type "0.25" | Accepts quarter-hour precision |
| Row total | Updates automatically as cells change |
| Week total | Updates automatically |

### 4. Hour Entry (Edit)

| Step | Expected |
|---|---|
| Change existing 4.0 → 6.0 | Save updates entry correctly |
| Change existing 4.0 → 4.0 | Save skips update (no API call for unchanged values — tolerance 0.01) |

### 5. Hour Entry (Delete)

| Step | Expected |
|---|---|
| Clear a cell that had hours → Save | Entry is deleted via `DELETE /time-entries/{id}` |
| Verify after refresh | Cell is empty |

### 6. Save Flow

| Step | Expected |
|---|---|
| Enter hours in 3 cells, edit 1, delete 1 → Click **Save** | Success alert: "Saved! 3 created, 1 updated, 1 removed." |
| Wait for save | Spinner on Save button during API calls |
| Save empty grid | Success with "0 created, 0 updated, 0 removed." |

### 7. Validation

| Step | Expected |
|---|---|
| Type negative number "-1" | Input rejected (doesn't accept) |
| Type text "abc" | Input rejected (doesn't accept) |
| Type "25" (>24h) | Save → error alert from backend (Pydantic validation) |
| Submit empty string | Treated as 0 → no entry created/deleted |

### 8. Entry Status Indicators

| Step | Expected |
|---|---|
| View a cell with APPROVED entry | Shows "✓" below the hours |
| View a cell with SUBMITTED entry | Shows "⏳" below the hours |
| View a cell with REJECTED entry | Shows "✗" below the hours |
| View a DRAFT entry | No status indicator (still editable) |

### 9. Backend Security Verifications

| Test | How |
|---|---|
| Batch limit | Send 51 entries → expect 422 |
| XSS in description | Send `<script>alert(1)</script>` → stored as literal text in DB |
| Hours overflow | Send `hours_spent: 24.01` → expect 422 |
| Forge other user ID | Send `employee_id` of another user → expect 400 |

### 10. Error Handling

| Step | Expected |
|---|---|
| Submit without network | Alert with "Network Error" or API error message |
| Server returns 500 | Alert with "Internal Server Error" |
| Refresh after save | Grid shows persisted data |

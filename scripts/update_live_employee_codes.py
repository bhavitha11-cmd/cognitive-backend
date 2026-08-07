import sys
import uuid
from app.database.session import SessionLocal
from app.models.employee import Employee

# Exact mapping based on user provided list
# Note: Employee names are untouched and preserved as requested.
# Only employee_code numbers/format are updated.
CODE_MAPPING = {
    "4e4942d1-0c5a-4bc4-aefe-4ce7e6607bdf": "CET-009",  # SHANKARAN RAJAVADIVEL
    "ac4e22e7-061b-4f1a-a554-70e0e194979f": "CET-010",  # PRANITHA SRINIVAS
    "9e563558-33ed-46f0-a03d-720a346fdd24": "CET-004",  # LALA LAJAPATHI CHOWDARY MULPURI
    "dc7990e8-a474-401e-92d8-f42314ef08fa": "CET-012",  # DEEPU MS
    "1fefd8d1-e555-47ff-9a10-6819605788fd": "CET-018",  # GOWTHAM SARAVANAN
    "07292e86-ceeb-46b7-93f5-0139c003acc2": "CET-020",  # GURUKIRAN KRISHNACHARI
    "af40f386-8a18-4b14-99ed-7e44dbad2d55": "CET-011",  # MANJUNATHA RV
    "235a3388-44f4-47b4-b1c9-64f83e004f6b": "CET-019",  # PASUPULETI SHANKAR SAI HANUMAN
    "2dc2709c-ff32-4173-9800-0d969c7d6e3e": "CET-013",  # SUPRITHA CL
    "a18ce531-56b9-4dd9-b54c-d19dbb47ef24": "CET-015",  # VAIBHAV KULKARNI
    "c478fb2c-d228-4900-bb46-8847e0e3f1fa": "CET-034",  # KARTHIK SHETTY
    "ae894ad7-1bb6-49ce-b44a-045bd80220cd": "CET-035",  # SINDHU SHETTY
    "a58700a5-483d-422e-a230-c501db6babb8": "CET-021",  # SRUJAN KS
    "55f16035-ab5b-4cbe-9039-1ad699d43a31": "CET-025",  # SANJU KR
    "4611b8e0-0fb6-4c8e-b6a9-f5812fb9e4de": "CET-022",  # KAVIRAJ VARADHARAJ
    "b4b41afb-dfec-4b2c-a9e1-4350dd4e696d": "CET-023",  # SANTHIYA MARAN
    "10f16e9d-8aec-4ad2-91b2-395119f3d372": "CET-024",  # MAGESH MURUGESAN
    "118d4df6-b757-4b2d-ab4c-06eeae257b0b": "CET-026",  # JANGAM SUBBARAYUDU
    "5e5343c9-92b7-4f85-992a-a2202cc6d855": "CET-029",  # NITHYA GOWDA
    "6a501aed-31ee-4e66-8f8b-d17dd9b0c3c4": "CET-030",  # ATHISH JEEVAN YADAV
    "c05d9072-f58f-4052-ab19-473f427fd0f0": "CET-032",  # GUNASEKAR DHANAVEL
    "8d18037a-1862-4bd5-b2b5-13cfc20cfdbf": "CET-028",  # YATHISH MG
    "670e5e38-2571-41bc-92c2-684de77419ab": "CET-033",  # SOUNDARAJAN SUNDARAM
    "b20e0ab9-e57d-499a-b073-6da5027f116c": "CET-017",  # SIVARAMAN RAVICHANDRAN
}

def run_update():
    db = SessionLocal()
    try:
        updated_count = 0
        for emp_id_str, new_code in CODE_MAPPING.items():
            emp = db.query(Employee).filter(Employee.id == uuid.UUID(emp_id_str)).first()
            if emp:
                old_code = emp.employee_code
                emp.employee_code = new_code
                db.add(emp)
                print(f"Updated '{emp.first_name} {emp.last_name}' ({emp.id}): {old_code} -> {new_code}")
                updated_count += 1
            else:
                print(f"WARNING: Employee ID {emp_id_str} not found in database!")

        # Also update system user EMP-001 -> CET-001 if exists
        sys_emp = db.query(Employee).filter(Employee.employee_code == "EMP-001").first()
        if sys_emp:
            sys_emp.employee_code = "CET-001"
            db.add(sys_emp)
            print(f"Updated System User: EMP-001 -> CET-001")
            updated_count += 1

        db.commit()
        print(f"\nSUCCESSFULLY UPDATED {updated_count} EMPLOYEES TO CET-XXX FORMAT!")
    except Exception as e:
        db.rollback()
        print(f"ERROR: Update failed, rolled back changes: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    run_update()

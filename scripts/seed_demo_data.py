"""
Seed script: populate the database with 2000 employees and realistic
certificate history so the system looks like it has been in production.

Data is injected directly into PostgreSQL via batch INSERT with pre-computed IDs.

Usage:
    python3 scripts/seed_demo_data.py > /tmp/seed_demo.sql
    docker compose exec -T postgres psql -U laredo -d laredo_certificates < /tmp/seed_demo.sql
"""

import hashlib
import json
import random
import sys
from datetime import date, timedelta

random.seed(42)  # Reproducible results

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NUM_EMPLOYEES = 2000
EMP_ID_START = 3          # IDs 1-2 are existing (admin + cash)
DOC_ID_START = 1          # Tables were cleared
REVIEWER_ID = 2           # Coordinator (Cash Bailey) reviews everything
CHUNK_SIZE = 500          # Rows per INSERT statement
TODAY = date(2026, 2, 3)  # Cap 5 days before real today so newest items show "~5 days" not "Today"
HISTORY_START = date(2024, 1, 15)  # System "went live"

# ---------------------------------------------------------------------------
# Name pools — weighted toward Hispanic/Latino names (Laredo ~95% Hispanic)
# ---------------------------------------------------------------------------
FIRST_NAMES_M = [
    "Jose", "Juan", "Carlos", "Miguel", "Luis", "David", "Jesus", "Daniel",
    "Ricardo", "Alejandro", "Fernando", "Roberto", "Eduardo", "Antonio",
    "Francisco", "Sergio", "Arturo", "Gabriel", "Raul", "Pedro", "Rafael",
    "Jorge", "Mario", "Oscar", "Hector", "Enrique", "Victor", "Manuel",
    "Marco", "Andres", "Adrian", "Rodrigo", "Diego", "Cesar", "Gerardo",
    "Ernesto", "Alberto", "Salvador", "Javier", "Guillermo", "Ruben",
    "Alfredo", "Lorenzo", "Rogelio", "Armando", "Jaime", "Reynaldo",
    "John", "James", "Michael", "Robert", "William", "Thomas", "Richard",
    "Christopher", "Anthony", "Mark", "Steven", "Brian", "Kevin", "Jason",
]

FIRST_NAMES_F = [
    "Maria", "Ana", "Laura", "Patricia", "Claudia", "Gabriela", "Carmen",
    "Rosa", "Sandra", "Monica", "Leticia", "Veronica", "Adriana", "Silvia",
    "Elena", "Isabel", "Teresa", "Alejandra", "Diana", "Beatriz", "Lucia",
    "Sofia", "Daniela", "Fernanda", "Mariana", "Catalina", "Irma",
    "Guadalupe", "Esperanza", "Dolores", "Yolanda", "Norma", "Martha",
    "Gloria", "Alma", "Marisol", "Brenda", "Erica", "Anita", "Blanca",
    "Jennifer", "Jessica", "Sarah", "Amanda", "Emily", "Rachel", "Melissa",
    "Michelle", "Nicole", "Lisa", "Karen", "Ashley", "Stephanie", "Megan",
]

LAST_NAMES = [
    "Garcia", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Perez", "Sanchez", "Ramirez", "Torres", "Flores", "Rivera",
    "Gomez", "Diaz", "Cruz", "Morales", "Reyes", "Gutierrez", "Ortiz",
    "Ramos", "Castillo", "Jimenez", "Moreno", "Romero", "Morgan",
    "Ruiz", "Mendoza", "Aguilar", "Medina", "Castro", "Vargas",
    "Vasquez", "Guerrero", "Herrera", "Salazar", "Delgado", "Pena",
    "Sandoval", "Contreras", "Soto", "Rojas", "Luna", "Estrada",
    "Acosta", "Silva", "Campos", "Vega", "Molina", "Navarro", "Rios",
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis",
    "Wilson", "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris",
    "Martin", "Thompson", "Robinson", "Clark", "Lewis", "Lee",
]

# ---------------------------------------------------------------------------
# City of Laredo departments
# ---------------------------------------------------------------------------
DEPARTMENTS = [
    "Public Works", "Parks & Recreation", "Utilities", "Fire Department",
    "Police Department", "Health Department", "Transit", "Planning & Zoning",
    "Finance", "Human Resources", "Information Technology", "City Manager",
    "City Secretary", "Legal", "Library", "Municipal Court", "Building & Codes",
    "Environmental Services", "Community Development", "Bridge Department",
    "Convention & Visitors Bureau", "Solid Waste", "Traffic Engineering",
    "Fleet Management", "Animal Care Services",
]

# ---------------------------------------------------------------------------
# Certificate types aligned with DB seed (IDs 1-6)
# ---------------------------------------------------------------------------
CERT_TYPES = {
    1: {
        "name": "Commercial Driver License (CDL)",
        "authority": "Texas Department of Public Safety",
        "validity_days": 1825,
        "departments": ["Public Works", "Utilities", "Transit", "Solid Waste",
                         "Fleet Management", "Environmental Services",
                         "Parks & Recreation", "Bridge Department"],
        "pct": 0.15,
        "hours": None,
        "renewals": (1, 2),  # min, max instances
    },
    2: {
        "name": "First Aid & CPR Certification",
        "authority": "American Red Cross",
        "validity_days": 730,
        "departments": None,
        "pct": 0.60,
        "hours": 8.0,
        "renewals": (1, 3),
    },
    3: {
        "name": "Hazmat Transportation Certification",
        "authority": "US Department of Transportation",
        "validity_days": 1095,
        "departments": ["Public Works", "Utilities", "Environmental Services",
                         "Fire Department", "Solid Waste"],
        "pct": 0.08,
        "hours": 24.0,
        "renewals": (1, 2),
    },
    4: {
        "name": "LMS Certificate of Completion",
        "authority": "City of Laredo LMS",
        "validity_days": None,
        "departments": None,
        "pct": 0.85,
        "hours": None,
        "renewals": (1, 3),  # 1-3 different courses
    },
    5: {
        "name": "HIPAA Acknowledgment",
        "authority": "City of Laredo Health Department",
        "validity_days": 365,
        "departments": ["Health Department", "Human Resources", "City Manager",
                         "Legal", "Fire Department", "Police Department"],
        "pct": 0.25,
        "hours": 2.0,
        "renewals": (1, 2),
    },
    6: {
        "name": "Employee Policies Acknowledgment",
        "authority": "City of Laredo Human Resources",
        "validity_days": 365,
        "departments": None,
        "pct": 0.90,
        "hours": 1.0,
        "renewals": (1, 3),
    },
}

LMS_COURSES = [
    "Sexual Harassment & Other Harassment Prevention Training",
    "Workplace Safety Fundamentals",
    "Ethics in Government Service",
    "Cybersecurity Awareness Training",
    "Defensive Driving Course",
    "Customer Service Excellence",
    "Diversity & Inclusion in the Workplace",
    "Emergency Preparedness & Response",
    "Bloodborne Pathogens Training",
    "Conflict Resolution in the Workplace",
    "Fire Extinguisher Safety Training",
    "OSHA 10-Hour General Industry",
    "Hazard Communication (HazCom)",
    "Personal Protective Equipment (PPE)",
    "Lockout/Tagout Safety Procedures",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(0, delta)))


def sql_str(val) -> str:
    if val is None:
        return "NULL"
    return "'" + str(val).replace("'", "''") + "'"


def sql_date(val) -> str:
    if val is None:
        return "NULL"
    return f"'{val.isoformat()}'"


def sql_ts(d: date) -> str:
    """Generate a realistic timestamp from a date."""
    h = random.randint(7, 17)
    m = random.randint(0, 59)
    s = random.randint(0, 59)
    return f"'{d.isoformat()}T{h:02d}:{m:02d}:{s:02d}+00:00'"


def sql_json(val) -> str:
    return "'" + json.dumps(val).replace("'", "''") + "'::jsonb"


def make_extracted_fields(holder_name, cert_type_name, issue_dt, authority, hours=None):
    """Build realistic extracted_fields JSONB matching pipeline output."""
    def conf():
        """Random but high confidence values."""
        base = random.uniform(0.88, 0.99)
        return {
            "zone": round(base + random.uniform(-0.03, 0.02), 2),
            "ocr": round(base + random.uniform(-0.05, 0.01), 2),
            "parse": round(min(1.0, base + random.uniform(0.0, 0.05)), 2),
            "validate": 1.0,
            "overall": round(base, 2),
        }

    fields = {
        "certificate_holder_name": {
            "value": holder_name,
            "confidence": conf(),
            "extraction_source": "zone",
            "needs_review": False,
        },
        "certificate_type": {
            "value": cert_type_name,
            "confidence": conf(),
            "extraction_source": "zone",
            "needs_review": False,
        },
        "issue_date": {
            "value": issue_dt.isoformat(),
            "confidence": conf(),
            "extraction_source": "zone",
            "needs_review": False,
        },
        "issuing_authority": {
            "value": authority,
            "confidence": conf(),
            "extraction_source": "zone",
            "needs_review": False,
        },
    }
    if hours is not None:
        fields["training_hours"] = {
            "value": str(hours),
            "confidence": conf(),
            "extraction_source": "zone",
            "needs_review": False,
        }
    return fields


def chunked_insert(table, columns, rows, out):
    """Print INSERT statements in chunks."""
    cols = ", ".join(columns)
    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i:i + CHUNK_SIZE]
        out.write(f"INSERT INTO {table}\n    ({cols})\nVALUES\n")
        out.write(",\n".join(chunk))
        out.write(";\n\n")


# ===========================================================================
# Generate data
# ===========================================================================

out = sys.stdout

# --- Employees ---
employees = []
used_emails = {"admin@ci.laredo.tx.us", "cashbailey@ci.laredo.tx.us"}
used_emp_numbers = {"ADMIN001", "105a3"}

for i in range(NUM_EMPLOYEES):
    emp_id = EMP_ID_START + i
    is_female = random.random() < 0.45
    first = random.choice(FIRST_NAMES_F if is_female else FIRST_NAMES_M)
    last = random.choice(LAST_NAMES)
    department = random.choice(DEPARTMENTS)

    # Unique email
    email_base = f"{first.lower()}.{last.lower()}"
    email = f"{email_base}@ci.laredo.tx.us"
    suffix = 2
    while email in used_emails:
        email = f"{email_base}{suffix}@ci.laredo.tx.us"
        suffix += 1
    used_emails.add(email)

    # Unique employee number
    while True:
        emp_num = f"{random.randint(10000, 99999)}"
        if emp_num not in used_emp_numbers:
            used_emp_numbers.add(emp_num)
            break

    hire_date = random_date(date(2015, 1, 1), date(2025, 12, 31))
    created_at = max(hire_date, HISTORY_START)

    employees.append({
        "id": emp_id,
        "first": first,
        "last": last,
        "email": email,
        "emp_num": emp_num,
        "department": department,
        "hire_date": hire_date,
        "created_at": created_at,
    })

# --- Certificates ---
documents = []   # (doc_id, emp_id, ...)
extractions = [] # (ext_id, doc_id, ...)
verified = []    # (ver_id, ext_id, doc_id, emp_id, ...)

next_doc_id = DOC_ID_START
next_ext_id = DOC_ID_START
next_ver_id = DOC_ID_START

for emp in employees:
    holder_name = f"{emp['last']}, {emp['first']}"

    for cert_type_id, ct in CERT_TYPES.items():
        # Department filter
        if ct["departments"] is not None:
            if emp["department"] not in ct["departments"]:
                continue

        # Probability filter
        if random.random() > ct["pct"]:
            continue

        # Number of instances (renewals or different courses)
        num = random.randint(*ct["renewals"])

        for instance in range(num):
            # Compute issue date window
            if num > 1 and ct["validity_days"]:
                start = HISTORY_START + timedelta(days=instance * ct["validity_days"])
                end = min(start + timedelta(days=ct["validity_days"]), TODAY)
            else:
                start = max(HISTORY_START, emp["hire_date"])
                end = TODAY - timedelta(days=10)

            if start >= end:
                continue

            issue_dt = random_date(start, end)
            exp_dt = (issue_dt + timedelta(days=ct["validity_days"])) if ct["validity_days"] else None

            # Cert name (LMS gets random course)
            cert_name = ct["name"]
            if cert_type_id == 4:
                cert_name = random.choice(LMS_COURSES)

            # Cert number
            cert_number = None
            if cert_type_id == 1:
                cert_number = f"TX{random.randint(10000000, 99999999)}"
            elif cert_type_id == 3:
                cert_number = f"HM-{random.randint(100000, 999999)}"

            # Hours
            hours = ct["hours"]
            if hours and cert_type_id == 4:
                hours = random.choice([1.0, 2.0, 4.0, 8.0])

            # CDL extras
            license_class = None
            endorsements = None
            if cert_type_id == 1:
                license_class = random.choice(["A", "B", "C"])
                endorsements = random.choice([None, "H", "N", "T", "H,N", "H,T"])

            # Timestamps — uploaded and reviewed within 5 days of issue
            upload_dt = issue_dt + timedelta(days=random.randint(0, 2))
            if upload_dt > TODAY:
                upload_dt = TODAY
            review_dt = upload_dt + timedelta(days=random.randint(1, 2))
            # Cap at 5 days from issue date
            max_review = issue_dt + timedelta(days=5)
            if review_dt > max_review:
                review_dt = max_review
            if review_dt > TODAY:
                review_dt = TODAY

            # Status mix — system looks well-maintained, no backlog
            roll = random.random()
            if roll < 0.002:
                review_state = "Rejected"
            else:
                review_state = "Approved"

            needs_review = review_state == "PendingReview"
            reviewed_by = REVIEWER_ID if review_state in ("Approved", "Rejected") else None
            reviewed_at = review_dt if review_state in ("Approved", "Rejected") else None

            # Extracted fields JSONB
            extracted_fields = make_extracted_fields(
                holder_name, cert_name, issue_dt, ct["authority"], hours
            )

            doc_id = next_doc_id

            # File metadata — use doc_id in storage_key for guaranteed uniqueness
            file_name = (
                f"{emp['last']}_{emp['first']}_"
                f"{cert_name[:20].replace(' ', '_')}_"
                f"{issue_dt.isoformat()}.pdf"
            )
            storage_key = f"docs/{emp['emp_num']}/{doc_id:06d}.pdf"
            ext_id = next_ext_id
            ver_id = next_ver_id
            next_doc_id += 1
            next_ext_id += 1
            next_ver_id += 1

            documents.append((
                doc_id, emp["id"], storage_key, file_name, "application/pdf",
                random.randint(50000, 500000), REVIEWER_ID, "Coordinator",
                upload_dt,
            ))

            extractions.append((
                ext_id, doc_id, review_state, extracted_fields, needs_review,
                reviewed_by, reviewed_at, upload_dt, review_dt,
            ))

            # Only Approved certs get verified records
            if review_state == "Approved":
                verified.append((
                    ver_id, ext_id, doc_id, emp["id"],
                    holder_name, cert_name, cert_number, ct["authority"],
                    issue_dt, exp_dt, hours, license_class, endorsements,
                    review_dt,
                ))
            else:
                next_ver_id -= 1  # Don't waste an ID


# ===========================================================================
# Output SQL
# ===========================================================================

out.write("-- =============================================================\n")
out.write(f"-- Demo seed: {NUM_EMPLOYEES} employees, {len(documents)} certificates\n")
out.write("-- City of Laredo Certificate Management System\n")
out.write("-- =============================================================\n")
out.write("BEGIN;\n\n")

# --- Employees ---
emp_rows = []
for e in employees:
    emp_rows.append(
        f"  ({e['id']}, {sql_str(e['emp_num'])}, {sql_str(e['first'])}, "
        f"{sql_str(e['last'])}, {sql_str(e['email'])}, 'Employee', true, "
        f"{sql_ts(e['created_at'])}, {sql_ts(TODAY)})"
    )
chunked_insert(
    "certificates.employees",
    ["id", "employee_number", "first_name", "last_name", "email",
     "role", "is_active", "created_at", "updated_at"],
    emp_rows, out,
)

# --- Documents ---
doc_rows = []
for d in documents:
    doc_id, emp_id, skey, fname, ftype, fsize, uploader, acting, upload_dt = d
    doc_rows.append(
        f"  ({doc_id}, {emp_id}, {sql_str(skey)}, {sql_str(fname)}, "
        f"{sql_str(ftype)}, {fsize}, {uploader}, {sql_str(acting)}, "
        f"{sql_ts(upload_dt)}, 'MANUAL_UPLOAD')"
    )
chunked_insert(
    "certificates.certificate_documents",
    ["id", "employee_id", "storage_key", "file_name", "file_type",
     "file_size_bytes", "uploaded_by_id", "acting_as", "created_at",
     "intake_channel"],
    doc_rows, out,
)

# --- Extractions ---
ext_rows = []
for e in extractions:
    ext_id, doc_id, state, fields, needs, rev_by, rev_at, created, updated = e
    review_reasons = '[]' if not needs else '["Awaiting coordinator review"]'
    ext_rows.append(
        f"  ({ext_id}, {doc_id}, {sql_str(state)}, {sql_json(fields)}, "
        f"{'true' if needs else 'false'}, '{review_reasons}'::jsonb, "
        f"'lms_certificate', 1, NULL, NULL, "
        f"{'NULL' if rev_by is None else rev_by}, "
        f"{'NULL' if rev_at is None else sql_ts(rev_at)}, "
        f"{'0' if state in ('Processing', 'PendingReview') else '2'}, "
        f"{sql_ts(created)}, {sql_ts(updated)})"
    )
chunked_insert(
    "certificates.extraction_runs",
    ["id", "document_id", "review_state", "extracted_fields",
     "needs_review", "needs_review_reasons",
     "template_id", "template_version", "template_match_evidence", "review_assist",
     "reviewed_by_id", "reviewed_at", "review_state_version",
     "created_at", "updated_at"],
    ext_rows, out,
)

# --- Verified records (only for Approved) ---
ver_rows = []
for v in verified:
    (ver_id, ext_id, doc_id, emp_id,
     holder, ctype, cnum, auth,
     issue, exp, hours, lic, endorse,
     rev_dt) = v
    ver_rows.append(
        f"  ({ver_id}, {ext_id}, {doc_id}, {emp_id}, "
        f"{sql_str(holder)}, {sql_str(ctype)}, {sql_str(cnum)}, {sql_str(auth)}, "
        f"{sql_date(issue)}, {sql_date(exp)}, "
        f"{'NULL' if hours is None else hours}, "
        f"{sql_str(lic)}, {sql_str(endorse)}, "
        f"{sql_ts(rev_dt)}, {REVIEWER_ID}, {sql_ts(rev_dt)})"
    )
chunked_insert(
    "certificates.verified_certificate_records",
    ["id", "extraction_id", "document_id", "employee_id",
     "certificate_holder_name", "certificate_type",
     "certificate_number", "issuing_authority",
     "issue_date", "expiration_date",
     "training_hours", "license_class", "endorsements",
     "created_at", "reviewed_by_id", "reviewed_at"],
    ver_rows, out,
)

# --- Reset sequences ---
max_emp_id = EMP_ID_START + NUM_EMPLOYEES - 1
max_doc_id = next_doc_id - 1
max_ext_id = next_ext_id - 1
max_ver_id = next_ver_id - 1

out.write("-- Reset sequences\n")
out.write(f"SELECT setval('certificates.employees_id_seq', {max_emp_id});\n")
out.write(f"SELECT setval('certificates.certificate_documents_id_seq', {max_doc_id});\n")
out.write(f"SELECT setval('certificates.extraction_runs_id_seq', {max_ext_id});\n")
out.write(f"SELECT setval('certificates.verified_certificate_records_id_seq', {max_ver_id});\n")
out.write("\nCOMMIT;\n")

# Summary to stderr
print(f"Generated: {NUM_EMPLOYEES} employees, {len(documents)} documents, "
      f"{len(extractions)} extractions, {len(verified)} verified records",
      file=sys.stderr)
states = {}
for e in extractions:
    states[e[2]] = states.get(e[2], 0) + 1
print(f"Status mix: {states}", file=sys.stderr)

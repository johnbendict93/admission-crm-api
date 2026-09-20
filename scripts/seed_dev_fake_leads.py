"""
Generate realistic FAKE admission enquiries for the DEV database only.

Why: no real leads exist until the product is sold, and the demo / future ML
modules need believable data. Everything here is invented - no real person,
no real phone number, no scraped data.

Safety rules (do not weaken):
  * DEV ONLY. Uses DEV_SUPABASE_URL/KEY and refuses to run if they are empty
    or equal to the PROD credentials.
  * DRY-RUN BY DEFAULT. Nothing touches the database unless --apply is given.
    Dry-run needs no .env and no network.
  * EVERY fake row is marked by an e-mail on MARKER_DOMAIN. (example.com
    sub-domains can never belong to anyone; '.invalid' is NOT used because
    pydantic's EmailStr rejects it and the API would 500 on those rows.)
  * Requires migration 0018 (leads.parent_phone) to be applied on DEV first.
  * Fake phone numbers start with 5 (not an assigned Indian mobile range).
  * --delete removes exactly the marked rows and nothing else.

Usage (from the API repo root, in the conda env):
    python scripts/seed_dev_fake_leads.py                    # dry-run, 500 leads, prints a sample
    python scripts/seed_dev_fake_leads.py --count 500 --apply
    python scripts/seed_dev_fake_leads.py --delete           # dry-run: counts what would go
    python scripts/seed_dev_fake_leads.py --delete --apply   # really delete the fake rows

NOTE ON REALISM: the TN cut-off formula (Maths + Physics/2 + Chemistry/2, out
of 200) is the real one. The course-interest mix is calibrated to public
state-wide TNEA 2026 branch shares (see COURSES). The other distributions
(district mix, enquiry seasonality, source mix, conversion odds) are still
hand-set assumptions, NOT yet calibrated to official TNEA / DGE statistics. Fine for demos and pipeline
tests; do not quote model accuracy from this data as if it were real.
"""
import argparse
import math
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MARKER_DOMAIN = "seed.example.com"
IST = timezone(timedelta(hours=5, minutes=30))

MALE = ["Karthik", "Arun", "Vignesh", "Sathish", "Manoj", "Dinesh", "Prakash", "Suresh", "Ramesh", "Harish",
        "Gokul", "Naveen", "Vijay", "Ajith", "Surya", "Bharath", "Kishore", "Lokesh", "Tamilarasan", "Elango",
        "Muthu", "Saravanan", "Ganesh", "Mohan", "Selvam", "Kannan", "Balaji", "Deepak", "Yuvaraj", "Ashwin"]
FEMALE = ["Priya", "Divya", "Kavya", "Nandhini", "Swathi", "Keerthana", "Meena", "Lakshmi", "Anitha", "Ramya",
          "Sandhya", "Pavithra", "Harini", "Janani", "Monisha", "Yamuna", "Deepika", "Sowmiya", "Abirami", "Gayathri",
          "Bhuvana", "Thenmozhi", "Vaishnavi", "Sneha", "Kalaiselvi", "Aishwarya", "Revathi", "Mythili", "Nithya", "Sangeetha"]
SECOND_M = ["Kumar", "Raj", "Kannan", "Babu", "Selvan", "Prabhu", "Nathan", "Krishnan", "Murugan", "Velan", "Anand", "Sekar"]
SECOND_F = ["Priya", "Dharshini", "Shree", "Devi", "Sri", "Mathi", "Rani", "Kumari", "Selvi", "Lakshmi", "Bala", "Jothi"]

DISTRICTS = {  # district: (weight, towns)
    "Chennai": (20, ["Adyar", "T. Nagar", "Ambattur", "Perambur", "Velachery", "Kolathur"]),
    "Kancheepuram": (13, ["Sriperumbudur", "Walajabad", "Uthiramerur", "Kancheepuram"]),
    "Villupuram": (13, ["Gingee", "Tindivanam", "Vikravandi", "Villupuram"]),
    "Cuddalore": (8, ["Chidambaram", "Neyveli", "Panruti", "Cuddalore"]),
    "Vellore": (8, ["Katpadi", "Gudiyatham", "Arcot", "Vellore"]),
    "Coimbatore": (5, ["Pollachi", "Mettupalayam", "Singanallur"]),
    "Madurai": (4, ["Melur", "Thirumangalam", "Usilampatti"]),
    "Tiruchirappalli": (4, ["Srirangam", "Lalgudi", "Musiri"]),
    "Salem": (4, ["Attur", "Omalur", "Mettur"]),
    "Tirunelveli": (3, ["Palayamkottai", "Ambasamudram"]),
    "Erode": (3, ["Bhavani", "Gobichettipalayam"]),
    "Thanjavur": (4, ["Kumbakonam", "Papanasam", "Orathanadu"]),
    "Namakkal": (3, ["Rasipuram", "Tiruchengode"]),
    "Dindigul": (3, ["Palani", "Oddanchatram"]),
    "Other": (5, ["Tiruvannamalai", "Krishnagiri", "Dharmapuri", "Ariyalur"]),
}
NEAR = {"Chennai", "Kancheepuram", "Villupuram", "Cuddalore", "Vellore"}
SCHOOL_KINDS = ["Govt. Hr. Sec. School", "Govt. Boys Hr. Sec. School", "Govt. Girls Hr. Sec. School",
                "St. Joseph's Matric. Hr. Sec. School", "Sri Vidya Matric. Hr. Sec. School",
                "Little Flower Matric. Hr. Sec. School", "Bharathi Matric. Hr. Sec. School",
                "Adarsh Vidyalaya Matric. Hr. Sec. School"]
STREETS = ["Gandhi Street", "Nehru Nagar", "Anna Salai", "Kamaraj Road", "Periyar Street", "Bharathi Nagar", "Ambedkar Street"]

# Course-interest mix, calibrated (Sept 2026) to PUBLIC state-wide TNEA 2026 seat
# shares (secondary sources quoting tneaonline.org; the official site was not
# reachable): CSE ~31%, AI&DS+AI&ML ~12%, ECE ~14%, EEE ~7%, Mech ~10%, Civil ~5%,
# IT+Biomedical+other ~22%. AI&DS is deliberately kept above its seat share (target
# 16%) because it is a high-demand branch DCE teaches. The base weights below are
# tuned so the REALISED mix (after the marks>80 boost for CS/AI further down) lands
# on: CS 31 / AI&DS 16 / ECE 14 / EEE 7 / Mech 10 / Civil 5 / Other 17.
# Seat share is supply, not enquiry demand - treat this as a plausibility anchor.
COURSES = [("B.E. Computer Science", 28.6), ("B.E. AI & Data Science", 14.6), ("B.E. Electronics & Communication", 15.1),
           ("B.E. Electrical & Electronics", 7.1), ("B.E. Mechanical", 10.9), ("B.E. Civil", 5.2), ("Other", 18.5)]
# MBA / MCA are deliberately left out: these are 12th-standard students, who do not enquire for PG courses.
OCCUPATIONS = [("Government Employee", 12, 0.10), ("Private Employee", 28, 0.0), ("Business", 20, 0.15),
               ("Farmer", 22, -0.10), ("Daily Wage", 14, -0.15), ("Other", 4, 0.0)]
# source: (weight, effect on conversion odds)
SOURCES = {"Instagram Ad": (18, -0.3), "Facebook Ad": (10, -0.4), "Walk-in": (14, 0.6), "Phone Enquiry": (14, 0.0),
           "Referral": (12, 0.7), "School Visit": (14, 0.4), "Website": (6, -0.1), "WhatsApp": (8, 0.0), "Other": (4, -0.3)}
CATEGORIES = [("BC", 40), ("MBC", 22), ("SC", 17), ("OC", 12), ("BCM", 4), ("SCA", 3), ("ST", 2)]
TELECALLERS = ["Telecaller A", "Telecaller B", "Telecaller C", "Telecaller D"]
# enquiry seasonality (results in May, TNEA Jun-Sep): month -> weight
MONTH_W = {1: 3, 2: 5, 3: 7, 4: 9, 5: 18, 6: 20, 7: 14, 8: 8, 9: 5, 10: 4, 11: 3, 12: 3}


def wpick(rng, pairs):
    items, weights = zip(*[(p[0], p[1]) for p in pairs])
    return rng.choices(items, weights=weights, k=1)[0]


def person_name(rng, female):
    return f"{rng.choice(FEMALE if female else MALE)} {rng.choice(SECOND_F if female else SECOND_M)}"


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def sigmoid(z):
    return 1 / (1 + math.exp(-z))


def enquiry_datetime(rng, today):
    start = today - timedelta(days=365)
    days = [start + timedelta(days=i) for i in range(365)]
    d = rng.choices(days, weights=[MONTH_W[x.month] for x in days], k=1)[0]
    return datetime(d.year, d.month, d.day, rng.randint(9, 18), rng.randint(0, 59), tzinfo=IST)


def generate(count, seed):
    rng = random.Random(seed)
    today = date.today()
    raw = []
    used_phones = set()

    def fake_phone():
        while True:
            p = "5" + "".join(str(rng.randint(0, 9)) for _ in range(9))
            if p not in used_phones:
                used_phones.add(p)
                return p

    for i in range(count):
        female = rng.random() < 0.42
        name = person_name(rng, female)
        district = wpick(rng, [(k, v[0]) for k, v in DISTRICTS.items()])
        town = rng.choice(DISTRICTS[district][1])
        school = f"{rng.choice(SCHOOL_KINDS)}, {town}"
        marks = round(clip(rng.gauss(74, 13), 45, 99), 1)
        # subject marks around the overall %, real TN cut-off = M + P/2 + C/2 (out of 200)
        maths = clip(marks + rng.gauss(0, 8), 35, 100)
        phys = clip(marks + rng.gauss(-2, 8), 35, 100)
        chem = clip(marks + rng.gauss(-1, 8), 35, 100)
        cutoff = round(maths + (phys + chem) / 2, 2)
        pcm = round((maths + phys + chem) / 3, 2)
        # course choice leans CS/AI for higher marks
        courses = [(c, w * (1.5 if (marks > 80 and ("Computer" in c or "AI" in c)) else 1.0)) for c, w in COURSES]
        course = wpick(rng, courses)
        occ, _, occ_eff = None, None, None
        occ_row = rng.choices(OCCUPATIONS, weights=[o[1] for o in OCCUPATIONS], k=1)[0]
        occ, occ_eff = occ_row[0], occ_row[2]
        source = wpick(rng, [(k, v[0]) for k, v in SOURCES.items()])
        created = enquiry_datetime(rng, today)
        logit_base = (
            0.02 * (cutoff - 140)                 # decent cut-off -> more likely to join
            - 0.05 * max(0.0, cutoff - 170)        # very high cut-off students usually go elsewhere
            + SOURCES[source][1] + occ_eff
            + (0.4 if district in NEAR else -0.3)
            + rng.gauss(0, 0.6)
        )
        raw.append(dict(i=i, female=female, name=name, district=district, town=town, school=school, marks=marks,
                        maths=maths, phys=phys, chem=chem, cutoff=cutoff, pcm=pcm, course=course, occ=occ,
                        source=source, created=created, logit=logit_base))

    # calibrate intercept so ~24% of enquiries are "would convert"
    lo, hi = -6.0, 6.0
    for _ in range(60):
        mid = (lo + hi) / 2
        mean_p = sum(sigmoid(r["logit"] + mid) for r in raw) / len(raw)
        lo, hi = (mid, hi) if mean_p < 0.24 else (lo, mid)
    intercept = (lo + hi) / 2

    leads, applicants = [], []
    now = datetime.now(IST)
    for r in raw:
        p = sigmoid(r["logit"] + intercept)
        converts = rng.random() < p
        age_days = max(0, (now - r["created"]).days)
        resolved_prob = min(1.0, age_days / 150) ** 0.7
        if rng.random() < resolved_prob:
            status = "Enrolled" if converts else "Lost"
        else:
            status = rng.choices(["New", "Contacted", "Visited"],
                                 weights=[3, 4, 2] if age_days < 20 else [1, 3, 3], k=1)[0]
        father = f"{rng.choice(MALE)} {rng.choice(SECOND_M)}"
        phone = fake_phone()          # student's number
        parent_phone = fake_phone()   # parent's number (leads.parent_phone, added by migration 0018)
        email = f"{r['name'].lower().replace(' ', '.')}.{r['i']}@{MARKER_DOMAIN}"
        score = int(clip(r["marks"] * 0.55 + SOURCES[r["source"]][1] * 10 + rng.gauss(10, 8), 5, 98))
        leads.append(dict(
            name=r["name"], phone=phone, parent_phone=parent_phone, email=email, school=r["school"], district=r["district"], marks=r["marks"],
            course_interest=r["course"], parent_name=father, parent_occupation=r["occ"], source=r["source"],
            status=status, score=score, assigned_to=rng.choice(TELECALLERS),
            created_at=r["created"].isoformat(),
        ))
        if status == "Enrolled":
            first, _, last = r["name"].partition(" ")
            joined = min(now, r["created"] + timedelta(days=rng.randint(5, 40)))
            dob_year = joined.year - 18 - (1 if rng.random() < 0.3 else 0)
            dept = r["course"].replace("B.E. ", "") if r["course"].startswith("B.E.") else None
            applicants.append(dict(
                first_name=first, last_name=last or first, gender="Female" if r["female"] else "Male",
                date_of_birth=date(dob_year, rng.randint(1, 12), rng.randint(1, 28)).isoformat(),
                phone=phone, email=email, parent_name=father, parent_phone=parent_phone, father_name=father,
                father_mobile=parent_phone, parent_occupation=r["occ"],
                address=f"{rng.randint(1, 120)}, {rng.choice(STREETS)}, {r['town']}, {r['district']}",
                city=r["district"], state="Tamil Nadu", pincode=str(rng.randint(600001, 639999)),
                category=wpick(rng, CATEGORIES), twelfth_school=r["school"], school_name=r["school"],
                twelfth_board="State Board", twelfth_year=joined.year, twelfth_percentage=r["marks"],
                hsc_percentage=r["marks"], twelfth_group="Physics-Chemistry-Maths-Computer Science",
                pcm_marks=r["pcm"], cutoff_marks=r["cutoff"], lead_source=r["source"],
                programme_interested="B.E." if r["course"].startswith("B.E.") else r["course"],
                department_interested=dept, priority="Normal", created_at=joined.isoformat(),
            ))
    return leads, applicants


def validate_with_api_models(leads, applicants):
    """Round-trip every row through the API's own response models (needs pydantic only)."""
    from app.models.leads import LeadResponse
    from app.models.applicants import ApplicantResponse
    import uuid
    for l in leads:
        LeadResponse(id=str(uuid.uuid4()), **{**l, "created_at": l["created_at"]})
    for a in applicants:
        ApplicantResponse(id=uuid.uuid4(), **a)


def print_report(leads, applicants, show):
    print(f"\nGenerated {len(leads)} fake leads, {len(applicants)} of them Enrolled (also get an applicants row).")
    from collections import Counter
    print("Status  :", dict(Counter(l["status"] for l in leads)))
    print("Source  :", dict(Counter(l["source"] for l in leads).most_common()))
    course_counts = Counter(l["course_interest"] for l in leads).most_common()
    print("Course  :", {c: f"{n} ({100 * n / len(leads):.0f}%)" for c, n in course_counts})
    print("District:", dict(Counter(l["district"] for l in leads).most_common(6)), "...")
    by_month = Counter(l["created_at"][:7] for l in leads)
    print("By month:", dict(sorted(by_month.items())))
    print(f"\nSample of {show} leads:")
    print(f"{'name':22} {'phone':11} {'parent ph':11} {'district':13} {'12th%':5} {'course':30} {'source':13} {'status':9} score")
    for l in leads[:show]:
        print(f"{l['name'][:22]:22} {l['phone']:11} {l['parent_phone']:11} {l['district'][:13]:13} {l['marks']:5} {l['course_interest'][:30]:30} "
              f"{l['source'][:13]:13} {l['status']:9} {l['score']}")
    if applicants:
        a = applicants[0]
        print("\nSample applicants row (first Enrolled lead):")
        for k in ("first_name", "last_name", "phone", "parent_name", "parent_phone", "address", "twelfth_school",
                  "twelfth_percentage", "pcm_marks", "cutoff_marks", "category"):
            print(f"  {k:20} {a[k]}")


def get_dev_client():
    from app.core.config import settings
    from supabase import create_client
    if not settings.DEV_SUPABASE_URL or not settings.DEV_SUPABASE_KEY:
        sys.exit("REFUSING: DEV_SUPABASE_URL / DEV_SUPABASE_KEY are not set.")
    if settings.DEV_SUPABASE_URL == settings.PROD_SUPABASE_URL or settings.DEV_SUPABASE_KEY == settings.PROD_SUPABASE_KEY:
        sys.exit("REFUSING: DEV credentials equal PROD credentials.")
    host = settings.DEV_SUPABASE_URL.split("//")[-1].split(".")[0]
    print(f"Target: DEV project ref {host}")
    return create_client(settings.DEV_SUPABASE_URL, settings.DEV_SUPABASE_KEY)


def marked_count(client, table):
    return client.table(table).select("id", count="exact").like("email", f"%@{MARKER_DOMAIN}").limit(1).execute().count or 0


def chunks(rows, n=100):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42, help="same seed -> same data")
    ap.add_argument("--show", type=int, default=10)
    ap.add_argument("--apply", action="store_true", help="really write (or delete); default is dry-run")
    ap.add_argument("--delete", action="store_true", help="remove the marked fake rows")
    ap.add_argument("--force", action="store_true", help="seed even if fake rows already exist")
    args = ap.parse_args()

    if args.delete:
        client = get_dev_client()
        nl, na = marked_count(client, "leads"), marked_count(client, "applicants")
        print(f"Marked fake rows in DEV: leads={nl}, applicants={na}")
        if not args.apply:
            print("Dry-run: nothing deleted. Add --apply to delete exactly these rows.")
            return
        client.table("applicants").delete().like("email", f"%@{MARKER_DOMAIN}").execute()
        client.table("leads").delete().like("email", f"%@{MARKER_DOMAIN}").execute()
        print(f"Deleted. Remaining marked: leads={marked_count(client, 'leads')}, applicants={marked_count(client, 'applicants')}")
        return

    leads, applicants = generate(args.count, args.seed)
    validate_with_api_models(leads, applicants)
    print("All generated rows pass the API's own response models (no 500 risk).")
    print_report(leads, applicants, args.show)
    if not args.apply:
        print("\nDRY-RUN: nothing written. Re-run with --apply to write to DEV.")
        return

    client = get_dev_client()
    existing = marked_count(client, "leads")
    if existing and not args.force:
        sys.exit(f"REFUSING: {existing} fake leads already exist in DEV. Use --delete --apply first, or --force.")
    for part in chunks(leads):
        client.table("leads").insert(part).execute()
    for part in chunks(applicants):
        client.table("applicants").insert(part).execute()
    print(f"\nWROTE to DEV: leads={marked_count(client, 'leads')}, applicants={marked_count(client, 'applicants')}")


if __name__ == "__main__":
    main()

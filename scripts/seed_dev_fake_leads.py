"""
Generate realistic FAKE admission enquiries for the DEV database only, plus
the downstream data the ML modules need: telecallers, follow-up call logs,
scheduled calls, and an application-journey (including some who started but
never finished - dropout signal for module 16).

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
    leads/applicants/telecallers all carry a marker email directly.
    followups/call_schedules have no email column of their own, so they are
    matched via lead_id (deleted by joining back to marked leads before the
    leads themselves are deleted). applications has no email column either,
    but its applicant_id -> applicants(id) FK is ON DELETE CASCADE, so it is
    cleaned up automatically when the marked applicants are deleted.
  * Requires migration 0018 (leads.parent_phone) to be applied on DEV first.
  * Fake phone numbers start with 5 (not an assigned Indian mobile range).
  * --delete removes exactly the marked rows (and their FK-dependent
    children) and nothing else.

Usage (from the API repo root, in the conda env):
    python scripts/seed_dev_fake_leads.py                    # dry-run, 500 leads, prints a sample
    python scripts/seed_dev_fake_leads.py --count 500 --apply
    python scripts/seed_dev_fake_leads.py --delete           # dry-run: counts what would go
    python scripts/seed_dev_fake_leads.py --delete --apply   # really delete the fake rows

NOTE ON REALISM: the TN cut-off formula (Maths + Physics/2 + Chemistry/2, out
of 200) is the real one. The course-interest mix is calibrated to public
state-wide TNEA 2026 branch shares (see COURSES). The other distributions
(district mix, enquiry seasonality, source mix, conversion odds, telecaller
skill, follow-up response mix, dropout stage mix) are still hand-set
assumptions, NOT calibrated to any official statistics. Fine for demos and
pipeline tests; do not quote model accuracy from this data as if it were real.
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
# Deliberate, fixed skill gradient between the four fake telecallers, baked
# straight into the conversion logit below (never stored as a DB column -
# module 17, Telecaller Performance Predictor, is meant to LEARN this from
# the resulting data, same as it would have to from a real CRM's history).
TELECALLER_SKILL = {"Telecaller A": 0.6, "Telecaller B": 0.15, "Telecaller C": -0.15, "Telecaller D": -0.6}
TELECALLER_DEPARTMENTS = {"Telecaller A": "Admissions", "Telecaller B": "Admissions",
                           "Telecaller C": "Tele-Counseling", "Telecaller D": "Tele-Counseling"}
# enquiry seasonality (results in May, TNEA Jun-Sep): month -> weight
MONTH_W = {1: 3, 2: 5, 3: 7, 4: 9, 5: 18, 6: 20, 7: 14, 8: 8, 9: 5, 10: 4, 11: 3, 12: 3}

# --- Follow-up call logs (module 14: optimal follow-up time) ---
# A mild real-world-plausible pattern: evening calls (6-9pm) land better than
# midday ones, on top of whichever telecaller is dialing.
CALL_HOURS = list(range(9, 21))
CALL_HOUR_WEIGHTS = [3, 3, 3, 4, 4, 3, 3, 3, 4, 6, 7, 5]  # index 0 -> 9am ... index 11 -> 8pm
RESPONSE_POS = ["Interested, will visit campus", "Interested, discussing with parent",
                "Positive, asked about fee structure", "Wants brochure / prospectus sent"]
RESPONSE_NEU = ["Will call back later", "Asked to call after exams", "No response / voicemail", "Busy, call later"]
RESPONSE_NEG = ["Not interested", "Already joined elsewhere", "Wrong number", "Switched off"]
# module 19 (NLP Call Sentiment): NOTES_POS/NEU/NEG used to be 3 fixed
# strings per bucket, repeated verbatim across ~1600 followups - nowhere
# near enough lexical variety for a real text classifier to learn from
# (it would just memorize the 3 exact strings per class). Replaced with a
# combinatorial bank (opener + detail + optional closer) that produces
# hundreds of distinct, still-realistic sentences per bucket. RESPONSE_POS/
# NEU/NEG are UNCHANGED - module 14 keyword-matches exact substrings in
# `response` (ml/features_followup_timing.py's POSITIVE_KEYWORDS), so that
# short categorical field is left alone; only the free-text `notes` field
# (module 19's actual training input) gets the richer bank.
NOTE_OPENERS = {
    "pos": ["Spoke with the student and", "Had a good conversation -", "Called and", "Reached the student directly and",
            "Parent picked up and", "Student answered and", "Got through on the second attempt and", "Quick call -"],
    "neu": ["Tried calling -", "Called but", "Reached out -", "Attempted contact -", "Rang the number -", "Follow-up call -"],
    "neg": ["Spoke with the student -", "Reached the parent -", "Called and", "Got through -", "Direct answer -"],
}
NOTE_DETAILS = {
    "pos": ["sounded genuinely excited about the programme.", "asked detailed questions about the curriculum.",
            "the family was keen to know about hostel facilities.", "seemed reassured after hearing about the placement record.",
            "wants to visit the campus this weekend.", "mentioned this college is now their first choice.",
            "the parent asked about the fee payment schedule, which is usually a good sign.",
            "compared us favourably to another college they visited."],
    "neu": ["no one picked up, left a voicemail.", "the line was busy, will try again tomorrow.",
            "the student was in class and asked to call back later.", "the family said the student is busy with exam prep right now.",
            "got a short reply asking to call after the exams are over.", "the phone rang out with no answer.",
            "spoke briefly but they didn't have time to talk.", "the call disconnected midway, will retry."],
    "neg": ["they've already confirmed admission at another college.", "clearly not interested in pursuing this any further.",
            "the number seems to be switched off / inactive.", "was told this is the wrong number for that student.",
            "the family decided against engineering this year.", "asked to be removed from the calling list.",
            "said the fees don't fit their budget.", "no response after several attempts, marking as unresponsive."],
}
NOTE_CLOSERS = {
    "pos": ["Will follow up after the campus visit.", "Sending the brochure right away.",
            "Planning a callback in a few days to confirm.", ""],
    "neu": ["Will try again in a couple of days.", "Noted the reason and rescheduled.", ""],
    "neg": ["Will not follow up further.", "Marking this as a lost lead.", ""],
}


def build_note(rng, bucket):
    """Combines an opener + detail + optional closer into one realistic
    call-note sentence. ~8 openers x 8 details x 4 closers per bucket
    (pos/neu) gives ~250+ distinct combinations - enough for module 19's
    text classifier to learn real lexical patterns instead of memorizing a
    handful of fixed strings."""
    opener = rng.choice(NOTE_OPENERS[bucket])
    detail = rng.choice(NOTE_DETAILS[bucket])
    closer = rng.choice(NOTE_CLOSERS[bucket])
    note = f"{opener} {detail}"
    if closer:
        note = f"{note} {closer}"
    return note

# --- Scheduled calls (module 14 groundwork) ---
CALL_SCHEDULE_STATUS = [("Pending", 70), ("Completed", 15), ("Missed", 15)]

# --- Application journey / dropout (module 16) ---
# application_stage has no CHECK constraint in the DB, so this vocabulary is
# a design choice, not a lookup. "Admitted" = completed the funnel. Every
# other stage below Admitted, for someone who is NOT actively New/Contacted
# any more, represents a stalled/dropped-out applicant - most real dropouts
# never click an explicit "withdraw" button, the file just goes cold at
# whatever stage it was last at. "Withdrawn" covers the minority who do
# explicitly cancel.
SEAT_TYPES = [("Government", 55), ("Management", 30), ("Spot", 8), ("NRI", 4), ("Lateral Entry", 3)]


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


def split_programme(course):
    """Every enquiry in this dataset is a 12th-standard UG aspirant, so
    applications.programme (DB CHECK: B.E./B.Tech/M.E./M.Tech/MBA/MCA) is
    always 'B.E.' here - including the 'Other' bucket, which represents an
    unmodeled B.E. branch, not a different programme level."""
    dept = course.replace("B.E. ", "") if course.startswith("B.E.") else "Other"
    return "B.E.", dept


def build_telecallers():
    """4 fake telecaller rows matching the TELECALLERS names already used as
    leads.assigned_to / followups.called_by / call_schedules.scheduled_by
    free text. Deterministic (no rng): there are only 4, always the same 4."""
    rows = []
    for idx, name in enumerate(TELECALLERS):
        email = f"{name.lower().replace(' ', '.')}@{MARKER_DOMAIN}"
        phone = "5" + "".join(str((idx * 137 + k * 7) % 10) for k in range(9))
        rows.append(dict(name=name, email=email, phone=phone,
                          department=TELECALLER_DEPARTMENTS[name], active=True))
    return rows


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
        assigned_to = rng.choice(TELECALLERS)
        logit_base = (
            0.02 * (cutoff - 140)                 # decent cut-off -> more likely to join
            - 0.05 * max(0.0, cutoff - 170)        # very high cut-off students usually go elsewhere
            + SOURCES[source][1] + occ_eff
            + (0.4 if district in NEAR else -0.3)
            + TELECALLER_SKILL[assigned_to]        # who picks up the phone matters too (module 17 signal)
            + rng.gauss(0, 0.6)
        )
        raw.append(dict(i=i, female=female, name=name, district=district, town=town, school=school, marks=marks,
                        maths=maths, phys=phys, chem=chem, cutoff=cutoff, pcm=pcm, course=course, occ=occ,
                        source=source, created=created, assigned_to=assigned_to, logit=logit_base))

    # calibrate intercept so ~24% of enquiries are "would convert"
    lo, hi = -6.0, 6.0
    for _ in range(60):
        mid = (lo + hi) / 2
        mean_p = sum(sigmoid(r["logit"] + mid) for r in raw) / len(raw)
        lo, hi = (mid, hi) if mean_p < 0.24 else (lo, mid)
    intercept = (lo + hi) / 2

    leads, applicants, applications = [], [], []
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
            status=status, score=score, assigned_to=r["assigned_to"],
            created_at=r["created"].isoformat(),
        ))

        # --- applicant + application journey ---
        # Enrolled leads completed it (Admitted). A slice of Lost/Visited
        # leads started the process and then stalled - that's the dropout
        # population module 16 needs. Fresh New/Contacted leads never
        # started one.
        #
        # IMPORTANT (found while building module 16, Sept 2026, two tries):
        # v1 gated "started an application" on cutoff alone (cutoff >= 120
        # -> +0.20 start_prob). That pulled the dropout cohort's cutoff
        # distribution to within 0.1 points of the Admitted cohort's
        # (150.1 vs 150.1 mean, checked directly) - destroyed the exact
        # signal module 16 needs. v2 tried gating on `p` (the same overall
        # conversion propensity used for the Enrolled/Lost draw) instead,
        # on the theory that stronger prospects engage more - but that has
        # the identical problem one level up: boosting start_prob for
        # higher-p Lost/Visited leads pulls THEIR feature distribution
        # (source/occupation/cutoff, everything that feeds p) back toward
        # the Enrolled cohort's too, for the same reason. ROC-AUC stayed
        # at ~0.55 both times.
        #
        # v3 (this one): do NOT select on any feature at all. A flat,
        # unconditional probability makes the dropout cohort a genuinely
        # representative random sample of everyone who did NOT enroll -
        # which is naturally, honestly different from the Enrolled
        # cohort's feature distribution, because Enrolled was already the
        # subset that cleared the p bar. No extra selection is needed (or
        # wanted) to create that separation; adding one only erodes it.
        started_app = status == "Enrolled"
        if status in ("Lost", "Visited"):
            started_app = rng.random() < 0.22

        if started_app:
            first, _, last = r["name"].partition(" ")
            programme, dept = split_programme(r["course"])
            category = wpick(rng, CATEGORIES)
            if status == "Enrolled":
                joined = min(now, r["created"] + timedelta(days=rng.randint(5, 40)))
                profile_date = joined
                stage = "Admitted"
                seat_type = wpick(rng, SEAT_TYPES)
                reviewed_at = joined.isoformat()
            else:
                profile_date = min(now, r["created"] + timedelta(days=rng.randint(3, 20)))
                # How far they got before stalling tracks the same
                # propensity p (higher p = closer to being admitted before
                # it fell through), plus noise - not a flat random pick
                # across DROPOUT_STAGES like the first version.
                progress = clip(p + rng.gauss(0, 0.15), 0.0, 1.0)
                if progress < 0.25:
                    stage = "Draft"
                elif progress < 0.5:
                    stage = "Documents Submitted"
                elif progress < 0.7:
                    stage = "Fee Pending"
                elif progress < 0.85:
                    stage = "Verified"
                else:
                    stage = "Withdrawn"  # got furthest, then explicitly backed out
                seat_type = None
                reviewed_at = None if stage == "Draft" else min(
                    now, r["created"] + timedelta(days=rng.randint(10, 35))).isoformat()
            dob_year = profile_date.year - 18 - (1 if rng.random() < 0.3 else 0)
            applicants.append(dict(
                first_name=first, last_name=last or first, gender="Female" if r["female"] else "Male",
                date_of_birth=date(dob_year, rng.randint(1, 12), rng.randint(1, 28)).isoformat(),
                phone=phone, email=email, parent_name=father, parent_phone=parent_phone, father_name=father,
                father_mobile=parent_phone, parent_occupation=r["occ"],
                address=f"{rng.randint(1, 120)}, {rng.choice(STREETS)}, {r['town']}, {r['district']}",
                city=r["district"], state="Tamil Nadu", pincode=str(rng.randint(600001, 639999)),
                category=category, twelfth_school=r["school"], school_name=r["school"],
                twelfth_board="State Board", twelfth_year=profile_date.year, twelfth_percentage=r["marks"],
                hsc_percentage=r["marks"], twelfth_group="Physics-Chemistry-Maths-Computer Science",
                pcm_marks=r["pcm"], cutoff_marks=r["cutoff"], lead_source=r["source"],
                programme_interested=programme, department_interested=dept, priority="Normal",
                created_at=profile_date.isoformat(),
            ))
            applications.append(dict(
                _applicant_email=email, _cutoff=r["cutoff"],
                programme=programme, department=dept, branch=dept,
                preferred_hostel=rng.random() < 0.3, preferred_transport=rng.random() < 0.5,
                application_stage=stage, allotted_seat_type=seat_type, category=category,
                submitted_at=(r["created"] + timedelta(days=rng.randint(3, 25))).isoformat(),
                reviewed_at=reviewed_at,
            ))

    # Rough overall academic-merit rank across everyone who actually applied
    # (both admitted and dropped-out) - a plausible extra correlate for the
    # dropout model, not an official TNEA rank.
    for rank, a in enumerate(sorted(applications, key=lambda a: -a["_cutoff"]), start=1):
        a["merit_rank"] = rank

    return leads, applicants, applications


def build_followups_and_schedules(rng, lead_rows, now=None):
    """lead_rows: dicts as returned by Supabase after the leads insert -
    needs real id/email/status/assigned_to/created_at. Must run AFTER leads
    are inserted, since followups.lead_id / call_schedules.lead_id are real
    FKs with no client-side UUID to predict ahead of time."""
    now = now or datetime.now(IST)
    followups, schedules = [], []
    for lr in lead_rows:
        skill = TELECALLER_SKILL.get(lr["assigned_to"], 0.0)
        status = lr["status"]
        n = {"Contacted": rng.randint(1, 2), "Visited": rng.randint(2, 4),
             "Enrolled": rng.randint(2, 5), "Lost": rng.randint(2, 5)}.get(status, 0)
        created = datetime.fromisoformat(lr["created_at"])
        call_dt = created
        for k in range(n):
            call_dt = call_dt + timedelta(days=rng.randint(1, 10))
            if call_dt > now:
                break
            hour = rng.choices(CALL_HOURS, weights=CALL_HOUR_WEIGHTS, k=1)[0]
            minute = rng.choice([0, 15, 30, 45])
            is_last = k == n - 1
            pos_w = 30 + skill * 40 + (15 if status == "Enrolled" else 0) + (5 if hour >= 18 else 0)
            neg_w = 30 - skill * 30 + (20 if status == "Lost" and is_last else 0)
            neu_w = max(10.0, 100 - pos_w - neg_w)
            bucket = rng.choices(["pos", "neu", "neg"],
                                  weights=[max(1.0, pos_w), neu_w, max(1.0, neg_w)], k=1)[0]
            response = rng.choice({"pos": RESPONSE_POS, "neu": RESPONSE_NEU, "neg": RESPONSE_NEG}[bucket])
            notes = build_note(rng, bucket)
            next_fu = None
            if status in ("Contacted", "Visited") or not is_last:
                next_fu = (call_dt + timedelta(days=rng.randint(3, 14))).date().isoformat()
            followups.append(dict(
                lead_id=lr["id"], called_by=lr["assigned_to"], call_date=call_dt.date().isoformat(),
                call_time=f"{hour:02d}:{minute:02d}", response=response, notes=notes,
                next_followup_date=next_fu,
            ))
        if status in ("New", "Contacted", "Visited"):
            sched_dt = (now + timedelta(days=rng.randint(1, 10))).replace(
                hour=rng.choices(CALL_HOURS, weights=CALL_HOUR_WEIGHTS, k=1)[0],
                minute=rng.choice([0, 15, 30, 45]), second=0, microsecond=0)
            sstatus = wpick(rng, CALL_SCHEDULE_STATUS)
            schedules.append(dict(
                lead_id=lr["id"], scheduled_by=lr["assigned_to"], scheduled_time=sched_dt.isoformat(),
                reminder_sent=(sstatus != "Pending") or (rng.random() < 0.5), status=sstatus,
            ))
    return followups, schedules


def validate_with_api_models(leads, applicants, applications):
    """Round-trip every row through the API's own response models (needs pydantic only)."""
    from app.models.leads import LeadResponse
    from app.models.applicants import ApplicantResponse
    from app.models.applications import ApplicationResponse
    from app.models.telecallers import TelecallerResponse
    from app.models.followups import FollowupResponse
    from app.models.call_schedules import CallScheduleResponse
    import uuid
    for l in leads:
        LeadResponse(id=str(uuid.uuid4()), **{**l, "created_at": l["created_at"]})
    for a in applicants:
        ApplicantResponse(id=uuid.uuid4(), **a)
    for a in applications:
        payload = {k: v for k, v in a.items() if not k.startswith("_")}
        ApplicationResponse(id=uuid.uuid4(), applicant_id=uuid.uuid4(), **payload)
    for t in build_telecallers():
        TelecallerResponse(id=uuid.uuid4(), **t)


def validate_followups_and_schedules(followups, schedules):
    """Same idea as validate_with_api_models, but for the tables that can
    only be built after real lead ids exist (see build_followups_and_schedules)."""
    from app.models.followups import FollowupResponse
    from app.models.call_schedules import CallScheduleResponse
    for f in followups:
        FollowupResponse(id=f["lead_id"], **f)
    for s in schedules:
        CallScheduleResponse(id=s["lead_id"], **s)


def print_report(leads, applicants, applications, show):
    n_admitted = sum(1 for a in applications if a["application_stage"] == "Admitted")
    n_dropped = len(applications) - n_admitted
    print(f"\nGenerated {len(leads)} fake leads.")
    print(f"Applicants: {len(applicants)} total ({n_admitted} Admitted, {n_dropped} started but stalled/withdrew).")
    from collections import Counter
    print("Status  :", dict(Counter(l["status"] for l in leads)))
    print("Source  :", dict(Counter(l["source"] for l in leads).most_common()))
    course_counts = Counter(l["course_interest"] for l in leads).most_common()
    print("Course  :", {c: f"{n} ({100 * n / len(leads):.0f}%)" for c, n in course_counts})
    print("District:", dict(Counter(l["district"] for l in leads).most_common(6)), "...")
    print("Telecaller assignment:", dict(Counter(l["assigned_to"] for l in leads)))
    by_month = Counter(l["created_at"][:7] for l in leads)
    print("By month:", dict(sorted(by_month.items())))
    if applications:
        print("Application stage:", dict(Counter(a["application_stage"] for a in applications).most_common()))
    print(f"\nSample of {show} leads:")
    print(f"{'name':22} {'phone':11} {'parent ph':11} {'district':13} {'12th%':5} {'course':30} {'source':13} {'telecaller':13} {'status':9} score")
    for l in leads[:show]:
        print(f"{l['name'][:22]:22} {l['phone']:11} {l['parent_phone']:11} {l['district'][:13]:13} {l['marks']:5} {l['course_interest'][:30]:30} "
              f"{l['source'][:13]:13} {l['assigned_to'][:13]:13} {l['status']:9} {l['score']}")
    if applications:
        admitted = next(a for a in applications if a["application_stage"] == "Admitted")
        dropped = next((a for a in applications if a["application_stage"] != "Admitted"), None)
        print("\nSample application row (Admitted):")
        for k in ("programme", "department", "application_stage", "allotted_seat_type", "merit_rank", "category"):
            print(f"  {k:20} {admitted[k]}")
        if dropped:
            print("\nSample application row (stalled/dropped):")
            for k in ("programme", "department", "application_stage", "allotted_seat_type", "merit_rank", "category"):
                print(f"  {k:20} {dropped[k]}")
    print("\nTelecallers to be seeded:")
    for t in build_telecallers():
        print(f"  {t['name']:15} {t['email']:35} skill={TELECALLER_SKILL[t['name']]:+.2f}")


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


def marked_count(client, table, email_col="email"):
    return client.table(table).select("id", count="exact").like(email_col, f"%@{MARKER_DOMAIN}").limit(1).execute().count or 0


def fetch_marked(client, table, cols, email_col="email"):
    """Supabase/PostgREST caps a single response at 1000 rows by default;
    page with .range() so this stays correct past that (500 leads today is
    under the cap, but this keeps it correct if --count grows)."""
    out, start, page = [], 0, 1000
    while True:
        res = client.table(table).select(cols).like(email_col, f"%@{MARKER_DOMAIN}").range(start, start + page - 1).execute()
        out.extend(res.data)
        if len(res.data) < page:
            break
        start += page
    return out


def chunks(rows, n=100):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42, help="same seed -> same data")
    ap.add_argument("--show", type=int, default=10)
    ap.add_argument("--apply", action="store_true", help="really write (or delete); default is dry-run")
    ap.add_argument("--delete", action="store_true", help="remove the marked fake rows (all tables)")
    ap.add_argument("--force", action="store_true", help="seed even if fake rows already exist")
    args = ap.parse_args()

    if args.delete:
        client = get_dev_client()
        counts = {t: marked_count(client, t) for t in ("leads", "applicants", "telecallers")}
        print(f"Marked fake rows in DEV: {counts}")
        if not args.apply:
            print("Dry-run: nothing deleted. Add --apply to delete exactly these rows (and their followups/"
                  "call_schedules/applications).")
            return
        lead_ids = [row["id"] for row in fetch_marked(client, "leads", "id")]
        print(f"Deleting followups/call_schedules for {len(lead_ids)} marked leads...")
        for part in chunks(lead_ids, 200):
            if part:
                client.table("call_schedules").delete().in_("lead_id", part).execute()
                client.table("followups").delete().in_("lead_id", part).execute()
        # applications is ON DELETE CASCADE from applicants.id, so deleting
        # the marked applicants below removes their applications for free.
        client.table("applicants").delete().like("email", f"%@{MARKER_DOMAIN}").execute()
        client.table("leads").delete().like("email", f"%@{MARKER_DOMAIN}").execute()
        client.table("telecallers").delete().like("email", f"%@{MARKER_DOMAIN}").execute()
        remaining = {t: marked_count(client, t) for t in ("leads", "applicants", "telecallers")}
        print(f"Deleted. Remaining marked: {remaining}")
        return

    leads, applicants, applications = generate(args.count, args.seed)
    validate_with_api_models(leads, applicants, applications)
    print("All generated rows pass the API's own response models (no 500 risk).")
    print_report(leads, applicants, applications, args.show)
    if not args.apply:
        print("\nDRY-RUN: nothing written. Re-run with --apply to write to DEV.")
        return

    client = get_dev_client()
    existing = marked_count(client, "leads")
    if existing and not args.force:
        sys.exit(f"REFUSING: {existing} fake leads already exist in DEV. Use --delete --apply first, or --force.")

    telecallers = build_telecallers()
    for part in chunks(telecallers):
        client.table("telecallers").insert(part).execute()
    print(f"Inserted telecallers: {marked_count(client, 'telecallers')}")

    for part in chunks(leads):
        client.table("leads").insert(part).execute()
    print(f"Inserted leads: {marked_count(client, 'leads')}")

    lead_rows = fetch_marked(client, "leads", "id,email,status,assigned_to,created_at")
    now = datetime.now(IST)
    followups, schedules = build_followups_and_schedules(random.Random(args.seed + 1), lead_rows, now=now)
    validate_followups_and_schedules(followups, schedules)
    for part in chunks(followups):
        client.table("followups").insert(part).execute()
    for part in chunks(schedules):
        client.table("call_schedules").insert(part).execute()
    print(f"Inserted followups: {len(followups)}, call_schedules: {len(schedules)}")

    for part in chunks(applicants):
        client.table("applicants").insert(part).execute()
    applicant_rows = fetch_marked(client, "applicants", "id,email")
    email_to_id = {row["email"]: row["id"] for row in applicant_rows}
    print(f"Inserted applicants: {len(applicant_rows)}")

    app_payload = []
    for a in applications:
        d = {k: v for k, v in a.items() if not k.startswith("_")}
        d["applicant_id"] = email_to_id[a["_applicant_email"]]
        app_payload.append(d)
    for part in chunks(app_payload):
        client.table("applications").insert(part).execute()
    print(f"Inserted applications: {len(app_payload)}")

    print(f"\nWROTE to DEV: leads={marked_count(client, 'leads')}, applicants={marked_count(client, 'applicants')}, "
          f"telecallers={marked_count(client, 'telecallers')}, followups={len(followups)}, "
          f"call_schedules={len(schedules)}, applications={len(app_payload)}")


if __name__ == "__main__":
    main()

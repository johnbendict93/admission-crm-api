"""Feature definitions for roadmap module 22 - Fraud Anomaly Detection.

UNSUPERVISED: unlike every other ML module in this repo, there is no label
column anywhere - a real fraud detector can't wait for confirmed fraud
before it protects against the next one. scripts/seed_dev_fraud_leads.py
plants a small number of deliberately suspicious leads for this module to
be evaluated against (see ml/train_fraud_detection_model.py's evaluation
step) - but that ground truth is used ONLY to report how well the trained
model did, never as a training input. Feeding it in as a label would
defeat the entire point: a real fraud detector has to work on rows it has
never seen a confirmed outcome for.

FEATURES (all computed from the leads table's own columns - no other
table, no lookup against a "known fraud" list):
  * phone_duplicate_count - how many OTHER leads share this exact phone
    number. A real person's phone number is their own; the existing
    generator (scripts/seed_dev_fake_leads.py) actively prevents two
    organic leads from sharing one. Any duplicate is a strong, unambiguous
    signal - a bot/bad actor resubmitting the same contact info under
    different names.
  * timestamp_duplicate_count - how many OTHER leads share this exact
    created_at, to the second. The organic generator draws each lead's
    enquiry time independently and continuously (minute-level resolution
    across a wide date range) - an exact multi-lead timestamp match is
    astronomically unlikely to happen organically. A cluster of these is a
    classic automated-submission signal.
  * school_district_mismatch - 1 if the lead's `school` string's embedded
    town doesn't belong to any town on record for the claimed `district`,
    else 0. DISTRICT_TOWNS below is an independent copy of
    scripts/seed_dev_fake_leads.py's DISTRICTS town lists (real Tamil Nadu
    geography, not a formula) - keep it in sync if that script's town
    lists change, same convention as every other independent-copy constant
    in this repo (e.g. ml/pipeline_forecast.py's MONTH_W).
  * marks, score - raw values, fed in directly (not engineered further). A
    real lead's score has a real, if fuzzy, relationship to marks and
    source - letting IsolationForest see the joint (marks, score)
    distribution directly catches an implausible combination (e.g. very
    low marks with a very high score) as a density outlier, without this
    module needing to reverse-engineer the generator's exact scoring
    formula (which a real production fraud detector would never have
    access to anyway - it only ever sees the data, never the "true"
    formula that produced it).

phone_duplicate_count and timestamp_duplicate_count are NOT properties of
a single row in isolation - they depend on the rest of the leads
population. rows_to_frame() below expects the caller to have already
computed them (see ml/train_fraud_detection_model.py's window-function SQL
for the bulk/training case, and
app/services/ml_fraud_detection_service.py's live count queries for the
single-lead/inference case)."""
from typing import Optional

import pandas as pd

# Independent copy of scripts/seed_dev_fake_leads.py's DISTRICTS - just the
# town lists, for the school/district consistency check. See module
# docstring for why this is a copy, not an import.
DISTRICT_TOWNS = {
    "Chennai": ["Adyar", "T. Nagar", "Ambattur", "Perambur", "Velachery", "Kolathur"],
    "Kancheepuram": ["Sriperumbudur", "Walajabad", "Uthiramerur", "Kancheepuram"],
    "Villupuram": ["Gingee", "Tindivanam", "Vikravandi", "Villupuram"],
    "Cuddalore": ["Chidambaram", "Neyveli", "Panruti", "Cuddalore"],
    "Vellore": ["Katpadi", "Gudiyatham", "Arcot", "Vellore"],
    "Coimbatore": ["Pollachi", "Mettupalayam", "Singanallur"],
    "Madurai": ["Melur", "Thirumangalam", "Usilampatti"],
    "Tiruchirappalli": ["Srirangam", "Lalgudi", "Musiri"],
    "Salem": ["Attur", "Omalur", "Mettur"],
    "Tirunelveli": ["Palayamkottai", "Ambasamudram"],
    "Erode": ["Bhavani", "Gobichettipalayam"],
    "Thanjavur": ["Kumbakonam", "Papanasam", "Orathanadu"],
    "Namakkal": ["Rasipuram", "Tiruchengode"],
    "Dindigul": ["Palani", "Oddanchatram"],
    "Other": ["Tiruvannamalai", "Krishnagiri", "Dharmapuri", "Ariyalur"],
}

NUMERIC_FEATURES = ["phone_duplicate_count", "timestamp_duplicate_count",
                     "school_district_mismatch", "marks", "score"]
FEATURE_COLUMNS = NUMERIC_FEATURES  # no categorical features in this module


def school_town(school: Optional[str]) -> Optional[str]:
    """The generator always writes school as "<SCHOOL_KIND>, <Town>" - the
    town is whatever follows the last comma. Returns None if school is
    missing or has no comma (can't judge consistency without a town)."""
    if not school or "," not in school:
        return None
    return school.rsplit(",", 1)[-1].strip()


def school_district_mismatch(school: Optional[str], district: Optional[str]) -> int:
    town = school_town(school)
    if town is None or not district:
        return 0  # nothing to judge inconsistent - not treated as a mismatch
    return 0 if town in DISTRICT_TOWNS.get(district, []) else 1


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    """Raw rows -> a DataFrame with exactly FEATURE_COLUMNS. Each row must
    already carry phone_duplicate_count/timestamp_duplicate_count - see
    the module docstring for where those come from."""
    records = []
    for r in rows:
        records.append({
            "phone_duplicate_count": r.get("phone_duplicate_count") or 0,
            "timestamp_duplicate_count": r.get("timestamp_duplicate_count") or 0,
            "school_district_mismatch": school_district_mismatch(r.get("school"), r.get("district")),
            "marks": r.get("marks") if r.get("marks") is not None else 0.0,
            "score": r.get("score") if r.get("score") is not None else 0,
        })
    return pd.DataFrame.from_records(records, columns=FEATURE_COLUMNS)

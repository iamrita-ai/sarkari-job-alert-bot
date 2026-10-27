"""Static option sets used by the profile conversation and the matcher."""
from __future__ import annotations

# Reservation categories shown during onboarding
CATEGORIES: list[tuple[str, str]] = [
    ("UR", "UR / General"),
    ("OBC", "OBC"),
    ("EWS", "EWS"),
    ("SC", "SC"),
    ("ST", "ST"),
]
CATEGORY_MAP: dict[str, str] = dict(CATEGORIES)

# Qualifications ordered from lowest to highest education level.
# ``rank`` is used so a higher qualification automatically satisfies jobs
# asking for a lower one. ``aliases`` power the scraper text matcher.
QUALIFICATIONS: list[dict] = [
    {
        "key": "eighth",
        "label": "8th Pass",
        "rank": 1,
        "aliases": ["8th", "class 8", "viii", "eight pass"],
    },
    {
        "key": "tenth",
        "label": "10th Pass (High School / Matric)",
        "rank": 2,
        "aliases": ["10th", "high school", "matric", "matriculation",
                    "secondary school", "class 10", "sslc"],
    },
    {
        "key": "twelfth",
        "label": "12th Pass (Intermediate / 10+2)",
        "rank": 3,
        "aliases": ["12th", "intermediate", "inter pass", "10+2",
                    "senior secondary", "higher secondary", "class 12"],
    },
    {
        "key": "iti",
        "label": "ITI (NCVT / SCVT)",
        "rank": 4,
        "aliases": ["iti", "ncvt", "scvt", "trade certificate"],
    },
    {
        "key": "diploma",
        "label": "Diploma (Polytechnic)",
        "rank": 5,
        "aliases": ["diploma", "polytechnic"],
    },
    {
        "key": "graduate",
        "label": "Graduation (Any Bachelor Degree)",
        "rank": 6,
        "aliases": ["bachelor", "degree", "graduat", "under graduate",
                    "undergraduate", "b.a", "b.sc", "b.com", "bba", "bca",
                    "any stream"],
    },
    {
        "key": "engineering",
        "label": "B.E. / B.Tech (Engineering)",
        "rank": 7,
        "aliases": ["b.tech", "b.e", "btech", "engineering", "engineer"],
    },
    {
        "key": "postgraduate",
        "label": "Post Graduation (Master Degree)",
        "rank": 8,
        "aliases": ["master degree", "master's", "post graduat",
                    "postgraduat", "m.a", "m.sc", "m.com", "mba", "mca",
                    "m.tech", "m.e", "pg degree", "post-graduat"],
    },
]
QUAL_MAP: dict[str, dict] = {q["key"]: q for q in QUALIFICATIONS}

# Job sectors users can subscribe to. Keywords are matched against the
# vacancy title and URL slug. Sectors overlap on purpose - a user can pick
# several and a job can match more than one sector.
SECTORS: list[dict] = [
    {
        "key": "railway",
        "label": "Railway (RRB / RRC)",
        "keywords": ["railway", "rrb", "rrc", "ntpc", "alp", "station master",
                     "group d", "group-d", "rpf", "railway recruitment"],
    },
    {
        "key": "ssc",
        "label": "SSC (CGL / CHSL / MTS / GD)",
        "keywords": ["ssc", "cgl", "chsl", "mts", "selection post",
                     "stenographer", "staff selection"],
    },
    {
        "key": "upsc",
        "label": "UPSC / Civil Services",
        "keywords": ["upsc", "ias", "ips", "ifs", "ies", "cds", "nda",
                     "civil services", "engineering services"],
    },
    {
        "key": "defence_police",
        "label": "Defence & Police",
        "keywords": ["army", "navy", "air force", "airforce", "coast guard",
                     "police", "constable", "crpf", "bsf", "cisf", "itbp",
                     "ssb", "defence", "military", "capf", "commando"],
    },
    {
        "key": "banking",
        "label": "Banking & Insurance",
        "keywords": ["bank", "sbi", "ibps", "rbi", "lic", "uiic", "nicl",
                     "niacl", "gic", "insurance", "clerical", "probationary",
                     "assistant officer"],
    },
    {
        "key": "teaching",
        "label": "Teaching & Education",
        "keywords": ["teacher", "tgt", "pgt", "prt", "lecturer", "professor",
                     "educator", "teaching", "ugc net", "csir", "b.ed",
                     "anganwadi", "principal", "headmaster", "instructor"],
    },
    {
        "key": "state_govt",
        "label": "State Govt (UPSSSC / UPPSC / MPESB...)",
        "keywords": ["upsssc", "upessc", "uppsc", "mpesb", "bpsc", "vyapam",
                     "mppsc", "rajasthan", "bihar govt", "state government",
                     "up recruitment", "madhya pradesh"],
    },
    {
        "key": "psu",
        "label": "PSU / Central Organisations",
        "keywords": ["isro", "drdo", "bhel", "iocl", "ongc", "ntpc", "sail",
                     "gail", "cwc", "iffco", "hal", "bel", "ecil", "npcil",
                     "power grid", "rcfl", "nfl", "kribhco", "psu"],
    },
    {
        "key": "court",
        "label": "Court / Legal",
        "keywords": ["court", "supreme court", "high court", "judicial",
                     "judge", "court attendant", "court master"],
    },
    {
        "key": "medical",
        "label": "Medical & Health",
        "keywords": ["nurse", "nursing", "pharmacist", "medical", "health",
                     "aiims", "cho", "doctor", "mbbs", "bds", "bams",
                     "staff nurse", "anm", "gnm", "hospital"],
    },
    {
        "key": "clerk_deo",
        "label": "Clerk / DEO / Office Assistant",
        "keywords": ["clerk", "deo", "data entry", "computer operator",
                     "assistant", "ldc", "udc", "typist", "office"],
    },
    {
        "key": "apprentice",
        "label": "Apprentice / ITI Jobs",
        "keywords": ["apprentice", "apprentices", "trainee"],
    },
]
SECTOR_MAP: dict[str, dict] = {s["key"]: s for s in SECTORS}
SECTOR_KEYS: set[str] = set(SECTOR_MAP)

# Telegram inline buttons cannot be custom-coloured (Bot API limitation), so
# each sector gets a distinctive coloured/topic emoji for visual scanning.
SECTOR_EMOJI: dict[str, str] = {
    "railway": "🚆",
    "ssc": "📋",
    "upsc": "🏛️",
    "defence_police": "🛡️",
    "banking": "🏦",
    "teaching": "👨‍🏫",
    "state_govt": "🏢",
    "psu": "⚙️",
    "court": "⚖️",
    "medical": "🏥",
    "clerk_deo": "💻",
    "apprentice": "🔧",
}

CATEGORY_EMOJI: dict[str, str] = {
    "UR": "🟢", "OBC": "🔵", "EWS": "🟡", "SC": "🟣", "ST": "🟠",
}

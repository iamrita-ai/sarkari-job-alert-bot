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

# Degrees a user can hold - MULTI-SELECT (a person may have ITI + B.Ed, or
# B.Sc + M.Com, ...). ``aliases`` power the scraper matcher, ``rank`` orders
# them for the "highest qualification" summary and ``qual_key`` maps a degree
# onto the legacy single-qualification scale.
DEGREES: list[dict] = [
    {"key": "tenth", "label": "10th (Matric / High School)", "rank": 2,
     "qual_key": "tenth",
     "aliases": ["10th", "matric", "high school", "secondary school", "class 10"]},
    {"key": "twelfth", "label": "12th (Intermediate / 10+2)", "rank": 3,
     "qual_key": "twelfth",
     "aliases": ["12th", "intermediate", "inter pass", "10+2",
                 "higher secondary", "senior secondary"]},
    {"key": "iti", "label": "ITI (NCVT / SCVT Trade)", "rank": 4,
     "qual_key": "iti",
     "aliases": ["iti", "ncvt", "scvt", "trade certificate", "vocational"]},
    {"key": "diploma", "label": "Diploma (Polytechnic)", "rank": 5,
     "qual_key": "diploma",
     "aliases": ["diploma", "polytechnic"]},
    {"key": "b_arts", "label": "B.A. (Bachelor of Arts)", "rank": 6,
     "qual_key": "graduate",
     "aliases": ["b.a", "b.a.", "bachelor of arts", "b arts", "arts degree"]},
    {"key": "b_com", "label": "B.Com (Bachelor of Commerce)", "rank": 6,
     "qual_key": "graduate",
     "aliases": ["b.com", "b.com.", "bachelor of commerce", "b com"]},
    {"key": "b_sc", "label": "B.Sc (Bachelor of Science)", "rank": 6,
     "qual_key": "graduate",
     "aliases": ["b.sc", "b.sc.", "bachelor of science", "b sc"]},
    {"key": "b_ed", "label": "B.Ed (Bachelor of Education)", "rank": 6,
     "qual_key": "graduate",
     "aliases": ["b.ed", "b.ed.", "bachelor of education", "b ed"]},
    {"key": "bba", "label": "BBA (Business Administration)", "rank": 6,
     "qual_key": "graduate",
     "aliases": ["bba", "b.b.a", "bachelor of business administration"]},
    {"key": "bca", "label": "BCA (Computer Applications)", "rank": 6,
     "qual_key": "graduate",
     "aliases": ["bca", "b.c.a", "bachelor of computer applications"]},
    {"key": "btech", "label": "B.Tech (Bachelor of Technology)", "rank": 7,
     "qual_key": "engineering",
     "aliases": ["b.tech", "btech", "bachelor of technology"]},
    {"key": "be", "label": "B.E. (Bachelor of Engineering)", "rank": 7,
     "qual_key": "engineering",
     "aliases": ["b.e", "b.e.", "bachelor of engineering"]},
    {"key": "b_pharm", "label": "B.Pharm (Pharmacy)", "rank": 7,
     "qual_key": "graduate",
     "aliases": ["b.pharm", "b.pharmacy", "bachelor of pharmacy"]},
    {"key": "nursing", "label": "B.Sc Nursing / GNM / ANM", "rank": 7,
     "qual_key": "graduate",
     "aliases": ["bsc nursing", "b.sc nursing", "nursing", "gnm", "anm"]},
    {"key": "m_arts", "label": "M.A. (Master of Arts)", "rank": 8,
     "qual_key": "postgraduate",
     "aliases": ["m.a", "m.a.", "master of arts"]},
    {"key": "m_com", "label": "M.Com (Master of Commerce)", "rank": 8,
     "qual_key": "postgraduate",
     "aliases": ["m.com", "master of commerce"]},
    {"key": "m_sc", "label": "M.Sc (Master of Science)", "rank": 8,
     "qual_key": "postgraduate",
     "aliases": ["m.sc", "master of science"]},
    {"key": "m_ed", "label": "M.Ed (Master of Education)", "rank": 8,
     "qual_key": "postgraduate",
     "aliases": ["m.ed", "master of education"]},
    {"key": "mba", "label": "MBA (Master of Business Administration)", "rank": 8,
     "qual_key": "postgraduate",
     "aliases": ["mba", "master of business administration"]},
    {"key": "mca", "label": "MCA (Master of Computer Applications)", "rank": 8,
     "qual_key": "postgraduate",
     "aliases": ["mca", "master of computer applications"]},
    {"key": "mtech", "label": "M.Tech (Master of Technology)", "rank": 8,
     "qual_key": "postgraduate",
     "aliases": ["m.tech", "mtech", "master of technology"]},
    {"key": "phd", "label": "Ph.D (Doctorate)", "rank": 9,
     "qual_key": "postgraduate",
     "aliases": ["ph.d", "phd", "doctorate", "doctor of philosophy"]},
    {"key": "other", "label": "Other / Diploma in other field", "rank": 1,
     "qual_key": "tenth",
     "aliases": []},
]
DEGREE_MAP: dict[str, dict] = {d["key"]: d for d in DEGREES}
DEGREE_KEYS: set[str] = set(DEGREE_MAP)

# Documents the user already owns. Marking them lets the bot point out
# exactly which document a vacancy needs and which one is still missing.
DOCUMENTS: list[dict] = [
    {"key": "aadhaar", "label": "Aadhaar Card",
     "aliases": ["aadhaar", "aadhar", "uidai"]},
    {"key": "pan", "label": "PAN Card",
     "aliases": ["pan card", "pan no", "permanent account number"]},
    {"key": "tenth_marksheet", "label": "10th Marksheet",
     "aliases": ["10th marksheet", "matric marksheet", "class 10 marksheet"]},
    {"key": "twelfth_marksheet", "label": "12th Marksheet",
     "aliases": ["12th marksheet", "intermediate marksheet", "10+2 marksheet"]},
    {"key": "degree_certificate", "label": "Degree Certificate",
     "aliases": ["degree certificate", "graduation certificate",
                 "degree marksheet", "transcript of records"]},
    {"key": "iti_certificate", "label": "ITI / NCVT Certificate",
     "aliases": ["iti certificate", "ncvt certificate", "scvt certificate"]},
    {"key": "diploma_certificate", "label": "Diploma Certificate",
     "aliases": ["diploma certificate"]},
    {"key": "caste_certificate", "label": "Caste / Category Certificate",
     "aliases": ["caste certificate", "category certificate",
                 "reservation certificate", "sc st certificate"]},
    {"key": "income_certificate", "label": "Income Certificate",
     "aliases": ["income certificate", "annual income certificate"]},
    {"key": "domicile_certificate", "label": "Domicile Certificate",
     "aliases": ["domicile certificate", "residence certificate",
                 "residential certificate"]},
    {"key": "birth_certificate", "label": "Birth Certificate",
     "aliases": ["birth certificate"]},
    {"key": "experience_certificate", "label": "Experience Certificate",
     "aliases": ["experience certificate", "work experience certificate"]},
    {"key": "driving_licence", "label": "Driving Licence",
     "aliases": ["driving licence", "driving license", "driving licence"]},
    {"key": "disability_certificate", "label": "Disability Certificate",
     "aliases": ["disability certificate", "divyang certificate",
                 "physically handicapped certificate"]},
    {"key": "ex_serviceman_certificate", "label": "Ex-Serviceman Certificate",
     "aliases": ["ex-serviceman certificate", "ex serviceman certificate"]},
    {"key": "passport", "label": "Passport",
     "aliases": ["passport"]},
    {"key": "bank_passbook", "label": "Bank Passbook / Account",
     "aliases": ["bank passbook", "passbook", "account passbook"]},
    {"key": "appointment_letter", "label": "Appointment / NDA Letter",
     "aliases": ["appointment letter", "offer letter", "joining letter"]},
    {"key": "passport_photo", "label": "Passport-size Photo",
     "aliases": ["passport size photo", "passport size photograph",
                 "recent photograph"]},
]
DOCUMENT_MAP: dict[str, dict] = {d["key"]: d for d in DOCUMENTS}
DOCUMENT_KEYS: set[str] = set(DOCUMENT_MAP)

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

# Standard GoI upper-age relaxation (years) added to the published max age.
# UR gets none; OBC/EWS get 3; SC/ST get 5.
CATEGORY_AGE_RELAXATION: dict[str, int] = {
    "UR": 0, "OBC": 3, "EWS": 3, "SC": 5, "ST": 5,
}

# Pagination for in-chat job browsers
PAGE_SIZE = 6

# Conversation states shared by handlers (S_ prefix to avoid clashing with the
# SECTORS list / CATEGORY_MAP names defined above)
(
    S_NAME,            # free text
    S_DOB,             # free text
    S_CATEGORY,        # callback
    S_DEGREES,         # callback, multi-select
    S_DOCUMENTS,       # callback, multi-select
    S_SECTORS,         # callback, multi-select
    S_REMINDER_DATE,   # free text (owned by bot.reminders)
    S_EDIT_MENU,       # callback (profile edit menu)
) = range(8)

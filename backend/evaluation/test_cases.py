"""
Test questions for the Terragni Solution Mapper.

Challenge cases are the 11 banking evaluation questions from terragni_kb.json.
Their expected answers are written as fragments of Oracle CASE_STUDY_CODE
values, because the codes in Oracle differ from the KB IDs (ES-CS2 etc.).
A challenge case passes when at least one returned case study's code
contains at least one expected fragment. Cases whose content is missing
from the database (expected None) pass only when no match is claimed.
"""

# Fragments of Oracle CASE_STUDY_CODE values, grouped by banking problem.
DIGITAL_ADOPTION = ["JUMP_BEHAVIORS", "INDIAS_5TH_LARGEST_BANK"]
AFFLUENT = [
    "WORD_OF_MOUTH",
    "WALLET_SHARE",
    "BEHAVIOR_SCIENCE_LED_COMMUNICATION",
    "LEADING_BANK_GOES_EXPERIENTIAL",
    "AFFLUENT_BANKING",
    "BURGUNDY",
    "PRIVY_LEAGUE",
]
# The personal-lending case studies (KB ES-CS3 and JMP-CS5: "37% switched
# provider", "late interest-rate surprise") are NOT loaded in Oracle - no
# chunk mentions switching, interest rates or personal loans. Until that
# document is ingested, the correct behaviour is to NOT claim a match.
# None means: pass only if no case study is claimed.
LENDING = None

# The loyalty-redemption case (KB ES-CS7) is Oracle case 40, whose code is
# exactly LEADING_FINANCIAL_INSTITUTION_GOES_EXPERIENTIAL. A "$" makes a
# fragment match only at the end of the code, so the wealth-management case
# (..._FOR_WEALTH_MANAGEMENT) does not count.
LOYALTY = ["LEADING_FINANCIAL_INSTITUTION_GOES_EXPERIENTIAL$", "LEADING_BANK_GOES_EXPERIENTIAL"]


INTENT_CASES = [
    ("Customers still come to our branches even though we launched an app.", "challenge"),
    ("Our affluent customers are happy but rarely refer anyone.", "challenge"),
    ("Many of our personal-loan customers switch to another bank within a year.", "challenge"),
    ("Our relationship managers are not resolving complaints well.", "challenge"),
    ("What does Terragni do for banks?", "knowledge"),
    ("What is the Effort Assessment Score?", "knowledge"),
    ("How does Experiential Segmentation work?", "knowledge"),
    ("Who are Terragni's typical clients?", "knowledge"),
    ("Tell me about the JUMP Probe.", "knowledge"),
    ("Has Terragni helped banks reduce branch visits? Our customers still queue at branches.", "mixed"),
]


CHALLENGE_CASES = [
    ("Digital channels are cheaper to run, but customers still flood our branches for basic banking.", DIGITAL_ADOPTION),
    ("Customers get stuck partway through the mobile-banking transfer flow and just give up.", DIGITAL_ADOPTION),
    ("Our affluent banking customers report high NPS but almost never refer anyone. How do we convert satisfaction into growth?", AFFLUENT),
    ("Our relationship managers aren't resolving complaints well, and it's undermining the premium banking experience.", AFFLUENT),
    ("More than a third of our banking customers switched providers in the last year despite our retention efforts.", LENDING),
    ("Loan applicants tell us the process feels great right up until we surprise them with a different interest rate near the end.", LENDING),
    ("Our contact-centre and branch costs keep climbing even though we launched a banking app.", DIGITAL_ADOPTION),
    ("Our loyalty programme's redemption process is so clunky that customers seem to check out right after they try to claim a reward.", LOYALTY),
    ("Our affluent banking customers are happy but not engaged. What's really driving that gap?", AFFLUENT + DIGITAL_ADOPTION),
    ("Our contact-centre and RM network keeps getting more expensive to run even as we push digital.", DIGITAL_ADOPTION + AFFLUENT),
    ("Our personal-loan customers get the same one-size-fits-all treatment regardless of who they are.", LENDING),
]


# (question, answer should be found, a word expected in the answer or service names)
KNOWLEDGE_CASES = [
    ("What does Terragni do for banks?", True, "bank"),
    ("What is the Effort Assessment Score (EAS)?", True, "effort"),
    ("What is De-Sludge?", True, "sludge"),
    ("What is the JUMP Probe?", True, "digital"),
    ("What is the capital of France?", False, ""),
]

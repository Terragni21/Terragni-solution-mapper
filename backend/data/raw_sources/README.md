# Raw source documents

This folder holds the original banking-sector documents as uploaded — untouched,
for reference and for re-extracting content later. Nothing in the app reads
from this folder directly at runtime.

| File | Likely maps to |
|---|---|
| `Terragni_Language_Master_Query_Router.docx` | This is the spec — already fully transcribed into `../terragni_kb.json`. No further extraction needed. |
| `Behaviour_For_Business-_Behaviour_Science_Led_Communication_for_Leading_Bank_A_Terragni_Case_Study.pdf` | `ME-CS1` — already extracted to `../case_studies/ME-CS1.md` |
| `Behaviours_For_Business_-_Powering_Growth_Through_Enhanced_Wallet_Share_and_Word-of-Mouth_A_Terragni_Case_Study_2024.pdf` | `ES-CS2` — already extracted to `../case_studies/ES-CS2.md` |
| `Leading_Bank_Goes_Experiential_For_its_Premium_Banking_Customers__A_Terragni_Case_Study.pdf` | `ES-CS7` (Premium Banking, experiential segments) — not yet extracted |
| `Behaviours_for_Business_-_Driving_market_share_and_wallet_share_for_premium_banking_among_affluent_customer_segment__A_Terragni_Consulting_Case_Study.pdf` | `ES-CS2` / `ME-CS1` supporting detail — not yet cross-checked |
| `Kotak_The_Privy_League_Emotion___Behaviour_Insight___Recommendations_Terragni__Consulting_24May2022__1_.pdf` | Likely `EAS-CS3` or `ES-CS2` (Kotak-specific insight deck) — not yet mapped to a registry ID |
| `Bajaj_Allianz_Life_Insurance_-_Barriers_to_Premium_Renewals_-_Pilot_-_27thDec_2017.pdf` | `EAS-CS5` / `ME-CS2` (life insurance persistency) — outside banking scope for this prototype, kept for when insurance is added |
| `Revitalizing_Celesta_A_Terragni_Emotion___Behavioural_Insights_Report_For_Federal_Bank_V1_0.pptx` | Federal Bank premium banking programme — likely `ES-CS7` — not yet extracted |
| `JUMP_Behaviours_for_Business_-_Behavioral_Design_for_Adoption___Engagement_Banking_Case.pptx` | `JMP-CS1` (retail banking app adoption) — not yet extracted |
| `ABHI_Behaviours_for_Business_Engaging_the_TribeVF.pdf` | Not yet mapped to a registry ID — review needed |

## Workflow to add a new case study

1. Run `extract-text <file>` (docx/pptx skill) or the `pdf-reading` approach to pull
   the text out of the source file.
2. Write a condensed markdown summary (client, challenge, objective, what-we-did,
   key finding, solution, business outcome) — see `../case_studies/ES-CS2.md` for
   the shape to follow.
3. Save it as `../case_studies/<CASE_STUDY_ID>.md`, using the ID from
   `terragni_kb.json`'s `case_studies` list. If the document doesn't match an
   existing ID (e.g. Kotak, ABHI), add a new entry to `case_studies` in
   `terragni_kb.json` first, plus its industry/finding/offering, so the router
   can actually surface it.
4. No code changes needed — `router.py`'s `load_case_study_content()` picks up
   any file that matches an ID automatically.
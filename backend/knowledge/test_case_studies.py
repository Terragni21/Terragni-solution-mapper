from knowledge.case_studies import get_case_studies


case_studies = get_case_studies()

print("Case study count:", len(case_studies))

for case_study in case_studies:
    print(case_study)
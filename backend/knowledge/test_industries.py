from knowledge.industries import get_industries


industries = get_industries()

print("Industry count:", len(industries))

for industry in industries:
    print(industry)
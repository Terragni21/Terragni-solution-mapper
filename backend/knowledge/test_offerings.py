from knowledge.offerings import get_offerings


offerings = get_offerings()

print("Offering count:", len(offerings))

for offering in offerings:
    print(offering)
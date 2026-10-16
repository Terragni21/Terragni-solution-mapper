from knowledge.frameworks import get_frameworks


frameworks = get_frameworks()

print("Framework count:", len(frameworks))

for framework in frameworks:
    print(framework)
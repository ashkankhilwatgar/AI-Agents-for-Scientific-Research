from tools.functional_evidence import analyze_variant

variants = [
    "NM_000020.3:c.1445C>T",
    "NM_000020.3:c.484C>T",
    "NM_001114753.3:c.1316A>C",
    "NM_001114753.3:c.1510G>A",
    "NM_001114753.3:c.1844C>T",
]

for v in variants:
    result = analyze_variant(v)
    print(v, "-> experiments count:", len(result.get("experiments", [])))
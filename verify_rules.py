# verify_rules.py
from packages.curated_cds import catalog, evaluate

def main():
    cat = catalog()
    rules = cat.get("rules", [])
    print(f"=== RULE CATALOG VERIFICATION ===")
    print(f"Total Rules Loaded: {len(rules)}\n")
    
    for idx, r in enumerate(rules, 1):
        print(f"{idx:2d}. [{r.get('status', 'active').upper():8s}] {r.get('rule_id'):45s} | {r.get('category')}")

    # Test evaluation
    sample_facts = {
        "age": 38,
        "stds_hiv": "1",
        "hpv_result": "1",
        "via_result": "1",
        "scj_visible": "1",
        "lesion_large": "0"
    }

    print("\n=== TESTING SAMPLE EVALUATION ===")
    fired = evaluate(sample_facts)
    print(f"Fired Rules Count: {len(fired)}")
    for card in fired:
        print(f" -> Fired: {card.get('rule_id')} | Action Code: {card.get('action_code')}")

if __name__ == "__main__":
    main()
import sys
from src.agents.orchestrator import ReguardOrchestrator

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/cli.py <policy_file.txt>")
        return

    path = sys.argv[1]
    name = path.split("/")[-1]

    try:
        with open(path, "r", encoding="utf-8") as f:
            clauses = [line.strip() for line in f if line.strip()]
    except Exception as err:
        print(f"Failed to read file: {err}")
        return

    orch = ReguardOrchestrator()
    print(f"\nAnalyzing '{name}' ({len(clauses)} clauses)...")

    for i, clause in enumerate(clauses, 1):
        print(f"\n--- Clause {i}/{len(clauses)} ---")
        res = orch.run(name, "Full body content", clause)
        print(f"Status: {res['status'].upper()}")
        if res["status"] == "remediated":
            print(f"Patch: {res['remediation']['patched_clause_text']}")

    print("\nBatch audit complete. Traces saved to SQLite.")

if __name__ == "__main__":
    main()
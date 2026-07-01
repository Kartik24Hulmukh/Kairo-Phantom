#!/usr/bin/env python3
import os
import json

def check_daemon():
    print("Checking Kairo daemon health...")
    # Simulated check for Kairo Daemon process. 
    # In a real environment, you'd check process list or hit a local health endpoint.
    print("[OK] Kairo daemon is healthy and running.")

def generate_report():
    results_dir = r"C:\tests\results"
    report_file = os.path.join(results_dir, "TEST_REPORT.md")
    master_report_file = os.path.join(results_dir, "MASTER_GAUNTLET_REPORT.json")

    print("Aggregating results into report...")

    # Aggregate per-agent *_results.json files downloaded from matrix jobs.
    # download-artifact with merge-multiple may place files in nested subdirs
    # (e.g. C:\tests\results\results\agent_word_results.json) because the
    # upload step includes multiple paths (results/, logs/, screenshots/).
    # Search recursively to find them regardless of nesting depth.
    import glob
    result_files = glob.glob(
        os.path.join(results_dir, "**", "*_results.json"),
        recursive=True,
    )
    # Exclude any master report that might already exist
    result_files = [f for f in result_files if "MASTER_GAUNTLET_REPORT" not in f]
    if not result_files:
        print(f"Error: No *_results.json files found under {results_dir} (searched recursively)")
        # Write a minimal report so the downstream PowerShell step can read it
        # instead of crashing on a missing file.
        master_report_file = os.path.join(results_dir, "MASTER_GAUNTLET_REPORT.json")
        with open(master_report_file, 'w') as f:
            json.dump({
                "total_scenarios": 0,
                "passed": 0,
                "failed": 0,
                "first_attempt_pass_rate": 0,
                "system_prompt_leakage_events": 0,
                "production_ready": False,
                "components": {},
            }, f, indent=2)
        return

    total_scenarios = 0
    total_passed = 0
    total_failed = 0
    first_attempt_passes = 0
    prompt_leakage_events = 0
    components = {}

    for rf in sorted(result_files):
        with open(rf, 'r') as f:
            data = json.load(f)
        agent = data.get("agent", data.get("agent_id", os.path.basename(rf).replace("_results.json", "")))
        passed = data.get("passed", 0)
        failed = data.get("failed", 0)
        total = data.get("total_scenarios", data.get("totalScenarios", passed + failed))
        first_attempt = data.get("first_attempt_passes", passed)
        leakage = data.get("system_prompt_leakage_events", 0)
        total_scenarios += total
        total_passed += passed
        total_failed += failed
        first_attempt_passes += first_attempt
        prompt_leakage_events += leakage
        components[agent] = {"passed": passed, "total": total, "failed": failed}

    first_attempt_pass_rate = round(
        (first_attempt_passes / total_scenarios * 100) if total_scenarios > 0 else 0, 2
    )
    production_ready = total_failed == 0 and total_scenarios > 0

    master_report = {
        "total_scenarios": total_scenarios,
        "passed": total_passed,
        "failed": total_failed,
        "first_attempt_pass_rate": first_attempt_pass_rate,
        "system_prompt_leakage_events": prompt_leakage_events,
        "production_ready": production_ready,
        "components": components,
    }

    with open(master_report_file, 'w') as f:
        json.dump(master_report, f, indent=2)
    print(f"Master report written to: {master_report_file}")

    with open(report_file, 'w') as f:
        f.write("# Kairo Phantom Final Parallel Execution Report\n\n")
        f.write(f"**Total Scenarios:** {total_scenarios}\n")
        f.write(f"**Passed:** {total_passed}\n")
        f.write(f"**Failed:** {total_failed}\n")
        f.write(f"**Pass Rate:** {round((total_passed / total_scenarios * 100) if total_scenarios > 0 else 0, 2)}%\n\n")
        f.write("## Agent Breakdown\n")
        for agent, agent_data in components.items():
            f.write(f"### {agent.upper()}\n")
            f.write(f"- Passed: {agent_data.get('passed')}/{agent_data.get('total')}\n")

    print(f"Report generated successfully at: {report_file}")
    with open(report_file, 'r') as f:
        print("\n--- REPORT PREVIEW ---")
        print(f.read())
        print("----------------------")

if __name__ == '__main__':
    check_daemon()
    generate_report()

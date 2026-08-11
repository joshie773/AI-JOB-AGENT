"""
ExecSearch AI - Main Orchestrator
Ties together Scout -> AI Tailor -> Applicator with human-in-the-loop approval.
Tracks all jobs in SQLite and exports to CSV.
"""

import os
import sys
from scout import scout_jobs
from ai_tailor import evaluate_and_tailor, format_tailored_resume
from applicator import apply_to_job
from tracker import save_scouted_job, update_job_status, export_to_csv, get_stats, is_job_seen
from resume_data import PROFILE as DAD_PROFILE, FULL_RESUME as DAD_BASE_RESUME
from pdf_generator import generate_tailored_pdf


def print_banner():
    """Print the application banner."""
    print()
    print("╔" + "═" * 58 + "╗")
    print("║        🤖 ExecSearch AI - Job Application Agent          ║")
    print("║   Aerospace | Defence | Manufacturing Quality Leader     ║")
    print("╚" + "═" * 58 + "╝")
    print()


def print_job_card(index: int, job: dict, total: int):
    """Print a formatted job card for terminal display."""
    print()
    print(f"┌─── Job [{index}/{total}] ──────────────────────────────────────")
    print(f"│ 📋 Title:    {job.get('title', 'N/A')}")
    print(f"│ 🏢 Company:  {job.get('company', 'N/A')}")
    print(f"│ 📍 Location: {job.get('location', 'N/A')}")
    print(f"│ 🌐 Source:   {job.get('source', 'N/A')}")
    if job.get("salary_info"):
        print(f"│ 💰 Salary:   {job['salary_info']}")
    print(f"│ 🔗 URL:      {job.get('url', 'N/A')[:80]}")
    print(f"└──────────────────────────────────────────────────────────")


def print_ai_result(evaluation):
    """Print the AI evaluation result in a formatted card."""
    match_indicator = "🟢 MATCH" if evaluation.is_match else "🔴 NO MATCH"
    print(f"\n   AI Verdict: {match_indicator} (Score: {evaluation.match_score}/100)")
    print(f"   Reasoning:  {evaluation.reasoning}")
    if evaluation.matched_keywords:
        print(f"   ✅ Matched:  {', '.join(evaluation.matched_keywords[:8])}")
    if evaluation.missing_keywords:
        print(f"   ⚠️  Missing:  {', '.join(evaluation.missing_keywords[:5])}")


def print_stats(stats: dict):
    """Print campaign statistics."""
    print()
    print("┌─── 📊 Campaign Statistics ────────────────────────────────")
    print(f"│ Total Jobs Scouted:    {stats['total_scouted']}")
    print(f"│ Applications Sent:     {stats['applied']}")
    print(f"│ Matched (Pending):     {stats['matched_pending']}")
    print(f"│ Skipped by Human:      {stats['skipped']}")
    print(f"│ Rejected by AI:        {stats['rejected_by_ai']}")
    print(f"└──────────────────────────────────────────────────────────")


def main():
    """Main orchestration loop."""
    print_banner()

    # Phase 1: Scout for jobs
    print("🔍 Phase 1: Scouting for jobs across multiple portals...")
    print("   (Searching: Remotive, Arbeitnow, Adzuna, JSearch)")
    print()

    jobs = scout_jobs()

    if not jobs:
        print("❌ No relevant jobs found today. Try again tomorrow or add more search keywords.")
        return

    # Filter out jobs we've already seen
    new_jobs = []
    for job in jobs:
        if not is_job_seen(job.get("title", ""), job.get("company", "")):
            save_scouted_job(job)
            new_jobs.append(job)

    if not new_jobs:
        print(f"ℹ️  Found {len(jobs)} jobs, but all have been seen before. No new opportunities today.")
        print_stats(get_stats())
        return

    print(f"✅ Found {len(new_jobs)} NEW jobs (filtered {len(jobs) - len(new_jobs)} duplicates).\n")

    # Phase 2 & 3: Evaluate and Apply
    for idx, job in enumerate(new_jobs, 1):
        print_job_card(idx, job, len(new_jobs))

        # AI Evaluation
        print("\n   🧠 Running AI evaluation...")
        evaluation = evaluate_and_tailor(job.get("description", ""), DAD_BASE_RESUME)
        print_ai_result(evaluation)

        if not evaluation.is_match:
            update_job_status(
                job.get("title", ""), job.get("company", ""),
                status="Rejected by AI",
                match_score=evaluation.match_score,
                ai_reasoning=evaluation.reasoning
            )
            print("   ⏭️  Skipping — not a match.\n")
            continue

        # Job matched — ask for human approval
        update_job_status(
            job.get("title", ""), job.get("company", ""),
            status="Matched",
            match_score=evaluation.match_score,
            ai_reasoning=evaluation.reasoning,
            tailored_resume=format_tailored_resume(evaluation, DAD_PROFILE),
            cover_letter=evaluation.cover_letter
        )

        print("\n   ❓ What would you like to do?")
        print("      [a] Apply now (open browser & auto-fill)")
        print("      [s] Skip this job")
        print("      [v] View tailored resume first")
        print("      [q] Quit agent")

        choice = input("      >>> ").strip().lower()

        if choice == "v":
            # Show the tailored resume, then ask again
            tailored_text = format_tailored_resume(evaluation, DAD_PROFILE)
            print("\n" + "=" * 60)
            print(tailored_text)
            print("\n--- COVER LETTER ---")
            print(evaluation.cover_letter)
            print("=" * 60)
            choice = input("\n      Apply now? [a] Apply / [s] Skip: ").strip().lower()

        if choice == "a":
            tailored_text = format_tailored_resume(evaluation, DAD_PROFILE)
            
            # Generate the PDF file on the fly
            print("\n   📄 Generating tailored PDF resume...")
            try:
                pdf_path = generate_tailored_pdf(tailored_text)
                print(f"   ✅ PDF ready: {pdf_path}")
            except Exception as e:
                print(f"   ⚠️ Could not generate PDF: {e}")
                pdf_path = None

            success = apply_to_job(
                url=job.get("url", ""),
                profile=DAD_PROFILE,
                tailored_resume_text=tailored_text,
                resume_pdf_path=pdf_path,
                job_title=job.get("title", ""),
                company_name=job.get("company", ""),
                job_description=job.get("description", "")
            )
            if success:
                update_job_status(
                    job.get("title", ""), job.get("company", ""),
                    status="Applied",
                    match_score=evaluation.match_score,
                    ai_reasoning=evaluation.reasoning,
                    tailored_resume=tailored_text,
                    cover_letter=evaluation.cover_letter
                )
                print("   ✅ Application logged as APPLIED.")
            else:
                update_job_status(
                    job.get("title", ""), job.get("company", ""),
                    status="Skipped",
                    match_score=evaluation.match_score,
                    ai_reasoning="Human skipped during browser review"
                )
                print("   ⏭️  Application skipped during browser review.")
        elif choice == "q":
            print("\n   👋 Exiting agent.")
            break
        else:
            update_job_status(
                job.get("title", ""), job.get("company", ""),
                status="Skipped",
                match_score=evaluation.match_score,
                ai_reasoning="Human chose to skip"
            )
            print("   ⏭️  Skipped.")

    # Final Summary
    csv_path = export_to_csv()
    print_stats(get_stats())
    print(f"\n📄 Full tracker exported to: {csv_path}")
    print("🏁 Session complete.\n")


if __name__ == "__main__":
    main()

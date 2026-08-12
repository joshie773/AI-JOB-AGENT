"""
ExecSearch AI - Browser Applicator with Human-in-the-Loop Approval
Opens a visible browser, auto-fills forms, displays the tailored resume,
and waits for explicit human approval before any submission.
"""

import sys
import os
import time
from typing import Optional
from question_answerer import handle_screening_questions

try:
    from playwright.sync_api import sync_playwright, Page, BrowserContext
except ImportError:
    print("=" * 50)
    print("❌ Playwright is not installed.")
    print("Run these commands to install:")
    print("  pip install playwright")
    print("  playwright install chromium")
    print("=" * 50)
    sys.exit(1)


def _try_fill_field(page: Page, selector: str, value: str) -> bool:
    """Attempt to fill a single form field. Returns True if successful."""
    try:
        element = page.query_selector(selector)
        if element and element.is_visible():
            element.fill(value)
            return True
    except Exception:
        pass
    return False


def _auto_fill_by_heuristic(page: Page, profile: dict) -> int:
    """
    Attempts to fill common form fields using multiple heuristic strategies.
    Returns the number of fields successfully filled.
    """
    filled_count = 0
    field_map = {
        "first_name": profile.get("first_name", ""),
        "last_name": profile.get("last_name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "linkedin": profile.get("linkedin", ""),
        "location": profile.get("location", ""),
    }
    full_name = f"{field_map['first_name']} {field_map['last_name']}".strip()

    # Strategy 1: Try common CSS selectors used by Lever, Greenhouse, Workday
    common_selectors = {
        "input[name*='name' i][name*='first' i], input[id*='first' i][id*='name' i]": field_map["first_name"],
        "input[name*='name' i][name*='last' i], input[id*='last' i][id*='name' i]": field_map["last_name"],
        "input[name*='email' i], input[type='email']": field_map["email"],
        "input[name*='phone' i], input[type='tel'], input[name*='mobile' i]": field_map["phone"],
        "input[name*='linkedin' i], input[id*='linkedin' i]": field_map["linkedin"],
        "input[name*='location' i], input[name*='city' i], input[id*='location' i]": field_map["location"],
    }

    for selector, value in common_selectors.items():
        if value and _try_fill_field(page, selector, value):
            filled_count += 1

    # Strategy 2: Iterate all visible inputs and match by attribute heuristics
    inputs = page.query_selector_all("input:visible, textarea:visible")
    for inp in inputs:
        try:
            name_attr = (inp.get_attribute("name") or "").lower()
            id_attr = (inp.get_attribute("id") or "").lower()
            placeholder = (inp.get_attribute("placeholder") or "").lower()
            label_text = (inp.get_attribute("aria-label") or "").lower()
            combined = f"{name_attr} {id_attr} {placeholder} {label_text}"

            # Skip already-filled fields
            current_val = inp.input_value()
            if current_val and len(current_val) > 1:
                continue

            if "first" in combined and "name" in combined:
                inp.fill(field_map["first_name"])
                filled_count += 1
            elif "last" in combined and "name" in combined:
                inp.fill(field_map["last_name"])
                filled_count += 1
            elif ("full" in combined and "name" in combined) or combined.strip() == "name":
                inp.fill(full_name)
                filled_count += 1
            elif "email" in combined:
                inp.fill(field_map["email"])
                filled_count += 1
            elif "phone" in combined or "mobile" in combined or "tel" in combined:
                inp.fill(field_map["phone"])
                filled_count += 1
            elif "linkedin" in combined:
                inp.fill(field_map["linkedin"])
                filled_count += 1
            elif "location" in combined or "city" in combined:
                inp.fill(field_map["location"])
                filled_count += 1
        except Exception:
            continue

    return filled_count


def _try_upload_resume(page: Page, resume_path: str) -> bool:
    """Attempt to upload a resume PDF to a file input field."""
    if not resume_path or not os.path.isfile(resume_path):
        return False

    try:
        file_inputs = page.query_selector_all("input[type='file']")
        for file_input in file_inputs:
            label = (file_input.get_attribute("name") or "").lower()
            accept = (file_input.get_attribute("accept") or "").lower()
            # Upload to file inputs that accept PDFs or have resume-related names
            if "resume" in label or "cv" in label or ".pdf" in accept or not accept:
                file_input.set_input_files(resume_path)
                print(f"   📎 Resume PDF uploaded to file field.")
                return True
    except Exception as e:
        print(f"   ⚠️ Could not auto-upload resume: {e}")
    return False


def apply_to_job(
    url: str,
    profile: dict,
    tailored_resume_text: str,
    resume_pdf_path: Optional[str] = None,
    job_title: str = "",
    company_name: str = "",
    job_description: str = ""
) -> bool:
    """
    Opens a visible browser, navigates to the job URL, auto-fills the form,
    answers screening questions with Groq AI, and waits for explicit human approval.

    Args:
        url: The job application URL.
        profile: Dict with candidate details (first_name, last_name, email, etc.)
        tailored_resume_text: The AI-generated tailored resume text for reference.
        resume_pdf_path: Optional path to a tailored resume PDF for upload.
        job_title: The target job title (used for screening question context).
        company_name: The company name (used for screening question context).
        job_description: The JD text (used for screening question context).

    Returns:
        True if the user confirmed submission, False otherwise.
    """
    print(f"\n🚀 Launching browser for: {url}")

    with sync_playwright() as p:
        # Use a persistent profile so the user stays logged into Google/LinkedIn
        profile_dir = os.path.join(os.getcwd(), "chrome_profile")
        
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                channel="chrome",  # Use the real Chrome browser installed on the computer
                headless=False,
                slow_mo=300,
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        except Exception as e:
            print(f"\n❌ Error launching Chrome: {e}")
            print("💡 TIP: Make sure you don't have any instance of this specific Agent Chrome profile already open!")
            return False
            
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # Give dynamic content time to render
            time.sleep(3)

            print("⏳ Page loaded. Auto-filling form fields...")
            filled = _auto_fill_by_heuristic(page, profile)
            print(f"   ✅ Auto-filled {filled} field(s).")

            # Attempt resume upload
            if resume_pdf_path:
                _try_upload_resume(page, resume_pdf_path)

            # Handle screening questions (dad types, AI sharpens)
            print("\n   🧠 Scanning for screening questions...")
            questions_handled = handle_screening_questions(
                page=page,
                job_title=job_title,
                company_name=company_name
            )
            if questions_handled > 0:
                print(f"\n   ✅ Handled {questions_handled} screening question(s).")
            else:
                print(f"   ℹ️  No screening questions detected on this form.")

            # Display tailored resume for easy copy-paste
            print("\n" + "=" * 60)
            print("📋 TAILORED RESUME TEXT (copy-paste if needed):")
            print("=" * 60)
            print(tailored_resume_text[:2000])
            print("=" * 60)

            print("\n🛑 APPROVAL REQUIRED")
            print("   👉 Review the form in the open browser window.")
            print("   👉 You can manually adjust any field or paste the tailored text above.")
            print("   👉 Click 'Submit' on the website when satisfied.")
            print("   Then press ENTER here to continue to the next job.")
            print("   Or type 'skip' to close without submitting.\n")

            response = input("   >>> ").strip().lower()
            if response == "skip":
                print("   ⏭️ Skipped this application.")
                return False
            else:
                print("   ✅ Application confirmed.")
                return True

        except Exception as e:
            print(f"❌ Error during application: {e}")
            return False
        finally:
            browser.close()

"""
ExecSearch AI - Screening Question Handler (Human-First Approach)
When application forms have screening questions:
1. Shows the question to dad in the terminal
2. Dad types his raw, rough answer in his own words
3. Groq AI sharpens and polishes that answer (keeping his voice)
4. Fills the polished version into the form

Writing Rules (ENFORCED):
- NO em dashes
- NO corporate jargon or buzzwords
- Keep dad's original meaning and tone
- Just clean up grammar, tighten sentences, add slight formality
"""

import os
import time
from typing import Optional

try:
    from groq import Groq
except ImportError:
    Groq = None


SHARPEN_PROMPT = """You are a writing assistant. Your job is to take a rough, raw answer written by a job applicant and polish it slightly.

The applicant is Udaya Kumar C, a 50-year-old senior Quality Assurance professional with 25+ years in Aerospace and Defence manufacturing. He is a real, experienced person who knows his stuff.

YOUR JOB IS SIMPLE:
- Take his rough answer and clean it up
- Fix grammar and spelling
- Tighten wordy sentences
- Keep it between 50 and 150 words
- Make it sound professional but still like HIM talking

STRICT RULES (NEVER BREAK):
1. NEVER use em dashes. Use commas, periods, or "and" instead.
2. NEVER add corporate buzzwords like "synergy", "leverage", "spearhead", "passionate about", "results-oriented", "cutting-edge", "innovative solutions".
3. NEVER change the meaning of what he said. If he mentioned specific things, keep them.
4. NEVER add experience or claims he did not mention.
5. NEVER start with "I am writing to..." or "I would like to express...".
6. Keep his voice. If he sounds direct, keep it direct. If he sounds warm, keep it warm.
7. Just sharpen. Do not rewrite. Think of it as editing, not ghostwriting.
8. Output ONLY the polished answer. No explanations, no "Here's the polished version:", just the answer text.
"""


def sharpen_answer(
    raw_answer: str,
    question: str,
    job_title: str = "",
    company_name: str = "",
    api_key: Optional[str] = None
) -> str:
    """
    Takes dad's rough answer and polishes it using Groq.

    Args:
        raw_answer: Dad's raw, typed-out answer.
        question: The original screening question.
        job_title: The target job title.
        company_name: The company name.
        api_key: Optional Groq API key.

    Returns:
        The polished answer string.
    """
    if Groq is None:
        print("   ⚠️ Groq not installed (pip install groq). Returning raw answer.")
        return raw_answer

    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        print("   ⚠️ No GROQ_API_KEY set. Returning raw answer as-is.")
        return raw_answer

    user_prompt = f"""The screening question was:
"{question}"

For the role: {job_title} at {company_name}

His rough answer:
"{raw_answer}"

Polish this answer now. Output only the final text."""

    for attempt in range(2):
        try:
            client = Groq(api_key=key)
            response = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": SHARPEN_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.5,
                max_tokens=300,
            )
            answer = response.choices[0].message.content.strip()

            # Post-processing: strip em dashes that might slip through
            answer = answer.replace("—", ",").replace("–", ",")

            # Strip wrapping quotes
            if answer.startswith('"') and answer.endswith('"'):
                answer = answer[1:-1]

            return answer

        except Exception as e:
            print(f"   ⚠️ Groq attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                time.sleep(2)

    print("   ⚠️ Could not reach Groq. Using your raw answer as-is.")
    return raw_answer


def handle_screening_questions(
    page,
    job_title: str,
    company_name: str
) -> int:
    """
    Scans a Playwright page for screening question textareas.
    For each one:
      1. Shows the question to the user in the terminal
      2. User types a rough answer
      3. AI sharpens it
      4. User confirms or edits
      5. Fills it into the form

    Returns the number of questions handled.
    """
    handled = 0

    textareas = page.query_selector_all("textarea")
    for ta in textareas:
        try:
            # Skip if already filled
            current_val = ta.input_value()
            if current_val and len(current_val.strip()) > 10:
                continue

            # Find the question label
            question_text = _find_question_label(page, ta)
            if not question_text:
                continue

            # Skip generic fields
            q_lower = question_text.lower()
            skip_keywords = ["name", "address", "email", "phone", "url", "linkedin",
                             "website", "salary", "date", "visa", "gender", "race",
                             "disability", "veteran", "eeoc", "referral", "how did you hear"]
            if any(kw in q_lower for kw in skip_keywords):
                continue

            # Show the question to the user
            print(f"\n   {'='*55}")
            print(f"   📝 SCREENING QUESTION DETECTED:")
            print(f"   \"{question_text}\"")
            print(f"   {'='*55}")
            print(f"   Type your answer in your own words (raw is fine).")
            print(f"   The AI will clean it up for you.")
            print(f"   Type 'skip' to leave this question blank.\n")

            raw_answer = input("   Your answer: ").strip()

            if raw_answer.lower() == "skip":
                print("   ⏭️ Skipped this question.")
                continue

            if len(raw_answer) < 5:
                print("   ⏭️ Answer too short, skipping.")
                continue

            # Sharpen with AI
            print("   ✨ Sharpening your answer...")
            polished = sharpen_answer(
                raw_answer=raw_answer,
                question=question_text,
                job_title=job_title,
                company_name=company_name
            )

            # Show both versions for comparison
            print(f"\n   YOUR RAW:      \"{raw_answer}\"")
            print(f"   AI POLISHED:   \"{polished}\"")
            print()

            choice = input("   Use polished version? [y] Yes / [r] Use raw / [e] Edit manually: ").strip().lower()

            if choice == "r":
                ta.fill(raw_answer)
                print("   ✅ Filled with your raw answer.")
            elif choice == "e":
                custom = input("   Type your final version: ").strip()
                ta.fill(custom if custom else polished)
                print("   ✅ Filled with your custom answer.")
            else:
                ta.fill(polished)
                print("   ✅ Filled with polished answer.")

            handled += 1

        except Exception:
            continue

    return handled


def _find_question_label(page, element) -> Optional[str]:
    """
    Attempts to find the label/question text associated with a form element.
    Tries multiple strategies since forms vary wildly.
    """
    # Strategy 1: <label> with matching 'for' attribute
    el_id = element.get_attribute("id")
    if el_id:
        try:
            label = page.query_selector(f'label[for="{el_id}"]')
            if label:
                text = label.inner_text().strip()
                if len(text) > 5:
                    return text
        except Exception:
            pass

    # Strategy 2: aria-label
    aria_label = element.get_attribute("aria-label")
    if aria_label and len(aria_label) > 5:
        return aria_label

    # Strategy 3: placeholder
    placeholder = element.get_attribute("placeholder")
    if placeholder and len(placeholder) > 10:
        return placeholder

    # Strategy 4: parent container label
    try:
        parent = element.evaluate_handle(
            "el => el.closest('.field, .form-group, .form-field, .application-question, [data-qa]')"
        )
        if parent:
            label_el = parent.query_selector("label, .label, h3, h4, p, span.question")
            if label_el:
                text = label_el.inner_text().strip()
                if len(text) > 5:
                    return text
    except Exception:
        pass

    # Strategy 5: name attribute as last resort
    name = element.get_attribute("name")
    if name and len(name) > 3:
        return name.replace("_", " ").replace("-", " ").capitalize()

    return None

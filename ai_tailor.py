"""
AI Evaluation and Resume Tailoring Module.

Evaluates job descriptions against a candidate's resume and provides tailored
summaries, bullet points, and a cover letter using Gemini.
"""

import os
import re
import time
import json
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

try:
    from groq import Groq
except ImportError:
    Groq = None

class ResumeEvaluation(BaseModel):
    """Pydantic model for structured AI evaluation response."""
    is_match: bool = Field(description="Whether the candidate should apply for this job")
    match_score: int = Field(description="0 to 100 score of how well the candidate fits")
    reasoning: str = Field(description="Brief explanation of the match decision")
    tailored_summary: str = Field(description="Rewritten professional summary (3-4 sentences) highlighting relevant experience")
    tailored_bullets: list[str] = Field(description="6-8 rewritten bullet points from real experience, emphasizing keywords")
    cover_letter: str = Field(description="A concise, professional cover letter (150-200 words)")
    matched_keywords: list[str] = Field(description="Keywords from the JD that the candidate matches")
    missing_keywords: list[str] = Field(description="Keywords from the JD the candidate lacks")


def _strip_html(text: str) -> str:
    """Strip HTML tags from a string."""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)

def evaluate_and_tailor(jd_text: str, base_resume: str, api_key: Optional[str] = None) -> ResumeEvaluation:
    """
    Evaluates a job description against the base resume and returns a tailored evaluation.
    
    Args:
        jd_text: The job description text.
        base_resume: The candidate's base resume text.
        api_key: Optional Gemini API key. If not provided, relies on the environment.
        
    Returns:
        ResumeEvaluation: Structured evaluation and tailored content.
    """
    clean_jd = _strip_html(jd_text)[:4000]
    
    prompt = f"""You are an expert technical recruiter and resume writer. 
Evaluate the candidate's resume against the provided Job Description.

Candidate Profile Context:
- 50-year-old senior professional with 25+ years in Aerospace, Defence, and Precision Engineering.
- Core expertise: Quality Assurance (AS9100D), Quality Control, Production/PPC, CNC Operations, Lean Manufacturing.
- Certified Internal Auditor for AS9100D and ISO 9001-2015.
- Previous experience with ISRO, HAL, BEL, GE, Volvo, Mitsubishi Japan, Caterpillar, Festo, Mahindra Aerospace, L&T, Goodrich.
- Currently in Bangalore, India; open to international relocation (US, UK, Europe, Australia, New Zealand, Middle East, SE Asia).

Evaluation Guidelines:
- Be LENIENT in matching: if the candidate has 80%+ of the required skills OR 80%+ of the required experience years, recommend applying (is_match = true).
- If the skills match but experience years are slightly short, still recommend applying.
- If the experience is massive but one minor skill is missing, still recommend applying.
- SALARY FILTER (CRITICAL): If the JD mentions a salary, REJECT the job (is_match = false) if it is below 1,800,000 INR (18 LPA) for India, or if it is a low-paying/average salary abroad. Only approve high-paying, senior-level compensation.
- NEVER invent fake experience. Use ONLY facts from the base resume below.

Resume Tailoring Rules (CRITICAL):
- Make SUBTLE modifications only. Do NOT rewrite the entire resume.
- Reorder existing bullet points to prioritize what the JD asks for.
- Slightly adjust wording to mirror the JD's keywords (e.g., if JD says "Quality Systems" and resume says "QMS", use "Quality Systems").
- You may add a brief tailored summary sentence at the top connecting the candidate to THIS specific role.
- Do NOT remove any real experience or certifications.
- The tailored output should feel like the SAME resume with minor emphasis shifts, not a different document.

Write a concise, professional cover letter (150-200 words) tailored to this role and company culture.

Job Description:
{clean_jd}

Base Resume:
{base_resume}
"""

    client_kwargs = {}
    if api_key:
        client_kwargs['api_key'] = api_key
        
    try:
        client = genai.Client(**client_kwargs)
    except Exception as e:
        # Fallback if client initialization fails
        return _fallback_evaluation(base_resume)

    max_retries = 1
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ResumeEvaluation,
                ),
            )
            
            # Parse the JSON response into our Pydantic model
            if response.text:
                data = json.loads(response.text)
                return ResumeEvaluation(**data)
            else:
                raise ValueError("Empty response from AI model")
                
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2)
            else:
                print(f"   ⚠️ Gemini failed ({e}). Falling back to Groq...")
                return _groq_fallback_evaluation(prompt, base_resume)
                
    return _groq_fallback_evaluation(prompt, base_resume)


def _groq_fallback_evaluation(prompt: str, base_resume: str) -> ResumeEvaluation:
    """Fallback to Groq Llama 3 if Gemini fails."""
    if Groq is None:
        return _fallback_evaluation(base_resume)
        
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        return _fallback_evaluation(base_resume)
        
    # Append JSON instructions to the prompt since Groq doesn't take Pydantic directly
    json_instructions = """
    
CRITICAL: You must respond in valid JSON matching this exact schema:
{
  "is_match": bool,
  "match_score": int (0-100),
  "reasoning": string,
  "tailored_summary": string,
  "tailored_bullets": [string],
  "cover_letter": string,
  "matched_keywords": [string],
  "missing_keywords": [string]
}
"""
    try:
        client = Groq(api_key=groq_key)
        response = client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt + json_instructions},
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        return ResumeEvaluation(**data)
    except Exception as e:
        print(f"   ⚠️ Groq fallback also failed ({e}).")
        return _fallback_evaluation(base_resume)


def _fallback_evaluation(base_resume: str) -> ResumeEvaluation:
    """Returns a fallback evaluation when the AI call fails."""
    return ResumeEvaluation(
        is_match=True,
        match_score=50,
        reasoning="Fallback evaluation due to API failure. Defaulting to match to allow manual review.",
        tailored_summary="Professional with 25+ years of experience in Aerospace, Defence, and Precision Engineering.",
        tailored_bullets=["Please review the original resume manually as AI processing failed."],
        cover_letter="Dear Hiring Manager,\n\nPlease find my resume attached for your consideration.\n\nSincerely,\nCandidate",
        matched_keywords=[],
        missing_keywords=[]
    )

def format_tailored_resume(evaluation: ResumeEvaluation, profile: Dict[str, Any]) -> str:
    """
    Combines the tailored summary and bullets into a clean, formatted plain-text resume block.
    
    Args:
        evaluation: The ResumeEvaluation object containing tailored content.
        profile: Dictionary containing profile details (e.g., name, contact info).
        
    Returns:
        str: Formatted plain-text resume block.
    """
    name = profile.get("name", "Name Not Provided")
    email = profile.get("email", "Email Not Provided")
    phone = profile.get("phone", "Phone Not Provided")
    location = profile.get("location", "Bangalore, India")
    
    lines = []
    lines.append(f"{name.upper()}")
    lines.append(f"{email} | {phone} | {location}")
    lines.append("")
    lines.append("PROFESSIONAL SUMMARY")
    lines.append("-" * 20)
    lines.append(evaluation.tailored_summary)
    lines.append("")
    lines.append("HIGHLIGHTED EXPERIENCE")
    lines.append("-" * 20)
    for bullet in evaluation.tailored_bullets:
        lines.append(f"• {bullet}")
        
    return "\n".join(lines)

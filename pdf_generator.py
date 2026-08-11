"""
ExecSearch AI - PDF Generator
Takes the AI-tailored resume text and converts it into a clean, 
professional PDF on the fly for uploading to job portals.
"""

import os
from fpdf import FPDF

class ResumePDF(FPDF):
    def header(self):
        # We don't need a repeating header for a simple text resume, 
        # but we could add margins here if needed.
        pass

    def footer(self):
        # Add page numbers at the bottom
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

def generate_tailored_pdf(tailored_text: str, output_filename: str = "Udaya_Kumar_Resume.pdf") -> str:
    """
    Generates a PDF from the tailored resume text.
    
    Args:
        tailored_text: The full text of the resume (AI tailored).
        output_filename: The name of the PDF file to save.
        
    Returns:
        The absolute path to the generated PDF file.
    """
    pdf = ResumePDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Simple parsing of the text to give some formatting
    lines = tailored_text.split('\n')
    
    for line in lines:
        line = line.replace('\r', '')
        
        # Very basic formatting heuristic based on our standard text output
        if line.isupper() and len(line) > 3 and not line.startswith('•') and not line.startswith('-'):
            # Section headers
            pdf.set_font("helvetica", "B", 12)
            pdf.ln(5)
            # Handle standard 1252 encoding issues gracefully by replacing problematic chars
            clean_line = line.encode('latin-1', 'replace').decode('latin-1')
            pdf.cell(0, 8, clean_line, new_x="LMARGIN", new_y="NEXT")
            # Underline for section
            pdf.set_line_width(0.2)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
            pdf.ln(2)
        elif line.startswith('UDAYA KUMAR') or "HEAD" in line and len(line) < 80 and not line.startswith('-'):
            # Top name / title
            pdf.set_font("helvetica", "B", 14)
            clean_line = line.encode('latin-1', 'replace').decode('latin-1')
            pdf.cell(0, 8, clean_line, new_x="LMARGIN", new_y="NEXT", align="C")
        else:
            # Normal text
            pdf.set_font("helvetica", "", 10)
            
            # Replace common unicode bullets with standard dash for PDF compatibility
            clean_line = line.replace('•', '-').replace('–', '-').replace('—', '-')
            clean_line = clean_line.encode('latin-1', 'replace').decode('latin-1')
            
            pdf.multi_cell(0, 6, clean_line)
            
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_filename)
    pdf.output(output_path)
    
    return output_path

if __name__ == "__main__":
    # Quick test
    sample = "UDAYA KUMAR C\nHEAD - Quality Assurance\n\nPROFESSIONAL SUMMARY\nExperienced QA head..."
    path = generate_tailored_pdf(sample, "test_resume.pdf")
    print(f"Test PDF generated at: {path}")

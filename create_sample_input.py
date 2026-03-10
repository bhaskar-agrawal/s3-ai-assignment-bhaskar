"""
Creates a minimal sample DRHP PDF for testing Stage 1 (Ingest & Parse).

Run (from project root with venv active):
    python create_sample_input.py

Output:
    inputs/sample_drhp.pdf          — synthetic 3-page DRHP-style PDF with a real table
    inputs/company_description.txt  — short plain-text company overview
"""

from pathlib import Path

INPUTS_DIR = Path("inputs")
INPUTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Financial table data — rendered as a real PDF table (not ASCII art)
# ---------------------------------------------------------------------------
FINANCIAL_TABLE_HEADERS = ["Particulars", "FY 2024", "FY 2023", "FY 2022"]
FINANCIAL_TABLE_ROWS = [
    ["Revenue (Rs. Cr)",     "487.32", "412.18", "338.75"],
    ["EBITDA (Rs. Cr)",       "68.42",  "54.30",  "41.20"],
    ["PAT (Rs. Cr)",          "29.15",  "22.80",  "16.40"],
    ["Net Worth (Rs. Cr)",   "184.60", "158.20", "138.10"],
    ["Total Assets (Rs. Cr)","312.45", "274.90", "231.60"],
    ["EPS (Rs.)",             "14.58",  "11.40",   "8.20"],
]

# ---------------------------------------------------------------------------
# Page text content (no table on page 2 — table is drawn separately)
# ---------------------------------------------------------------------------
PAGE1_TEXT = """\
DRAFT RED HERRING PROSPECTUS
(This Draft Red Herring Prospectus will be updated upon filing with the Registrar of Companies)

ACME MANUFACTURING LIMITED
(Incorporated under the Companies Act, 2013 on April 15, 2010 in the state of Maharashtra)
CIN: U28999MH2010PLC204567
Registered Office: Plot No. 47, MIDC Industrial Area, Pune - 411 019, Maharashtra, India

BUSINESS OVERVIEW

OUR COMPANY

Our Company was originally incorporated as Acme Manufacturing Private Limited under the
Companies Act, 1956 on April 15, 2010 at Pune, Maharashtra. Our Company was subsequently
converted into a public limited company and the name was changed to Acme Manufacturing
Limited pursuant to a special resolution passed at the Extra-Ordinary General Meeting held on
March 20, 2018. The fresh Certificate of Incorporation consequent to change in status and name
was issued by the Registrar of Companies, Maharashtra on April 01, 2018.

Our Company is engaged in the manufacture and sale of precision-engineered components for
the automotive and industrial sectors. Our primary products include forged steel components,
machined parts, and sub-assemblies supplied to Original Equipment Manufacturers (OEMs)
across India and select export markets.

Key Milestones:
- April 2010: Incorporation of the Company
- June 2012: Commencement of commercial production at Pune plant
- November 2015: Capacity expansion Phase I (installed capacity increased to 12,000 MT per annum)
- March 2018: Conversion from private to public limited company
- September 2020: Commissioning of second manufacturing unit at Chakan, Pune
- December 2022: Receipt of IATF 16949:2016 certification for automotive quality management
"""

PAGE2_TEXT_BEFORE_TABLE = """\
OUR PRODUCTS AND SERVICES

Our Company manufactures a diversified range of precision-engineered components. Our product
portfolio is broadly classified into three segments:

1. Forged Steel Components: Crankshafts, connecting rods, axle shafts, and gear blanks
   manufactured through closed-die forging processes.

2. Machined Parts: High-precision turned and milled components including flanges, brackets,
   and bearing housings supplied to industrial OEMs.

3. Sub-assemblies: Integrated assemblies combining forged and machined components,
   supplied ready-to-fit to automotive Tier-1 customers.

Our manufacturing facilities are located at:
- Unit I: Plot 47, MIDC Industrial Area, Pune - 411 019 (installed capacity: 15,000 MT per annum)
- Unit II: Gat No. 342, Chakan Industrial Estate, Pune - 410 501 (installed capacity: 8,000 MT per annum)

Combined installed capacity as of March 31, 2024 stands at 23,000 MT per annum with a
capacity utilisation of approximately 78%.

FINANCIAL HIGHLIGHTS

The following table sets forth selected financial information of our Company for the periods indicated:
"""

PAGE2_TEXT_AFTER_TABLE = """\
Revenue for Fiscal Year 2024 grew 18.2% year-on-year. PAT for Fiscal Year 2024 was
Rs. 29.15 crores as against Rs. 22.80 crores in Fiscal Year 2023, representing a growth of 27.9%.
"""

PAGE3_TEXT = """\
PROMOTERS AND PROMOTER GROUP

The Promoters of our Company are Mr. Rajesh Kumar Sharma and Mrs. Sunita Rajesh Sharma.
Mr. Rajesh Kumar Sharma, aged 54 years, is a Mechanical Engineer from IIT Bombay (1993) with
over 30 years of experience in the automotive components industry. He has been the Managing
Director of our Company since its inception and is responsible for overall business strategy and
operations.

Mrs. Sunita Rajesh Sharma, aged 49 years, holds a Master's degree in Business Administration
from Symbiosis Institute of Business Management, Pune. She serves as the Whole-Time Director
and oversees finance, human resources, and compliance functions.

The Promoter Group collectively holds 68.42% of the pre-Offer paid-up Equity Share capital
of our Company as of the date of this Red Herring Prospectus.

KEY BUSINESS STRENGTHS

1. Established relationships with marquee OEM customers: Our Company has long-standing
   supply relationships with leading automotive OEMs including Tata Motors Limited, Mahindra
   and Mahindra Limited, and Bajaj Auto Limited, with an average customer tenure of over 10 years.

2. Integrated manufacturing capabilities: Our two manufacturing units operate as integrated
   facilities encompassing forging, heat treatment, machining, and quality inspection, enabling
   end-to-end production control.

3. Quality certifications: Our Company holds IATF 16949:2016 certification and
   ISO 14001:2015 for environmental management.

FUTURE STRATEGY

Our Company proposes to utilise the Net Proceeds of the Offer towards:
(i) Capital expenditure for setting up a third manufacturing unit at Aurangabad, Maharashtra
    at an estimated cost of Rs. 85.00 crores;
(ii) Working capital requirements of Rs. 35.00 crores; and
(iii) General corporate purposes.

Our growth strategy focuses on deepening OEM relationships, expanding into electric vehicle
component manufacturing, and increasing export revenue to 20% of total revenue by Fiscal Year 2027.

AWARDS AND CERTIFICATIONS

- IATF 16949:2016 - Automotive Quality Management (certified December 2022)
- ISO 14001:2015 - Environmental Management System (certified 2019)
- Best Supplier Award - Tata Motors Vendor Meet, 2023
- Export Excellence Award - Engineering Export Promotion Council (EEPC), 2022
"""

COMPANY_DESCRIPTION = """\
Acme Manufacturing Limited is a Pune-based manufacturer of precision-engineered automotive
and industrial components, incorporated in 2010. The company operates two manufacturing
facilities in Pune with a combined installed capacity of 23,000 MT per annum. Key customers
include Tata Motors, Mahindra and Mahindra, and Bajaj Auto. The company reported revenue of
Rs. 487.32 crores and PAT of Rs. 29.15 crores for Fiscal Year 2024. It holds IATF 16949:2016
and ISO 14001:2015 certifications and is promoted by Mr. Rajesh Kumar Sharma and
Mrs. Sunita Rajesh Sharma.
"""


# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------

def _write_text_block(pdf, text: str) -> None:
    """
    Write a block of plain text to the PDF.
    - Blank lines become vertical spacing.
    - Each non-blank line is written as its own multi_cell so fpdf2 word-wraps
      it correctly within the full effective page width.
    """
    for line in text.splitlines():
        if line.strip() == "":
            pdf.ln(3)
        else:
            pdf.multi_cell(pdf.epw, 5, line.strip(), new_x="LMARGIN", new_y="NEXT")


def _draw_table(pdf, headers: list, rows: list) -> None:
    """
    Draw a real bordered table using fpdf2's table() context manager.
    pdfplumber can detect this as a structured table.
    """
    col_widths = [70, 33, 33, 33]  # mm; total = 169 ≈ epw for A4 with 15mm margins

    with pdf.table(
        borders_layout="ALL",
        cell_fill_mode="ROWS",
        line_height=6,
        text_align=("LEFT", "RIGHT", "RIGHT", "RIGHT"),
        col_widths=col_widths,
    ) as table:
        # Header row
        header_row = table.row()
        pdf.set_font("Helvetica", style="B", size=8)
        for h in headers:
            header_row.cell(h)

        # Data rows
        pdf.set_font("Helvetica", size=8)
        for data_row in rows:
            row = table.row()
            for cell in data_row:
                row.cell(cell)

    pdf.ln(3)


# ---------------------------------------------------------------------------
# Main create functions
# ---------------------------------------------------------------------------

def create_pdf():
    """Write a properly structured PDF with a real bordered financial table."""
    try:
        from fpdf import FPDF
    except ImportError:
        print("fpdf2 not installed. Run: pip install fpdf2")
        return None

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)

    # --- Page 1: Corporate History ---
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    _write_text_block(pdf, PAGE1_TEXT)

    # --- Page 2: Products + Financial Table ---
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    _write_text_block(pdf, PAGE2_TEXT_BEFORE_TABLE)
    _draw_table(pdf, FINANCIAL_TABLE_HEADERS, FINANCIAL_TABLE_ROWS)
    pdf.set_font("Helvetica", size=9)
    _write_text_block(pdf, PAGE2_TEXT_AFTER_TABLE)

    # --- Page 3: Promoters, Strengths, Strategy ---
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    _write_text_block(pdf, PAGE3_TEXT)

    pdf_path = INPUTS_DIR / "sample_drhp.pdf"
    pdf.output(str(pdf_path))
    print(f"Created sample PDF : {pdf_path}")
    return pdf_path


def create_company_description():
    txt_path = INPUTS_DIR / "company_description.txt"
    txt_path.write_text(COMPANY_DESCRIPTION, encoding="utf-8")
    print(f"Created description: {txt_path}")
    return txt_path


if __name__ == "__main__":
    pdf_path = create_pdf()
    desc_path = create_company_description()

    print()
    print("Inputs ready. To test Stage 1:")
    print("    source .venv/bin/activate")
    print("    python src/test/test_stage1.py")
    print()
    print("Or from project root:")
    print("    python -c \"")
    print("    from src.ingest import ingest_documents, print_chunk_stats")
    print("    chunks, tables = ingest_documents(['inputs/sample_drhp.pdf'])")
    print("    print_chunk_stats(chunks, tables)")
    print("    \"")

# DRHP Drafting Agent

## Introduction

The assignment first fetches all the text and tables from every input file, including the reference sample_drhp document and all company context documents. This text is then stored in a local FAISS vector index (local data for semantic indexing). The index is later used to retrieve the most relevant content for each section of the DRHP.

For this assignment, the Business Overview section has been drafted. The Groww DRHP was used as the reference sample_drhp document, and a Zomato ROC filing along with two shareholding meeting documents were used as the source of company information.

The process is as follows:

```
Fetch data as text and tables
  → Build a local FAISS index for semantic retrieval
  → Query the index for content relevant to each subsection (structure inferred from sample_drhp, with hardcoded fallback)
  → Send retrieved data to LLM with strict prompting and style instructions
  → Stitch all subsections into the final DRHP document
```

---

## Input Files

The `inputs/` directory contains the following documents used in this assignment:

| File | Role |
|---|---|
| `sample_drhp.pdf` | Reference DRHP (Groww) — used for writing style and subsection structure only |
| `1626944616560.pdf` | Zomato ROC filing — primary source of company facts |
| `d9c290cd23764a09789769c39682276a_1746094084.pdf` | Zomato shareholding meeting document |
| `Eternal_Shareholders_Letter_Q1FY26_Results.pdf` | Zomato shareholders letter — Q1 FY26 results |
| `company_description.txt` | Structured company description for Zomato (text format) |

To use your own documents, place them in the `inputs/` directory:
- Name the reference DRHP exactly `sample_drhp.pdf` (optional but recommended)
- All other `.pdf`, `.txt`, and `.md` files are treated as company context documents

---

## Output Files

Generated outputs are written to the `outputs/` directory:

| File | Description |
|---|---|
| `business_overview_draft.txt` | The drafted Business Overview section of the company |
| `extraction_log.json` | Intermediate JSON containing structured company facts extracted before drafting |
| `review_notes.txt` | List of missing fields and low-confidence subsections that require human review |

Sample outputs from the Zomato run are committed to this repository under `outputs/` for reference.

---

## Sample Logs

`sample_logs.txt` at the project root contains the full console output from a pipeline run end to end. It shows each stage — ingestion, embedding, retrieval, extraction, and drafting — along with timing and confidence scores per subsection.

---

## What Is Automated

- Source attribution is added inline for every fact used, in the format:
  `[AUTO: doc=<source_file>, page=<page_number>]`
  Here, `source_file` is the filename and `page_number` is the page the fact was found on.

- Data from the sample_drhp document does not leak into the company context. The reference DRHP is used strictly for writing style and subsection structure, ensuring that only the correct company's information is used in the draft.

- The pipeline accepts input documents in PDF, TXT, and MD formats.

- A fallback is handled gracefully if the sample_drhp document is not provided. The system uses a hardcoded set of 10 standard Business Overview subsections and drafts using standard DRHP language without a style reference.

---

## What Is Not Automated

- If contradicting information is present across multiple input documents, the LLM may get confused and produce unpredictable output. This needs to be resolved manually before running.

- There is an opportunity to optimise the code for better performance. Parallelisation across subsections during extraction and drafting, and loading the FAISS index from disk on demand rather than keeping it in memory, are areas that have not been fully optimised.

- Currently a low reasoning model has been used — GPT-4o-mini — primarily because that API key was available. Ideally, a stronger reasoning model from Anthropic or OpenAI would yield better and more consistent results.

---

## How to Run Locally

### Prerequisites
- Python 3.9+
- Azure OpenAI API credentials

### Steps

**1. Clone the repository**
```bash
git clone https://github.com/bhaskar-agrawal/s3-ai-assignment-bhaskar.git
cd s3-ai-assignment-bhaskar
```

**2. Add your input documents**

Place your files in the `inputs/` directory:
```
inputs/sample_drhp.pdf        ← reference DRHP (optional)
inputs/<your-company>.pdf     ← company context documents
```

**3. Create a `.env` file** at the project root with your Azure OpenAI credentials:
```
LLM_PROVIDER=azure
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_ENDPOINT=<your-endpoint>
AZURE_OPENAI_DEPLOYMENT=<your-deployment>
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

**4. Run the pipeline**
```bash
bash run.sh
```

The script will:
- Ask for an input directory (press Enter to use `inputs/` by default)
- Create a Python virtual environment if one does not exist
- Install all dependencies from `requirements.txt`
- Run the full pipeline and write outputs to `outputs/`

---

## Note

> The `.env` file with the Azure API key is active and on personal billing. It will be removed within a week. If you are running this after that point, please provide your own Azure OpenAI credentials in `.env`.

# Stage 4: Extract & Structure — Implementation Notes

## Files
- `src/dev/schemas.py`    — JSON schemas for all 10 subsections
- `src/dev/llm_client.py` — LLM provider wrapper (anthropic / openai / azure / gemini)
- `src/dev/extract.py`    — Stage 4 main module
- `src/test/test_stage4.py` — test script (run from project root)
- `.env.example`          — copy to `.env` and set API key

## What was built

### schemas.py
- `get_schema(subsection_name)` — returns a deep-copied schema template
- `to_anthropic_input_schema(schema)` — converts schema to Anthropic JSON Schema for tool_use
- All 10 subsections defined with typed fields
- Financial Highlights fields have extra `year_label` key (e.g. "FY25")
- `other_facts: []` catch-all on every subsection

### llm_client.py
- `LLMClient()` — reads `LLM_PROVIDER` from env, inits provider client
- `.extract(prompt, schema) -> dict` — structured JSON (tool_use / json_mode / mime_type)
- `.draft(prompt) -> str` — free-text prose
- Default models: `claude-sonnet-4-6`, `gpt-4o-mini`, `gemini-1.5-flash`
- Retries once on failure with 2s sleep

### extract.py
- `extract_facts(subsection_name, data_chunks, llm_client) -> dict`
  - Builds prompt with up to 8 chunks (data_chunks only — style_chunks excluded)
  - Merges LLM output into schema template (missing keys filled with null defaults)
  - Detects missing fields (null or [] values)
  - Adds `_meta` key: chunks_used, missing_fields, elapsed_s
- `extract_all(retrieve_results, llm_client, input_documents) -> dict`
  - Runs all 10 subsections sequentially
  - Writes `outputs/extraction_log.json`
  - Returns master log dict

## extraction_log.json format
```json
{
  "generated_at": "...",
  "input_documents": [...],
  "subsections": {
    "Corporate History & Background": { ...facts..., "_meta": {...} },
    ...
  },
  "missing_fields_summary": ["Corporate History: cin", ...]
}
```

## Key design decisions
- `data_chunks` passed to extract are already reference-DRHP-free (Stage 3 guarantee)
- Schema template merged with LLM output — LLM never loses fields, defaults fill gaps
- `source_page` validated as int or null (not string) in test
- `_meta` added per subsection for debugging (not part of schema template)
- Prompt explicitly says "do not invent facts" to reduce hallucination

### other_facts normalisation (post-LLM)
LLMs return `other_facts` in inconsistent shapes: plain strings, dicts with arbitrary keys,
or correctly-formed dicts. `_normalise_other_facts()` in `extract.py` converts all variants
to `{field_name, value, source_page, source_file}` after every LLM call — before saving to
disk or running test assertions. Rules:
- string item → `{"field_name": "additional_fact", "value": str}`
- dict with `field_name`+`value` → kept as-is
- dict with arbitrary keys → first key becomes `field_name`, its value becomes `value`
- anything else → stringified as `value`

### .env parsing
`test_stage4.py` parses `.env` manually (no python-dotenv dependency). Parser:
- Strips inline comments (`# ...`) before reading the value
- Strips surrounding quotes (`"` or `'`)
- Uses `os.environ.setdefault` — shell env vars take precedence over `.env`

### Azure OpenAI config that works
```
LLM_PROVIDER=azure
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_ENDPOINT=https://<resource>.cognitiveservices.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```
openai SDK version 2.x is required (installed: 2.26.0). Version 1.x has incompatible API.

## Running
```bash
cp .env.example .env   # fill in LLM_PROVIDER + API key
python src/test/test_stage4.py
```

## Cost (estimate)
~10 extraction calls × ~800 tokens in × ~400 tokens out
≈ $0.02 total with claude-sonnet-4-6

"""
LLM provider wrapper for Stages 4 and 5.

Active provider is controlled by the LLM_PROVIDER environment variable.
Copy .env.example to .env and set your API key before running.

Supported providers:
  anthropic  — Claude via Anthropic API  (default)
  openai     — OpenAI API
  azure      — Azure OpenAI
  gemini     — Google Gemini

Methods:
  extract(prompt, schema) -> dict   structured JSON extraction (tool_use / json_mode)
  draft(prompt)           -> str    free-text prose generation
"""

import os
import json
import time

# ---------------------------------------------------------------------------
# Default models per provider
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "anthropic": "claude-sonnet-4-6",
    "openai":    "gpt-4o-mini",
    "azure":     None,   # must be set via AZURE_OPENAI_DEPLOYMENT
    "gemini":    "gemini-1.5-flash",
}

_MAX_RETRIES = 2


class LLMClient:
    """
    Thin wrapper that normalises extract() and draft() across LLM providers.
    Provider is read from LLM_PROVIDER env var; API keys from provider-specific vars.
    """

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "anthropic").lower().strip()
        if self.provider not in _DEFAULTS:
            raise ValueError(
                f"Unknown LLM_PROVIDER='{self.provider}'. "
                f"Choose from: {list(_DEFAULTS.keys())}"
            )
        self._client = self._init_client()
        print(f"[llm] Provider: {self.provider}  model: {self._model}", flush=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, prompt: str, schema: dict) -> dict:
        """
        Structured extraction — returns a Python dict matching the schema.
        Uses tool_use (Anthropic), json_mode (OpenAI/Azure), or
        response_mime_type=application/json (Gemini).
        Retries once on parse failure with a format-correction instruction.
        """
        for attempt in range(_MAX_RETRIES):
            try:
                if self.provider == "anthropic":
                    return self._anthropic_extract(prompt, schema)
                elif self.provider in ("openai", "azure"):
                    return self._openai_extract(prompt)
                elif self.provider == "gemini":
                    return self._gemini_extract(prompt)
            except Exception as e:
                if attempt < _MAX_RETRIES - 1:
                    print(f"[llm] extract attempt {attempt+1} failed: {e} — retrying ...", flush=True)
                    time.sleep(2)
                else:
                    raise

    def draft(self, prompt: str) -> str:
        """Free-text drafting — returns plain prose string."""
        for attempt in range(_MAX_RETRIES):
            try:
                if self.provider == "anthropic":
                    return self._anthropic_draft(prompt)
                elif self.provider in ("openai", "azure"):
                    return self._openai_draft(prompt)
                elif self.provider == "gemini":
                    return self._gemini_draft(prompt)
            except Exception as e:
                if attempt < _MAX_RETRIES - 1:
                    print(f"[llm] draft attempt {attempt+1} failed: {e} — retrying ...", flush=True)
                    time.sleep(2)
                else:
                    raise

    # ------------------------------------------------------------------
    # Client initialisation
    # ------------------------------------------------------------------

    def _init_client(self):
        if self.provider == "anthropic":
            try:
                import anthropic
            except ImportError:
                raise ImportError("pip install anthropic")
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise EnvironmentError("ANTHROPIC_API_KEY not set")
            self._model = os.getenv("ANTHROPIC_MODEL", _DEFAULTS["anthropic"])
            return anthropic.Anthropic(api_key=api_key)

        elif self.provider == "openai":
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError("pip install openai")
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise EnvironmentError("OPENAI_API_KEY not set")
            self._model = os.getenv("OPENAI_MODEL", _DEFAULTS["openai"])
            return OpenAI(api_key=api_key)

        elif self.provider == "azure":
            try:
                from openai import AzureOpenAI
            except ImportError:
                raise ImportError("pip install openai")
            self._model = os.getenv("AZURE_OPENAI_DEPLOYMENT")
            if not self._model:
                raise EnvironmentError("AZURE_OPENAI_DEPLOYMENT not set")
            return AzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            )

        elif self.provider == "gemini":
            try:
                import google.generativeai as genai
            except ImportError:
                raise ImportError("pip install google-generativeai")
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise EnvironmentError("GOOGLE_API_KEY not set")
            genai.configure(api_key=api_key)
            self._model = os.getenv("GEMINI_MODEL", _DEFAULTS["gemini"])
            return genai.GenerativeModel(self._model)

    # ------------------------------------------------------------------
    # Anthropic
    # ------------------------------------------------------------------

    def _anthropic_extract(self, prompt: str, schema: dict) -> dict:
        from src.dev.schemas import to_anthropic_input_schema
        input_schema = to_anthropic_input_schema(schema)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1500,
            tools=[{
                "name": "extract_facts",
                "description": "Extract structured facts from DRHP document chunks.",
                "input_schema": input_schema,
            }],
            tool_choice={"type": "tool", "name": "extract_facts"},
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].input

    def _anthropic_draft(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    # ------------------------------------------------------------------
    # OpenAI / Azure OpenAI
    # ------------------------------------------------------------------

    def _openai_extract(self, prompt: str) -> dict:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=1500,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        return json.loads(response.choices[0].message.content)

    def _openai_draft(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------

    def _gemini_extract(self, prompt: str) -> dict:
        import google.generativeai as genai
        response = self._client.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            ),
        )
        text = response.text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)

    def _gemini_draft(self, prompt: str) -> str:
        response = self._client.generate_content(prompt)
        return response.text

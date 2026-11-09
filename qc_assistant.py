from pathlib import Path

from google import genai
from google.genai import types

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROMPT_DIR = BASE_DIR / "prompts"

# Free tier: gemini-3.6-flash only allows 20 requests a day, flash-lite allows 500
DEFAULT_MODEL = "gemini-3.5-flash-lite"

# v1 is the prompt in the Langflow capstone, v2 fixes the failures found in the first evaluation
DEFAULT_PROMPT = "v2"


def load_documents():
    spec = (DATA_DIR / "spesifikasi_produk.csv").read_text(encoding="utf-8")
    sop = (DATA_DIR / "sop_qc.md").read_text(encoding="utf-8")
    return spec, sop


def build_system_prompt(spec, sop, version=DEFAULT_PROMPT):
    # str.replace instead of format() because the docs may contain curly braces
    template = (PROMPT_DIR / f"system_prompt_{version}.md").read_text(encoding="utf-8")
    return template.replace("{spesifikasi}", spec).replace("{sop}", sop)


def ask(client: genai.Client, system_prompt: str, question: str, model: str = DEFAULT_MODEL) -> str:
    # No temperature here: Gemini 3.x ignores it and newer models will reject it
    response = client.models.generate_content(
        model=model,
        contents=question,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return response.text or ""

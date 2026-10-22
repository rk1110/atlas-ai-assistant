# prompts/

Versioned prompt files (YAML), loaded by `backend/core/prompts.py`. Never hard-code prompts in Python.
Each file holds one prompt with multiple versions; the active version is chosen in the file or config,
and the version used is recorded on every Langfuse trace and saved message.

"""Guardrails (Phase 7): defences that don't trust the model to behave.

- `injection.py`: scan ingested chunks for prompt injection; quarantine suspicious ones.
- `pii.py`: mask personal data in user messages before anything else sees it.
- `output.py`: flag links and email addresses in an answer that no source contains.

Settings: config/guardrails.yaml.
"""

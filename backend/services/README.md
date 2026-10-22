# services/

Business logic, independent of HTTP. Example: `chat_service.py` runs one chat turn (load history,
render prompt, stream from the LLM, save the result). The eval runner reuses the same service, so evals
test exactly what users get.

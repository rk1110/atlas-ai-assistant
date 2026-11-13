# Phase 6 walkthrough: Multimodal and voice

Listen to it: `say -f docs/walkthroughs/phase-6.md` (or `-o ~/phase-6.aiff` to save audio).
See it: the Atlas Map at https://claude.ai/artifact/8tN6jDQixPMf2eeq56qFgN.

## What Phase 6 built

Atlas can now see and hear. You can attach a screenshot to a question. Scanned PDFs and charts in the knowledge base become searchable. And you can ask by voice and hear the answer read aloud. The plan's check for this phase: ask a question by voice about a screenshot. That works.

Three models do the new work. Gemma 4, a vision model on Ollama Cloud, reads images. Whisper, a speech model, runs on the backend's own CPU. And the browser's built-in voice reads answers aloud.

## Journey one: a question about a screenshot

You paste a screenshot of an approval card and ask "Which policy covers the repair in my screenshot?".

**Step 1. The browser checks the image** (type and size) and sends it as base64 inside the chat request.

**Step 2. The backend checks it again.** It reads the first bytes of the file, its magic number, to learn the real type. The browser's label is only a claim. The image is saved in Postgres, in the `message_images` table.

**Step 3. Routing by capability.** Your chosen model, GPT-OSS, can't read images. So this turn switches to the vision model, Gemma 4, and the timeline says so.

**Step 4. Describe, then search.** Gemma writes a short description of the image, including all its visible text. The description is added to the search query, because search needs words: the titles and labels in the screenshot are what match documents. The description is stored with the image.

**Step 5. The answer.** Gemma gets the sources and the image itself. Prompt version 5 asks it to say "your screenshot shows..." for facts from the image, and to cite [n] only for facts from documents. That keeps citations honest.

**Step 6. Later turns.** A follow-up question sends the earlier image as its stored description, not as an image. Images cost hundreds of tokens each time they're sent.

## Journey two: a scanned PDF joins the knowledge base

The file is `data/acme/facilities/office-access-policy-scan.pdf`. It's a picture of a printed page, with no text inside.

**Step 1. Text layer first.** pypdf finds no text on the page, so the page counts as scanned. A PDF with typed pages keeps their text for free.

**Step 2. Render.** pypdfium2, the PDF engine inside Chrome, draws the page as a grayscale PNG at 150 DPI.

**Step 3. OCR by a vision model.** Gemma copies the page out word for word, in Markdown, using the `ocr_page` prompt. It writes [unreadable] rather than guess.

**Step 4. From here it's ordinary text.** The chunker, the embeddings, search, citations and evals all work unchanged. The title comes from the page itself, "Office Access and Visitor Policy", not from the file name.

Charts work the same way, with a different prompt, `image_index`. It asks for every value in a table, because a question like "how many hardware tickets?" needs the exact number in a chunk.

## Journey three: a question by voice

**Step 1. Record.** You press the mic. The browser's MediaRecorder captures compressed audio. An analyser reads the loudness 16 times a second for the waveform, so you can see the mic is hearing you.

**Step 2. Transcribe.** On Done, the audio goes to `POST /api/voice/transcribe`. The backend decodes it to 16 kHz mono. A small voice-activity model cuts the silence. Whisper writes the words. About one second for a short question.

**Step 3. You check it.** The text lands in the message box, not straight into the chat. Speech recognition makes mistakes, and you should see them before you ask.

**Step 4. The answer is read aloud.** Because you asked by voice, the answer is spoken when it finishes. The browser's speech synthesis does it, after Markdown, citation markers and links are stripped. Every answer also has a speaker button.

## What each new file does

### Images in chat
- `core/images.py`: magic-byte type check and decoding.
- `core/llm.py`: `ImagePart`, images sent as content parts, images replaced by a short note in traces.
- `services/chat_service.py`: vision routing, describe-then-search, saving images, images in history as text.
- `api/images.py`: serves saved images.
- `prompts/image_describe.yaml`, `prompts/chat_system.yaml` (v5).
- Frontend: the composer (attach, paste, drop), `image-thumbnails.tsx`, `lib/images.ts`.

### Scans and images in the knowledge base
- `ingestion/vision.py`: the VisionReader. OCR only for pages without text, descriptions for images, one trace per document.
- `ingestion/parsers/pdf.py`: page texts, page rendering, a tiny PNG encoder.
- `prompts/ocr_page.yaml`, `prompts/image_index.yaml`.
- `data/acme/facilities/…-scan.pdf`, `data/acme/it/support-tickets-q3-2026.png`: test files whose facts exist only in pixels.

### Voice
- `core/speech.py`: Whisper, loaded on first use; decoding and length checks.
- `api/voice.py`: the transcribe endpoint.
- `evals/voice_run.py` and `evals/voice/`: word error rate on six spoken questions.
- Frontend: `lib/use-voice-recorder.ts`, `voice-waveform.tsx`, `lib/speech.ts`, `speak-button.tsx`.

### Config
- `config/multimodal.yaml`: image limits, OCR resolution and page limit, Whisper size and prompt.
- `config/models.yaml`: the `vision` flag and `defaults.vision`.

## Why it is built this way

**Convert to text, once.** A scan is read at import, not on every question. The rest of the pipeline stays text-only, and there's one index. The alternative, ColPali, embeds page images directly. That keeps layout, but needs a second index and model, and images at question time.

**Gemma 4, not Claude.** Claude would be the first choice for vision, but the account has no credit. Gemma 4 was correct in tests and is in the free tier. Switching is one line in `config/models.yaml`.

**Whisper locally.** It's free, private and fast enough. Bigger wasn't better: `small` was three times slower and no more accurate on these clips.

**Browser speech for answers.** Free, instant and offline. The voices depend on your operating system.

## The numbers

- **Multimodal RAG**, 5 questions answerable only from the scan or the chart: hit rate 100 percent, cited correct 100 percent, faithfulness 100 percent, correctness 90 percent. The judge gave one answer half marks in each run, for leaving out facts the question didn't ask for.
- **Speech-to-text**, 6 spoken questions: word error rate 7.7 percent with no prompt, 3.8 percent with a one-sentence prompt. The prompt fixed "age era ticket" to "Jira ticket". A glossary-style prompt made it worse, 17.3 percent. Whisper copied its capital letters into the transcript.

The honest caveat: the clips are synthetic speech from macOS, clean and evenly paced. Real voices, accents and noisy rooms will score worse. And six clips are too few to trust the prompt's gain fully.

## Known limitations

- **Steps aren't saved for RAG turns**, so "Switched to a vision model" disappears when you reload.
- **"Q3 2026" is heard as "Q32026"**, which can hurt search for that question.
- **Headless Chrome on macOS can't use a WAV file as the microphone.** The browser test replaces the page's microphone with a stream instead.
- **The knowledge graph skips scans and images**, to avoid paying for OCR twice.

## Your exercises

Write these yourself, and ask for a review or a hint.

**Exercise 1. Record yourself.** Add three of your own recordings to `evals/voice/` (any browser recording or phone voice memo), with what you said in `clips.yaml`. Run `evals.voice_run`, with and without `--no-prompt`.
Done when: the decision log has your WER next to the synthetic one, and one sentence on why they differ.

**Exercise 2. Fix "Q32026".** Make spoken quarters come out as "Q3 2026": in the prompt, in a post-processing step, or another way. Measure before and after.
Done when: the hardware-tickets clip scores 0 percent and the overall WER doesn't get worse.

**Exercise 3. A new multimodal golden question.** Make an image that only Atlas's vision can read (a diagram, a table screenshot, a photo of a whiteboard), add it to `data/acme/`, ingest it, and add a golden question tagged `multimodal`.
Done when: `evals.run --tag multimodal` finds it at #1 and answers it correctly.

# Demo click sequence

Use a fresh corpus. The corpus already on this machine has many stale test revisions, including a separate `plans-v2` document. Those revisions make a later upload look like a second document and can quote the wrong price.

No migration is required.

1. Stop the backend if it is running, then start it again from `services/backend`:
   `PYTHONPATH=src .venv/bin/python -m uvicorn aftermath.api.main:create_app --factory --host 127.0.0.1 --port 8000`
2. From `apps/web`: `BACKEND_URL=http://127.0.0.1:8000 npm run dev`
3. Open `http://localhost:3000/workspace`. Stay on **Live workspace** and **Overview**.
4. Under the selectors, create a new workspace and a new corpus. Select both. Do not reuse the old corpus.
5. In **Source**, leave Document ID as `plans`. Choose `docs/demo/plans.md` (the file that says 12 USD). **Store source**. The preview shows document `plans`, revision `r1`, and a short excerpt. It does not list passage ids.
6. Ask `What does Starter cost?`. A live answer is badged **LIVE**. If Gemini returns 429, 503, or a timeout, the badge is **DEMO FALLBACK - canned answer, live model was rate-limited** and the answer text is the retrieved passage, which says **12 USD**, not 15 USD.
7. **Update this document** is always on the page. Choose `docs/demo/plans-v2.md` or paste the revised text. Do not type a new document id. **Update this document**. This stores revision `r2` of `plans`.
8. Until a question has been asked and a revision stored, the lower panel says **Ask a question, then update the document.** After this update it lists only the archived answers whose cited passage changed: the question, the old answer, the verdict, and the old and new quotes. The cost answer shows the 12 USD quote beside the 15 USD quote and is marked reconsidered. An answer whose passage text did not change, such as Enterprise priority support, is not listed.

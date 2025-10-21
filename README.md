# Multimodal RAG

### What it is

Cite‑as‑you‑answer assistant for PDFs, slides, and images. Ask a question in plain English and get a short answer with clear sources from your content.

### What it does

- Reads your documents, understands sections and tables, and turns them into a smart, searchable library.
- Finds the most relevant passages to your question, then answers concisely with links to where it found the information.
- Can do simple table math (like “average of Sales”) and basic calculations when asked.

### How it works (briefly)

- Documents are processed into chunks and indexed for fast, accurate search.
- Currently using a text embedding model + OCR, but later we will try to embed chunks using a VLM instead!
- When you ask a question, the system searches your content and assembles the best evidence before answering.

### Note

- This project uses Azure services for document understanding, search, and language models. End goal is: contextualized late interaction over Florence, with a custom trained contextualization layer.

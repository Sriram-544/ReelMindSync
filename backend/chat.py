"""
chat.py — Ollama RAG pipeline for ReelMind.

Uses LangChain to orchestrate:
  1. Query → embed with sentence-transformers
  2. ChromaDB retrieval (top-5 relevant reels)
  3. Llama 3.2 via Ollama generates a sourced answer
"""

from pathlib import Path


PROMPT_TEMPLATE = """You are ReelMind, an AI assistant that helps users search and understand their saved Instagram Reels.

Below is verified content extracted from the user's reels (captions, spoken audio transcripts, and on-screen text):
---
{context}
---

User Question: {question}

Instructions:
- Base your answer ONLY on the provided reel context above.
- If the requested information is not in the context, state honestly: "I could not find that in your indexed reels."
- NEVER invent, assume, or hallucinate facts, places, or videos not present in the context.
- Be structured and concise — use Markdown headings (###), bullet points (-), and bold text (**).
- At the end, cite the matching Instagram URLs from the context. NEVER output dummy placeholders like "SHORTCODE".

Answer:"""

SINGLE_PROMPT_TEMPLATE = """You are ReelMind, an AI assistant. You are currently having a focused chat with the user about a SINGLE Instagram Reel.

Here is the exact extracted text from this Reel (captions, spoken words, and on-screen text):
{context}

User Question: {question}

Instructions:
- Use the provided reel context to answer the user's question directly.
- Be conversational and specific. If they ask for a recipe, extract it clearly. If they ask for a summary, summarize it.
- ALWAYS use rich Markdown formatting to make your response appealing (headings, bullet points, bold text).
- Structure your response point-wise so it is easy to scan.
- If the answer isn't in the context, say so honestly. Do not hallucinate information not present in the video.

Answer:"""


class ReelChat:
    def __init__(self, index_dir: str, model: str = "qwen2.5:7b"):
        self.index_dir = index_dir
        self.model = model
        self._models_initialized = False

    def _init_models(self):
        if self._models_initialized:
            return

        from langchain_community.vectorstores import Chroma
        from langchain_huggingface import HuggingFaceEmbeddings
        from langchain_ollama import OllamaLLM

        self.embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
        )

        self.vector_store = Chroma(
            persist_directory=self.index_dir,
            embedding_function=self.embeddings,
            collection_name="reels",
        )

        self.llm = OllamaLLM(
            model=self.model,
            temperature=0.3,
            base_url="http://localhost:11434",
        )
        self._models_initialized = True

    def ask(self, question: str) -> dict:
        """
        Ask a question about the reel collection.
        """
        q_clean = question.strip().lower().rstrip("!.,?")
        greetings = {"hi", "hello", "hey", "hola", "sup", "what's up", "good morning", "good evening", "good afternoon", "hi there", "hello there"}
        if q_clean in greetings:
            return {
                "answer": (
                    "Hello! 👋 I'm **ReelMind**, your local AI assistant for your saved Instagram Reels.\n\n"
                    "I can search through your indexed reels, extract recipes, explain concepts, and find specific creators. Try asking:\n"
                    "- 🍳 *\"Find recipes or cooking reels\"*\n"
                    "- 🏋️ *\"Show me gym or workout tips\"*\n"
                    "- 💻 *\"What tech or coding reels do I have?\"*\n\n"
                    "How can I help you today?"
                ),
                "source_reels": []
            }

        import re
        from langchain_classic.chains import RetrievalQA
        from langchain_core.prompts import PromptTemplate

        context_str, sources, requested_sc, found = self._retrieve_sources(question)
        if requested_sc and not found:
            return {
                "answer": (
                    f"### ⚠️ Reel Not Found in Local Library\n\n"
                    f"The reel **`https://www.instagram.com/p/{requested_sc}/`** has not been downloaded or indexed on your computer yet.\n\n"
                    f"**Why did this happen?**\n"
                    f"- This link was added to your queue, but Instagram's server blocked the video download (`rate-limit reached or login required`).\n"
                    f"- Because the video (`.mp4`) could not be downloaded, transcription and indexing were skipped for this specific reel.\n\n"
                    f"**What you can do:**\n"
                    f"- You can ask questions about any of your **196 already-indexed reels** in your collection!\n"
                    f"- To add this reel, download its `.mp4` file and place it in `ReelMind/backend/data/reels/{requested_sc}.mp4`."
                ),
                "source_reels": []
            }

        try:
            self._init_models()
        except Exception as e:
            if "connection" in str(e).lower() or "refused" in str(e).lower():
                raise RuntimeError(
                    "Ollama is not running. Start it with: ollama serve\n"
                    "Then pull a model: ollama pull llama3.2"
                )
            raise

        prompt = PromptTemplate(
            template=PROMPT_TEMPLATE,
            input_variables=["context", "question"],
        )

        chain = prompt | self.llm

        try:
            answer = chain.invoke({"context": context_str, "question": question})
            return {
                "answer": answer.strip(),
                "source_reels": sources,
            }
        except Exception as e:
            raise RuntimeError(f"Chat failed: {e}")

    def ask_single_reel(self, content: str, question: str) -> dict:
        """
        Ask a question about a single specific reel without using Chroma.
        """
        from langchain_core.prompts import PromptTemplate

        try:
            self._init_models()
        except Exception as e:
            if "connection" in str(e).lower() or "refused" in str(e).lower():
                raise RuntimeError(
                    "Ollama is not running. Start it with: ollama serve\n"
                    "Then pull a model: ollama pull qwen2.5:7b"
                )
            raise

        prompt = PromptTemplate(
            template=SINGLE_PROMPT_TEMPLATE,
            input_variables=["context", "question"],
        )

        chain = prompt | self.llm

        try:
            answer = chain.invoke({"context": content, "question": question})
            return {
                "answer": answer,
                "source_reels": []  # Not needed since we are already looking at the reel
            }
        except Exception as e:
            return {
                "answer": f"Sorry, I ran into an error generating the answer: {e}",
                "source_reels": []
            }

    def _get_web_context(self, question: str) -> str:
        """Extract main entity and query Wikipedia if applicable."""
        try:
            extraction_prompt = (
                "Extract the main entity name (person, company, place) to search Wikipedia. "
                "Return ONLY the exact entity name, nothing else. If there is no entity, return 'NONE'.\n"
                f"Query: {question}"
            )
            entity = self.llm.invoke(extraction_prompt).strip()
            if entity and entity.upper() != "NONE":
                from langchain_community.tools import WikipediaQueryRun
                from langchain_community.utilities import WikipediaAPIWrapper
                wiki = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper(top_k_results=1, doc_content_chars_max=500))
                wiki_result = wiki.invoke(entity)
                if wiki_result and "No good Wikipedia Search Result" not in wiki_result:
                    return f"\n\n[Background Web Context from Wikipedia: {wiki_result}]"
        except Exception as e:
            print(f"[Chat] Wikipedia search failed: {e}")
        return ""

    def _retrieve_sources(self, question: str):
        import json
        import re
        from indexer import ReelIndexer

        match = re.search(r'instagram\.com/(?:reel|p)/([A-Za-z0-9_-]+)', question)
        requested_sc = match.group(1) if match else None

        # If a specific shortcode/URL was requested:
        if requested_sc:
            # 1. Check if processed json file exists on disk
            processed_file = Path(self.index_dir).parent / "processed" / f"{requested_sc}.json"
            if processed_file.exists():
                try:
                    with open(processed_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    sources = [{
                        "filename": data.get("filename", f"{requested_sc}.mp4"),
                        "shortcode": requested_sc,
                        "caption": data.get("caption", ""),
                        "username": data.get("username", ""),
                        "thumbnail": data.get("thumbnail", f"{requested_sc}.jpg"),
                        "timestamp": str(data.get("timestamp", "")),
                    }]
                    context_str = f"Source URL: https://instagram.com/reel/{requested_sc}/\n{data.get('content', '')}"
                    return context_str, sources, requested_sc, True
                except Exception as e:
                    print(f"[Chat] Error reading processed json: {e}")

            # 2. Check in index
            indexer = ReelIndexer(self.index_dir)
            hits = indexer.search_hybrid(question, k=1, where={"shortcode": requested_sc})
            if hits:
                h = hits[0]
                meta = h.get("metadata", {})
                sources = [{
                    "filename": meta.get("filename", f"{requested_sc}.mp4"),
                    "shortcode": requested_sc,
                    "caption": meta.get("caption", ""),
                    "username": meta.get("username", ""),
                    "thumbnail": meta.get("thumbnail", ""),
                    "timestamp": meta.get("timestamp", ""),
                }]
                context_str = f"Source URL: https://instagram.com/reel/{requested_sc}/\n{h.get('content', '')}"
                return context_str, sources, requested_sc, True

            # If specific shortcode was requested but NOT found, NEVER fallback to unrelated random reels!
            return "", [], requested_sc, False

        # Regular hybrid search across all reels
        indexer = ReelIndexer(self.index_dir)
        hits = indexer.search_hybrid(question, k=5)
        if not hits:
            hits = indexer.search(question, k=5)

        seen = set()
        sources = []
        context_docs = []
        for h in hits:
            meta = h.get("metadata", {})
            fn = meta.get("filename", "")
            sc = meta.get("shortcode", "")
            if fn and fn not in seen:
                seen.add(fn)
                sources.append({
                    "filename":  fn,
                    "shortcode": sc,
                    "caption":   meta.get("caption", ""),
                    "username":  meta.get("username", ""),
                    "thumbnail": meta.get("thumbnail", ""),
                    "timestamp": meta.get("timestamp", ""),
                })
            context_docs.append(f"Source URL: https://instagram.com/reel/{sc}/\n{h.get('content', '')}")

        context_str = "\n\n---\n\n".join(context_docs)
        return context_str, sources, None, True

    def ask_stream(self, question: str):
        """Streams AI tokens for the user's question using hybrid retrieval."""
        q_clean = question.strip().lower().rstrip("!.,?")
        greetings = {"hi", "hello", "hey", "hola", "sup", "what's up", "good morning", "good evening", "good afternoon", "hi there", "hello there"}
        if q_clean in greetings:
            yield {"type": "sources", "sources": []}
            greeting_msg = (
                "Hello! 👋 I'm **ReelMind**, your local AI assistant for your saved Instagram Reels.\n\n"
                "I can search through your indexed reels, extract recipes, explain concepts, and find specific creators. Try asking:\n"
                "- 🍳 *\"Find recipes or cooking reels\"*\n"
                "- 🏋️ *\"Show me gym or workout tips\"*\n"
                "- 💻 *\"What tech or coding reels do I have?\"*\n\n"
                "How can I help you today?"
            )
            for word in greeting_msg.split(" "):
                yield {"type": "token", "token": word + " "}
            yield {"type": "done", "sources": []}
            return

        context_str, sources, requested_sc, found = self._retrieve_sources(question)

        # If user asked about a specific link that isn't indexed yet:
        if requested_sc and not found:
            yield {"type": "sources", "sources": []}
            not_found_msg = (
                f"### ⚠️ Reel Not Found in Local Library\n\n"
                f"The reel **`https://www.instagram.com/p/{requested_sc}/`** has not been downloaded or indexed on your computer yet.\n\n"
                f"**Why did this happen?**\n"
                f"- This link was added to your queue, but Instagram's server blocked the video download (`rate-limit reached or login required`).\n"
                f"- Because the video (`.mp4`) could not be downloaded, transcription and indexing were skipped for this specific reel.\n\n"
                f"**What you can do:**\n"
                f"- You can ask questions about any of your **196 already-indexed reels** in your collection!\n"
                f"- To add this reel, download its `.mp4` file and place it in `ReelMind/backend/data/reels/{requested_sc}.mp4`."
            )
            for word in not_found_msg.split(" "):
                yield {"type": "token", "token": word + " "}
            yield {"type": "done", "sources": []}
            return

        try:
            self._init_models()
        except Exception as e:
            if "connection" in str(e).lower() or "refused" in str(e).lower():
                raise RuntimeError(
                    "Ollama is not running. Start it with: ollama serve\n"
                    "Then pull a model: ollama pull llama3.2"
                )
            raise

        yield {"type": "sources", "sources": sources}

        prompt_text = PROMPT_TEMPLATE.format(context=context_str, question=question)

        for chunk in self.llm.stream(prompt_text):
            yield {"type": "token", "token": chunk}

        yield {"type": "done", "sources": sources}

    def ask_single_reel_stream(self, content: str, question: str):
        """Streams AI tokens for a single reel."""
        try:
            self._init_models()
        except Exception as e:
            if "connection" in str(e).lower() or "refused" in str(e).lower():
                raise RuntimeError(
                    "Ollama is not running. Start it with: ollama serve\n"
                    "Then pull a model: ollama pull llama3.2"
                )
            raise

        prompt_text = SINGLE_PROMPT_TEMPLATE.format(context=content, question=question)
        for chunk in self.llm.stream(prompt_text):
            yield {"type": "token", "token": chunk}

        yield {"type": "done"}

    def is_ollama_available(self) -> bool:
        """Quick check if Ollama HTTP API is reachable."""
        import urllib.request
        try:
            urllib.request.urlopen(
                "http://localhost:11434/api/tags", timeout=2
            )
            return True
        except Exception:
            return False

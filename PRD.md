# Product Requirements Document (PRD)
## ReelMind - Offline Instagram Reel Search & Chat Application

---

## 1. Executive Summary

**Product Name:** ReelMind (working title)

**Problem Statement:** Users save hundreds of Instagram Reels but cannot search or retrieve them based on spoken content, on-screen text, or conceptual meaning. Existing solutions require API costs, cloud dependencies, or lack video content understanding.

**Solution:** A completely free, offline desktop application that downloads saved Instagram Reels, extracts all content (audio, captions, on-screen text), stores them locally, and provides a ChatGPT-like interface to search and chat with your Reel collection.

**Key Differentiator:** Zero API costs, zero cloud dependencies, 100% local processing and storage.

---

## 2. Technical Stack (100% Free & Local)

| Component | Technology Choice | Why |
|:----------|:------------------|:----|
| **Downloader** | Instaloader | Free, open-source, downloads Reels + JSON metadata  |
| **Speech-to-Text** | OpenAI Whisper (local) | Best-in-class accuracy, completely free, runs offline  |
| **On-screen Text OCR** | EasyOCR | Free, supports multiple languages, local processing |
| **LLM (Chat)** | Ollama + Llama 3.2 / Mistral | Local LLM, no API keys, runs on CPU/GPU  |
| **Embeddings** | sentence-transformers (all-MiniLM-L6-v2) | 90MB only, fast, good quality, free  |
| **Vector Database** | ChromaDB | 100% free, runs locally, no API keys needed  |
| **RAG Orchestration** | LangChain or Piragi | Simplifies the RAG pipeline  |
| **Frontend/UI** | Streamlit or Custom Tkinter | Free, Python-native, easy to build chat interfaces  |

---

## 3. System Architecture Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           REELMIND - SYSTEM ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────────────────────────────────────────┐ │
│  │   PHASE 1    │     │                   PHASE 2                        │ │
│  │   DOWNLOAD   │────▶│                 EXTRACT TEXT                     │ │
│  └──────────────┘     └──────────────────────────────────────────────────┘ │
│         │                                      │                            │
│         ▼                                      ▼                            │
│  ┌──────────────┐     ┌──────────────┐   ┌──────────────┐   ┌────────────┐│
│  │ Instaloader  │     │   Whisper    │   │   EasyOCR    │   │  JSON from ││
│  │  Downloads   │     │  (Audio to   │   │ (Screen Text │   │Instaloader ││
│  │ Reels + JSON │     │   Text)      │   │    to Text)  │   │ (Captions) ││
│  └──────────────┘     └──────────────┘   └──────────────┘   └────────────┘│
│                                                     │                       │
│                                                     ▼                       │
│                              ┌──────────────────────────────────────────┐  │
│                              │            Consolidated Text              │  │
│                              │  {filename: "reel1.mp4",                 │  │
│                              │   content: "caption + transcript + ocr"} │  │
│                              └──────────────────────────────────────────┘  │
│                                                     │                       │
│                                                     ▼                       │
│  ┌──────────────┐     ┌──────────────────────────────────────────────────┐ │
│  │   PHASE 3    │     │                   PHASE 4                        │ │
│  │   INDEXING   │────▶│                   CHAT UI                        │ │
│  └──────────────┘     └──────────────────────────────────────────────────┘ │
│         │                                      │                            │
│         ▼                                      ▼                            │
│  ┌──────────────┐     ┌──────────────┐   ┌──────────────────────────────┐│
│  │  ChromaDB    │     │   Ollama     │   │        Streamlit UI          ││
│  │  (Vectors)   │◀───▶│  (Llama 3.2  │   │  ┌────────────────────────┐  ││
│  └──────────────┘     │   / Mistral) │   │  │ "Find the reel about   │  ││
│         │             └──────────────┘   │  │ sustainable cooking"    │  ││
│         │                    ▲           │  └────────────────────────┘  ││
│         │                    │           │              │               ││
│         │              ┌─────┴─────┐     │              ▼               ││
│         │              │ LangChain │     │  ┌────────────────────────┐  ││
│         └─────────────▶│   RAG     │────▶│  │ "Reel: 2024-05-15.mp4  │  ││
│                        │ Pipeline  │     │  │ Answer: It shows..."   │  ││
│                        └───────────┘     │  └────────────────────────┘  ││
│                                          └──────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Detailed Implementation Steps

### Phase 1: Data Download (Instaloader)

**Objective:** Download all saved Reels and their metadata locally.

**Prerequisites:**
- Python 3.10+ installed
- Instagram account credentials

**Step-by-Step:**

```bash
# 1. Install Instaloader
pip install instaloader

# 2. Download saved Reels (run this command)
instaloader --login YOUR_USERNAME :saved --reels
```

**Output Structure:**
```
saved/
├── 2024-05-15_18-30-00_UTC.mp4      # Reel video
├── 2024-05-15_18-30-00_UTC.json     # Metadata (caption, timestamp, likes)
├── 2024-05-16_20-15-00_UTC.mp4
├── 2024-05-16_20-15-00_UTC.json
└── ...
```

**What JSON Contains:** 
- Caption text
- Timestamp
- Like count
- Hashtags
- Owner username

**Time Estimate:** ~1-2 hours for 500 Reels (depends on internet speed)

---

### Phase 2: Content Extraction (Audio + Screen Text)

**Objective:** Extract ALL text content from each Reel for searchability.

#### 2.1 Audio Transcription with Whisper

```python
import whisper
import os

def transcribe_reel(video_path):
    model = whisper.load_model("base")
    result = model.transcribe(video_path)
    return result["text"]
```

#### 2.2 On-screen Text Extraction with EasyOCR

```python
import easyocr
import cv2

def extract_on_screen_text(video_path, interval_seconds=5):
    reader = easyocr.Reader(['en'])
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(fps * interval_seconds)
    
    all_text = []
    frame_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % frame_interval == 0:
            results = reader.readtext(frame, detail=0)
            all_text.extend(results)
        frame_count += 1
    
    cap.release()
    return " ".join(all_text)
```

#### 2.3 Consolidate All Text

```python
import json
import os

def consolidate_reel_content(video_path, json_path):
    with open(json_path, 'r') as f:
        metadata = json.load(f)
    
    caption = metadata.get('caption', '')
    transcript = transcribe_reel(video_path)
    screen_text = extract_on_screen_text(video_path)
    
    combined_text = f"""
    CAPTION: {caption}
    SPOKEN CONTENT: {transcript}
    ON-SCREEN TEXT: {screen_text}
    """
    
    return {
        'filename': os.path.basename(video_path),
        'content': combined_text,
        'timestamp': metadata.get('date_utc'),
        'caption': caption
    }
```

---

### Phase 3: Vector Indexing

```python
from sentence_transformers import SentenceTransformer
import chromadb
import json
import os

class ReelIndexer:
    def __init__(self, persist_directory="./reel_index"):
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(
            name="reels",
            metadata={"hnsw:space": "cosine"}
        )
    
    def index_reel(self, reel_data):
        embedding = self.embedding_model.encode(reel_data['content'])
        self.collection.add(
            ids=[reel_data['filename']],
            embeddings=[embedding.tolist()],
            metadatas=[{
                'filename': reel_data['filename'],
                'timestamp': reel_data.get('timestamp'),
                'caption': reel_data.get('caption')
            }],
            documents=[reel_data['content']]
        )
```

---

### Phase 4: Chat Interface

```python
from langchain_ollama import OllamaLLM
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

class ReelChat:
    def __init__(self, vector_store_path="./reel_index"):
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.vector_store = Chroma(
            persist_directory=vector_store_path,
            embedding_function=self.embeddings
        )
        self.llm = OllamaLLM(
            model="llama3.2",
            temperature=0.3,
            base_url="http://localhost:11434"
        )
        self.retriever = self.vector_store.as_retriever(search_kwargs={"k": 5})
    
    def ask(self, question):
        result = self.qa_chain.invoke({"query": question})
        return {
            "answer": result['result'],
            "source_reels": [doc.metadata['filename'] for doc in result['source_documents']]
        }
```

---

## 5. Complete Project Structure

```
reelmind/
│
├── download/
│   ├── downloaded_reels/
│   └── instaloader_script.py
│
├── extract/
│   ├── whisper_transcriber.py
│   ├── easyocr_extractor.py
│   ├── consolidate.py
│   └── processed_data/
│
├── index/
│   ├── indexer.py
│   └── reel_index/
│
├── chat/
│   ├── app.py
│   ├── reel_chat.py
│   └── requirements.txt
│
├── requirements.txt
└── README.md
```

---

## 6. Complete requirements.txt

```txt
instaloader>=4.11
openai-whisper>=20231117
easyocr>=1.7.0
opencv-python>=4.8.0
torch>=2.0.0
chromadb>=0.4.22
sentence-transformers>=2.2.0
langchain>=0.3.0
langchain-community>=0.3.0
langchain-ollama>=0.3.0
streamlit>=1.28.0
python-dotenv>=1.0.0
tqdm>=4.65.0
```

---

## 7. Timeline Estimate

| Phase | Effort | Time |
|:------|:-------|:-----|
| Phase 1: Download | Setup only | 30 minutes (plus download time) |
| Phase 2: Extraction | Code + testing | 1-2 days |
| Phase 3: Indexing | Code + testing | 1 day |
| Phase 4: Chat UI | Code + testing | 1-2 days |
| Integration & Polish | Bug fixes, optimizations | 1 day |

**Total: 4-6 days for a working prototype**

---

## 8. Limitations & Future Enhancements

**Current Limitations:**
- Requires manual trigger for downloading new Reels (no auto-sync)
- Whisper transcription can be slow on large collections
- Screen text extraction only processes sampled frames

**Future Enhancements:**
- Add automatic periodic sync with Instagram
- Implement batch GPU processing for faster transcription
- Add video thumbnail display in chat results
- Export search results to CSV/Excel
- Add tagging and custom categorization

# GEMINI Development Guidelines: Extreme Bad-Handwriting Digitizing Stack
**Project ID:** HNX26EPS04 — HACKNEX 2026 Hackathon

## Core Principles & Project Rules

1. **Build From Scratch:**
   - All code, components, pipelines, and modules must be newly implemented specifically for this repository during HACKNEX 2026.
   - Do NOT copy, clone, adapt, or reuse code or architecture templates from previous projects (e.g., old Steganography Detection or Poison Pill LLM Gateway projects).
   - Standard open-source libraries, frameworks, APIs, and public documentation are allowed, but application logic must be original.

2. **Absolute Grounded Truth & Integrity:**
   - **No fake metrics:** Do not invent or fabricate OCR accuracy, Character Error Rate (CER), Word Error Rate (WER), latency numbers, or confidence benchmarks. Metrics are only reported when verified against concrete test datasets.
   - **No fake API responses:** Endpoints must return actual computed states. Never hardcode mock transcribed text to pretend OCR is functioning when it is not.
   - **No fake external links or citations:** All URLs, dataset references, and documentation citations must be genuine and verifiable.
   - **Recognize uncertainty:** A core architectural thesis of this project is flagging uncertainty instead of hallucinating results. The system must reflect this integrity at all levels.

3. **Modular & Extensible Architecture:**
   - Keep preprocessing, recognition, layout analysis, confidence scoring, uncertainty detection, and verification services strictly decoupled.
   - Each phase should be isolated behind clean interfaces with typed schemas (Pydantic models and explicit Python typing).
   - Allow swap-in/swap-out of downstream recognition engines without breaking frontend contracts.

4. **Testing & Verification:**
   - Every added endpoint, service, and utility must be accompanied by automated tests.
   - Run tests before committing (`pytest` for backend, build/lint checks for frontend).
   - Never suppress errors or commit broken builds.

5. **Security & Secrets:**
   - Never commit API keys, tokens, credentials, or production environment variables.
   - All sensitive configs must reside in `.env` (ignored by git) and documented generically in `.env.example`.

6. **Git Discipline:**
   - Maintain clear, descriptive, and conventional commit messages (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).
   - Review `git status` and staged diffs before committing.
   - Never silently delete or overwrite existing work.
   - Keep Git history honest and intelligible for hackathon evaluation.

7. **Documentation & Decision Logging:**
   - Document key architectural decisions, data flows, and trade-offs in `docs/architecture/` and module docstrings.
   - Ensure the repository can be easily understood and presented during student judging.

# CareerX

> **AI-powered Career Assistant** that generates ATS-optimized resumes tailored to a Job Description using Google Gemini.

CareerX is designed as a lightweight, production-style MVP that transforms a candidate's persistent profile and a Job Description into a professional, ATS-friendly PDF resume.

The project follows a clean, modular architecture with strong typing, centralized AI integration, and a CLI-first workflow.

---

# Features

* Persistent candidate profile (`profile.json`)
* AI-powered Job Description parsing
* ATS-optimized resume generation
* Professional LaTeX resume template
* PDF generation
* Command-line interface (CLI)
* Strongly typed Pydantic models
* Modular architecture
* Ruff-compatible codebase

---

# Technology Stack

| Component       | Technology        |
| --------------- | ----------------- |
| Language        | Python 3.13+      |
| Package Manager | uv                |
| AI Model        | Google Gemini     |
| Validation      | Pydantic v2       |
| Configuration   | pydantic-settings |
| CLI             | Typer             |
| Rendering       | Jinja2            |
| PDF             | LaTeX (pdflatex)  |
| Formatting      | Ruff              |
| Testing         | pytest            |

---

# Architecture

```text
                profile.json
                      │
                      ▼
              ProfileService
                      │
                      ▼
             Candidate Profile
                      │
                      │
Job Description ──────┘
        │
        ▼
 Job Description Parser
        │
        ▼
 Structured JobDescription
        │
        ▼
 Resume Builder (Gemini)
        │
        ▼
      Resume Object
        │
        ▼
   Resume Renderer
        │
        ▼
      resume.tex
        │
        ▼
      pdflatex
        │
        ▼
      resume.pdf
```

---

# Prerequisites

Install the following before running CareerX.

* Python 3.13 or later
* uv
* LaTeX distribution

  * TeX Live (Linux)
  * MacTeX (macOS)
  * MiKTeX or TeX Live (Windows)

Verify installation:

```bash
python --version
uv --version
pdflatex --version
```

---

# Installation

Clone the repository.

```bash
git clone https://github.com/AnudeepReddyBondugula/CareerX

cd careerx
```

Install dependencies.

```bash
uv sync
```

or

```bash
uv pip install -e .
```

---

# Environment Configuration

Create a `.env` file in the project root.

```env
GOOGLE_API_KEY=your_google_api_key
```

---

# Candidate Profile

CareerX uses a persistent profile stored in:

```text
profile.json
```

Populate this file with your information once. Every resume generation uses this profile automatically.

---

# Running the Project

Generate a tailored resume using a Job Description.

```bash
careerx generate --job jd.txt --output ./output/
```

Example:

```bash
careerx generate \
    --job examples/backend_engineer.txt \
    --output ./output/
```

Generated files:

```text
output/
├── tailored_resume.tex
└── tailored_resume.pdf
└── tailored_resume.json
```

---

# CLI Usage

Generate a resume.

```bash
careerx generate \
    --job jd.txt \
    --output ./output/
```

Help menu.

```bash
careerx --help
```

Generate command help.

```bash
careerx generate --help
```

---

# How It Works

1. Load candidate profile from `profile.json`.
2. Read the Job Description.
3. Parse the Job Description into a structured model.
4. Generate an ATS-optimized resume using Gemini.
5. Render the resume into LaTeX.
6. Compile LaTeX into a PDF.

Pipeline:

```text
Profile
    +
Job Description
        │
        ▼
 JD Parser
        │
        ▼
 Resume Builder
        │
        ▼
 Resume Renderer
        │
        ▼
 resume.tex
        │
        ▼
 resume.pdf
```

---

# Development

Run Ruff.

```bash
ruff check .
```

Auto-fix issues.

```bash
ruff check . --fix
```

Format code.

```bash
ruff format .
```

---

# Future Roadmap

Planned enhancements beyond the include:

* Cover Letter Generation
* Interview Preparation
* Resume Scoring
* Job Market Analysis
* Skill Gap Analysis
* Multiple Resume Templates
* DOCX Export
* Recruiter Feedback

---

# Acknowledgements

Built with:

* Python
* Google Gemini
* Typer
* Pydantic
* Jinja2
* LaTeX
* Ruff

---

**CareerX**

Build once. Tailor everywhere.

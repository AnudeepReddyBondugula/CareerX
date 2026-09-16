# CareerX

**An AI resume builder that cannot lie about you.**

CareerX takes your complete career profile (as JSON) and a job posting, and
returns an ATS-optimised, LaTeX-typeset resume tailored to that posting — as a
PDF, a `.tex` source file, and structured JSON.

The interesting part is not that an LLM rewrites your bullets. It is that the
system retrieves the evidence first and verifies the output afterwards, so the
generated resume is constrained to things you actually did.

---

## Contents

- [How it works](#how-it-works)
- [Why retrieval, and why grounding](#why-retrieval-and-why-grounding)
- [Quick start](#quick-start)
- [The profile file](#the-profile-file)
- [HTTP API](#http-api)
- [CLI](#cli)
- [Configuration](#configuration)
- [LaTeX, and how it stays free](#latex-and-how-it-stays-free)
- [Deployment](#deployment)
- [Architecture](#architecture)
- [Development](#development)
- [Design decisions and trade-offs](#design-decisions-and-trade-offs)

---

## How it works

```
  profile.json          job posting (raw text)
       │                          │
       │                          ▼
       │                 ┌─────────────────┐
       │                 │  JD Parser      │  LLM → structured JobDescription
       │                 └────────┬────────┘
       │                          │ requirements
       ▼                          ▼
┌──────────────┐          ┌──────────────────┐
│  Chunker     │  atomic  │   FAISS index    │  cosine over unit vectors
│  (1 bullet = │─────────▶│  (IndexFlatIP)   │◀── embeddings (provider/local)
│   1 chunk)   │  evidence└────────┬─────────┘
└──────────────┘                   │ top-k per requirement
                                   ▼
                        ┌─────────────────────────┐
                        │  Retrieval result       │
                        │  · evidence per req     │
                        │  · section relevance    │
                        │  · coverage / gaps      │
                        └────────────┬────────────┘
                                     ▼
                        ┌─────────────────────────┐
                        │  Resume Builder (LLM)   │  sees evidence, not everything
                        └────────────┬────────────┘
                                     ▼
                        ┌─────────────────────────┐
                        │  Grounding Validator    │  ← removes anything invented
                        └────────────┬────────────┘
                                     ▼
                     Jinja2 → LaTeX → Tectonic → PDF
```

Every stage is a separate, injectable component, and every one of them is
tested without a network connection.

---

## Why retrieval, and why grounding

**Retrieval.** A complete career profile is long — every project, every bullet,
every skill you have ever had. Pasting all of it into a prompt is expensive,
pushes the model toward generic output, and gets worse as the profile grows.
Instead, the profile is split into atomic chunks (one achievement bullet = one
chunk), embedded, and indexed with FAISS. Each requirement in the posting is
then used as a semantic query, so the generation prompt contains the evidence
that matters for *this* job, ranked, plus an explicit list of requirements your
profile does **not** support.

That last part is what makes retrieval load-bearing rather than decorative: the
model is told which requirements are gaps, and instructed to leave them as gaps.

**Grounding.** Prompting a model to "never fabricate" reduces fabrication; it
does not eliminate it. So the generated resume is checked against the source
profile before it is rendered:

| Check | Rule |
|---|---|
| Employers | must already appear in the profile |
| Projects | must already appear in the profile |
| Institutions, certifications | must already appear in the profile |
| Skills | must already be claimed in the profile |
| Numbers in bullets | every metric must appear somewhere in the profile |
| Contact details | always copied from the profile, never from model output |

Anything that fails is removed and reported in `report.grounding_issues`
(or, with `STRICT_GROUNDING=true`, fails the whole run). The metric check is
the one that matters most in practice: it is what stops "improved performance"
from quietly becoming "improved performance by 40%".

---

## Quick start

### Docker (recommended — includes LaTeX)

```bash
git clone https://github.com/AnudeepReddyBondugula/CareerX
cd CareerX

cp .env.example .env
# Set GOOGLE_API_KEY (free tier) or switch LLM_PROVIDER=openai and set OPENAI_API_KEY

docker compose up --build
```

Open <http://localhost:8000> for the UI, or <http://localhost:8000/docs> for the API.

The first build takes a few minutes: it downloads Tectonic and pre-compiles
both templates so the first request is fast.

### Local (Python 3.13+ and [uv](https://docs.astral.sh/uv/))

```bash
uv sync
cp .env.example .env    # then add your API key

uv run careerx doctor   # reports what this machine can and cannot do
uv run careerx serve
```

Without a LaTeX engine installed you still get valid `.tex` and JSON output —
only the PDF step is skipped, and the response says so.

---

## The profile file

Your profile is a single JSON file describing everything you have done. Write
it once; every generated resume is a tailored subset of it.

Get a filled-in example and the exact schema:

```bash
uv run careerx example-profile -o profile.json
uv run careerx profile-schema
```

or, from a running server, `GET /api/v1/profile/example` and
`GET /api/v1/profile/schema`.

```jsonc
{
  "profile": {
    "full_name": "Ada Sharma",
    "headline": "Backend Engineer",
    "email": "ada.sharma@example.com",
    "phone": "+1 555 0100",
    "location": "Bengaluru, India",
    "linkedin": "https://linkedin.com/in/example",
    "github": "https://github.com/example",
    "portfolio": ""
  },
  "summary": "Backend engineer with 4 years building Python services…",
  "experience": [
    {
      "company": "Northwind Payments",
      "title": "Senior Backend Engineer",
      "location": "Bengaluru, India",
      "start_date": "Mar 2023",
      "end_date": "Present",
      "achievements": [
        "Rebuilt the settlement pipeline on FastAPI and PostgreSQL, cutting median reconciliation time from 40 minutes to 6 minutes."
      ]
    }
  ],
  "projects": [
    {
      "name": "CareerX",
      "technologies": ["Python", "FastAPI", "FAISS"],
      "description": ["Built an AI resume builder…"],
      "github": "https://github.com/example/careerx",
      "live_demo": ""
    }
  ],
  "skills": [{ "name": "Python", "category": "Languages" }],
  "education": [
    {
      "institution": "NIT Warangal",
      "degree": "B.Tech",
      "field_of_study": "Computer Science",
      "start_date": "2017",
      "end_date": "2021",
      "grade": "8.6 CGPA"
    }
  ],
  "certifications": [{ "name": "AWS SAA", "issuer": "Amazon Web Services" }],
  "achievements": [{ "title": "Hackathon winner", "description": "…" }]
}
```

**Include everything.** Retrieval picks what is relevant per job, so a longer
profile produces better-targeted resumes, not worse ones. And because a metric
must exist in the profile to survive grounding, quantify your bullets *here*.

---

## HTTP API

Interactive docs at `/docs`. All endpoints are under `/api/v1`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/generate` | Generate from a JSON body |
| `POST` | `/api/v1/generate/upload` | Generate from an uploaded `profile.json` (multipart) |
| `GET` | `/api/v1/runs/{run_id}/{artifact}` | Download `resume.pdf`, `resume.tex`, `resume.json`, `report.json` |
| `GET` | `/api/v1/meta` | Provider, models, templates, LaTeX engine, limits |
| `GET` | `/api/v1/profile/schema` | JSON Schema for the profile |
| `GET` | `/api/v1/profile/example` | A valid example profile |
| `GET` | `/healthz`, `/readyz` | Liveness and readiness |

### Example

```bash
curl -X POST http://localhost:8000/api/v1/generate/upload \
  -F profile=@profile.json \
  -F job_description_file=@jd.txt \
  -F template=treyHunner \
  | tee response.json | jq '{run_id, pdf_available, coverage: .report.coverage}'

curl -OJ "$(jq -r .artifacts.pdf response.json)"
```

### Response shape

```jsonc
{
  "run_id": "9f2c…",
  "template": "treyHunner",
  "expires_in_seconds": 1800,
  "resume": { /* the tailored Resume */ },
  "job_description": { /* the parsed posting */ },
  "latex": "\\documentclass{resume}…",
  "pdf_available": true,
  "artifacts": {
    "pdf": "http://…/runs/9f2c…/resume.pdf",
    "latex": "http://…/runs/9f2c…/resume.tex",
    "resume_json": "http://…/runs/9f2c…/resume.json"
  },
  "report": {
    "provider": "gemini",
    "embedding_backend": "provider:gemini:text-embedding-004",
    "evidence_chunks": 34,
    "requirement_matches": [
      { "requirement": "FastAPI", "matches": [{ "chunk_id": "experience:0:1", "score": 0.81, "text": "…" }] }
    ],
    "section_scores": [
      { "section_id": "experience:0", "label": "Senior Backend Engineer - Northwind Payments", "score": 3.42 }
    ],
    "coverage": { "covered": ["Python"], "partially_covered": [], "uncovered": ["Kafka"] },
    "grounding_issues": []
  },
  "timings_ms": { "parse_job_description": 1420, "retrieve_evidence": 260, "generate_resume": 8100, "compile_pdf": 1900 }
}
```

The `report` is the explainability surface: which of your bullets matched which
requirement, which parts of your profile ranked highest, which requirements you
do not cover, and what (if anything) the model tried to invent.

### Errors

Uniform JSON: `{"error": "<code>", "detail": "…", "request_id": "…"}`.

| Status | `error` | Meaning |
|---|---|---|
| 400 | `unknown_template` | No such template |
| 413 | `payload_too_large` | Upload or posting exceeds the limit |
| 422 | `invalid_profile` / `validation_error` | Bad input |
| 422 | `ungrounded_content` | Strict mode rejected the generated resume |
| 429 | `rate_limited` | Includes a `Retry-After` header |
| 502 | `llm_upstream_error` | Provider failed after retries |
| 503 | `llm_not_configured` | No API key for the selected provider |

---

## CLI

```bash
careerx doctor                              # what this machine can do
careerx example-profile -o profile.json     # start from a filled-in example
careerx profile-schema                      # print the JSON Schema

careerx generate --job jd.txt --profile profile.json --output ./output
careerx generate --job jd.txt --template classic --no-pdf

careerx serve --port 8000 --reload
```

`generate` prints a coverage summary and a ranking of your most relevant
sections, then writes `resume.tex`, `resume.pdf`, `resume.json` and
`report.json`.

---

## Configuration

Everything is environment-driven; see [`.env.example`](.env.example) for the
annotated list. The ones that matter most:

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` |
| `GOOGLE_API_KEY` / `OPENAI_API_KEY` | — | One is required |
| `EMBEDDING_BACKEND` | `auto` | `auto`, `provider`, `sentence-transformers`, `hashing` |
| `DEFAULT_TEMPLATE` | `treyHunner` | `treyHunner` or `classic` |
| `LATEX_ENGINE` | auto-detect | `tectonic`, then `pdflatex` |
| `ARTIFACT_TTL_SECONDS` | `1800` | How long downloads stay available |
| `STRICT_GROUNDING` | `false` | `true` fails instead of repairing |
| `RATE_LIMIT_REQUESTS` | `10` | Per IP, per window |

### Embedding backends

Resolved as a fallback chain, so the service runs anywhere:

1. **`provider`** — Gemini or OpenAI embedding APIs. Best quality; needs a key.
2. **`sentence-transformers`** — local MiniLM. Free and offline, but pulls in
   torch (~2 GB installed), so it is an optional extra:
   `uv sync --extra local-embeddings`.
3. **`hashing`** — deterministic signed-hash bag-of-terms, built in, no
   dependencies, no network. Weaker than a neural encoder (no synonymy: it will
   not match "Postgres" to "relational databases"), but exact on shared
   vocabulary, and it keeps the test suite hermetic and the free-tier image small.

---

## LaTeX, and how it stays free

A resume using `fontawesome5` normally implies a full TeX Live install — several
gigabytes, which no free host will build or run happily.

CareerX uses **[Tectonic](https://tectonic-typesetting.github.io/)** instead: a
single ~35 MB self-contained binary that downloads only the packages a document
actually needs and caches them. The Docker image installs it and then
pre-compiles every template at build time, which warms that cache *and* fails
the build if a template is broken.

Three further properties keep this robust:

- **Engine fallback.** If the preferred engine is installed but unusable — most
  commonly Tectonic on a host that cannot reach its package bundle — the
  compiler transparently tries the next available engine (`pdflatex`).
- **Graceful degradation.** With no engine at all, generation still succeeds and
  returns the `.tex` and JSON, with `pdf_available: false` and a reason. A
  missing TeX install is not a 500.
- **A dependency-light template.** `classic` uses only stock `article` plus
  packages present in any minimal TeX installation — no custom `.cls`, no
  fontawesome — so it compiles in environments where `treyHunner` cannot.

### LaTeX injection

Resume data is arbitrary user input, and LaTeX is a programming language:
`\input{/etc/passwd}` in a name field is a file-read primitive, and a stray `&`
or `%` breaks compilation outright. Every interpolated value is escaped through
the Jinja environment's `finalize` hook, so a template *cannot* forget to escape
something; values that are legitimately LaTeX must be explicitly marked
`LatexSafe`. URLs get URL-safe escaping instead, since hyperref reads them
near-verbatim. This is covered by tests.

---

## Deployment

### Render (free tier)

A [`render.yaml`](render.yaml) blueprint is included. Point Render at the repo,
set `GOOGLE_API_KEY` (or `OPENAI_API_KEY`) as a secret, and deploy.

The free instance sleeps after inactivity — expect a ~50 s cold start — and has
512 MB of RAM, which is why the image does not bundle torch. `EMBEDDING_BACKEND`
stays on `auto`: provider embeddings when the key works, hashing otherwise.

### Anywhere else

The image is a plain Docker image with no host-specific assumptions. It reads
`$PORT`, binds `$HOST`, runs as a non-root user, and exposes `/healthz` and
`/readyz`. That is enough for Fly.io, Railway, Cloud Run, Hugging Face Spaces
(set `PORT=7860`) or a VPS.

---

## Architecture

```
src/careerx/
├── api/                 FastAPI app, routes, schemas, error handling, rate limiting
│   └── static/          single-page browser UI
├── ai/
│   ├── providers/       LLMProvider ABC + Gemini and OpenAI implementations
│   └── prompts/         system instructions
├── rag/
│   ├── chunking.py      Resume → atomic EvidenceChunks
│   ├── embeddings.py    backend chain: provider → sentence-transformers → hashing
│   ├── index.py         FAISS IndexFlatIP wrapper
│   └── retriever.py     per-requirement retrieval, section scoring, coverage
├── builders/            JD parsing and resume generation
├── services/
│   ├── generation_service.py   the pipeline
│   ├── grounding.py            anti-hallucination validator
│   └── artifact_store.py       TTL-expiring run storage
├── renderers/           Jinja2 → LaTeX, with escaping
├── latex/               engine detection, compilation, fallback
├── templates/           *.tex.j2 + assets/resume.cls
├── models/              Pydantic domain models
├── config/              settings and logging
└── cli.py               Typer CLI
```

Nothing above `api/` imports from it: the CLI and the web service are two front
ends over the same `ResumeGenerationService`.

---

## Development

```bash
uv sync --all-extras

uv run pytest -q          # 176 tests, no network, no API key needed
uv run ruff check .
uv run ruff format .
```

The suite runs against a `FakeProvider`, so it is deterministic and offline.
The PDF compilation tests skip automatically when no LaTeX engine is installed
and run for real when one is — CI installs Tectonic so they always run there.

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs lint, format
check and tests, then builds the Docker image and smoke-tests the container.

---

## Design decisions and trade-offs

Things that were deliberate, including the costs:

- **Stateless service, TTL artifact store.** No database and no accounts. The
  payloads are people's resumes, so the right default for a public demo is to
  keep nothing. The cost is that a run's downloads expire.
- **In-process rate limiting.** Correct only for a single replica. A Redis-backed
  limiter would be the most fragile part of a free-tier deployment, so the
  limitation is accepted and documented rather than engineered around.
- **Exact FAISS index (`IndexFlatIP`).** A profile has hundreds of chunks, not
  millions. An approximate index would trade recall for a speedup that does not
  matter at this size.
- **Per-request index.** Built and discarded per request, which follows from
  statelessness. For a multi-tenant product you would cache the index per
  profile version instead.
- **Grounding repairs by default, fails in strict mode.** A user would rather
  get a resume with one bullet removed than a 500. Teams wanting a hard failure
  set `STRICT_GROUNDING=true`.
- **Provider abstraction over one SDK.** Two providers is the point: it forces
  the interface to be real, and it is what lets a deployment switch on a single
  environment variable.

---

## Acknowledgements

The `treyHunner` template is the Medium Length Professional CV by
[Trey Hunner](http://www.treyhunner.com/), via
[LaTeXTemplates.com](http://www.LaTeXTemplates.com), used under its original
permissive notice (see `src/careerx/templates/assets/resume.cls`).

Built with FastAPI, Pydantic, FAISS, Jinja2, Typer, Tectonic, and Google Gemini
or OpenAI.

---

**CareerX — build once, tailor everywhere.**

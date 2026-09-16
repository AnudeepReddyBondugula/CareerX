import numpy as np
import pytest

from careerx.ai.providers.base import EmbeddingTask
from careerx.config.settings import Settings
from careerx.models import (
    Education,
    EvidenceChunk,
    EvidenceKind,
    Experience,
    JobDescription,
    Project,
    Resume,
    Skill,
)
from careerx.rag.chunking import build_evidence_chunks
from careerx.rag.embeddings import HashingEmbeddings, build_embedding_backend
from careerx.rag.index import VectorIndex
from careerx.rag.retriever import EvidenceRetriever

# ----------------------------------------------------------------------
# Chunking
# ----------------------------------------------------------------------


def test_each_achievement_becomes_its_own_chunk() -> None:
    resume = Resume(
        experience=[
            Experience(
                company="Acme",
                title="Engineer",
                achievements=["Built a thing", "Fixed another thing"],
            )
        ]
    )

    chunks = build_evidence_chunks(resume)

    # One header chunk plus one per bullet.
    assert len(chunks) == 3
    assert [chunk.item_index for chunk in chunks] == [0, 1, 2]
    assert all(chunk.kind is EvidenceKind.EXPERIENCE for chunk in chunks)


def test_chunk_ids_are_stable_and_unique(profile: Resume) -> None:
    first = build_evidence_chunks(profile)
    second = build_evidence_chunks(profile)

    ids = [chunk.chunk_id for chunk in first]
    assert len(ids) == len(set(ids))
    assert ids == [chunk.chunk_id for chunk in second]


def test_chunks_carry_their_owning_label(profile: Resume) -> None:
    chunks = build_evidence_chunks(profile)
    experience_chunks = [c for c in chunks if c.kind is EvidenceKind.EXPERIENCE]

    assert all(chunk.label for chunk in experience_chunks)
    assert any("Northwind Payments" in chunk.text for chunk in experience_chunks)


def test_blank_entries_are_skipped() -> None:
    resume = Resume(
        skills=[Skill(name=""), Skill(name="Python")],
        education=[Education()],
    )

    chunks = build_evidence_chunks(resume)

    assert len(chunks) == 1
    assert "Python" in chunks[0].text


def test_section_id_groups_chunks_from_one_entry() -> None:
    resume = Resume(projects=[Project(name="A", description=["x", "y"])])

    section_ids = {chunk.section_id for chunk in build_evidence_chunks(resume)}

    assert section_ids == {"project:0"}


# ----------------------------------------------------------------------
# Embeddings
# ----------------------------------------------------------------------


def test_hashing_embeddings_are_unit_norm() -> None:
    vectors = HashingEmbeddings(128).encode(["hello world", "python fastapi"], task=EmbeddingTask.DOCUMENT)

    assert vectors.shape == (2, 128)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


def test_hashing_embeddings_are_deterministic() -> None:
    backend = HashingEmbeddings(128)
    first = backend.encode(["FastAPI and PostgreSQL"], task=EmbeddingTask.DOCUMENT)
    second = HashingEmbeddings(128).encode(["FastAPI and PostgreSQL"], task=EmbeddingTask.DOCUMENT)

    assert np.allclose(first, second)


def test_hashing_embeddings_rank_shared_vocabulary_higher() -> None:
    backend = HashingEmbeddings(1024)
    query = backend.encode(["python fastapi backend service"], task=EmbeddingTask.QUERY)
    documents = backend.encode(
        [
            "Built a python fastapi backend service for payments",
            "Designed marketing campaigns for retail clients",
        ],
        task=EmbeddingTask.DOCUMENT,
    )

    scores = documents @ query[0]

    assert scores[0] > scores[1]


def test_empty_input_returns_empty_matrix() -> None:
    assert HashingEmbeddings(64).encode([], task=EmbeddingTask.DOCUMENT).shape == (0, 64)


def test_text_without_usable_tokens_does_not_produce_nan() -> None:
    vectors = HashingEmbeddings(64).encode(["   ", "!!!"], task=EmbeddingTask.DOCUMENT)

    assert not np.isnan(vectors).any()


def test_backend_selection_falls_back_to_hashing_without_a_provider() -> None:
    settings = Settings(_env_file=None, embedding_backend="hashing", hashing_embedding_dimension=256)

    backend = build_embedding_backend(settings, provider=None)

    assert isinstance(backend, HashingEmbeddings)
    assert backend.dimension == 256


# ----------------------------------------------------------------------
# Index
# ----------------------------------------------------------------------


def _chunk(index: int, text: str) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=f"skill:{index}:0",
        kind=EvidenceKind.SKILL,
        section_index=index,
        text=text,
    )


def test_index_returns_nearest_chunk_first() -> None:
    backend = HashingEmbeddings(512)
    chunks = [_chunk(0, "python fastapi"), _chunk(1, "graphic design illustrator")]

    index = VectorIndex(512)
    index.add(chunks, backend.encode([c.text for c in chunks], task=EmbeddingTask.DOCUMENT))

    results = index.search(backend.encode(["fastapi python"], task=EmbeddingTask.QUERY), top_k=2)

    assert results[0][0][0].chunk_id == "skill:0:0"
    assert results[0][0][1] > results[0][1][1]


def test_index_clamps_top_k_to_corpus_size() -> None:
    backend = HashingEmbeddings(64)
    chunks = [_chunk(0, "python")]

    index = VectorIndex(64)
    index.add(chunks, backend.encode(["python"], task=EmbeddingTask.DOCUMENT))

    assert len(index.search(backend.encode(["python"], task=EmbeddingTask.QUERY), top_k=10)[0]) == 1


def test_empty_index_returns_a_row_per_query() -> None:
    assert VectorIndex(8).search(np.zeros((3, 8), dtype=np.float32), top_k=5) == [[], [], []]


def test_index_rejects_mismatched_inputs() -> None:
    with pytest.raises(ValueError, match="chunks but"):
        VectorIndex(8).add([_chunk(0, "a")], np.zeros((2, 8), dtype=np.float32))


def test_index_rejects_wrong_dimensionality() -> None:
    with pytest.raises(ValueError, match="dimensional"):
        VectorIndex(8).add([_chunk(0, "a")], np.zeros((1, 4), dtype=np.float32))


# ----------------------------------------------------------------------
# Retriever
# ----------------------------------------------------------------------


def test_retrieval_matches_every_requirement(
    profile: Resume,
    parsed_job_description: JobDescription,
    settings: Settings,
) -> None:
    retriever = EvidenceRetriever(HashingEmbeddings(1024), settings)

    result = retriever.retrieve(profile, parsed_job_description)

    assert len(result.requirement_matches) == len(parsed_job_description.requirement_statements())
    assert all(match.matches for match in result.requirement_matches)
    assert result.chunks


def test_retrieval_surfaces_the_relevant_skill(settings: Settings) -> None:
    resume = Resume(
        skills=[Skill(name="Kubernetes", category="Cloud"), Skill(name="Photoshop", category="Design")],
    )
    job = JobDescription(required_skills=["Kubernetes"])

    result = EvidenceRetriever(HashingEmbeddings(1024), settings).retrieve(resume, job)

    assert "Kubernetes" in result.requirement_matches[0].matches[0].text


def test_section_scores_rank_the_more_relevant_role_first(settings: Settings) -> None:
    resume = Resume(
        experience=[
            Experience(company="DesignCo", title="Designer", achievements=["Produced print brochures"]),
            Experience(
                company="PyCo",
                title="Backend Engineer",
                achievements=["Built python fastapi microservices on postgresql"],
            ),
        ]
    )
    job = JobDescription(required_skills=["python", "fastapi", "postgresql", "microservices"])

    result = EvidenceRetriever(HashingEmbeddings(1024), settings).retrieve(resume, job)

    top = result.section_scores[0]
    assert top.section_id == "experience:1"
    assert top.matched_requirements == ["python", "fastapi", "postgresql", "microservices"]

    # The unrelated design role must not outrank it, and given orthogonal
    # vocabulary it is expected to score nothing at all.
    design = [score for score in result.section_scores if score.section_id == "experience:0"]
    assert all(score.score < top.score for score in design)


def test_coverage_flags_a_requirement_the_profile_cannot_support(settings: Settings) -> None:
    resume = Resume(skills=[Skill(name="Python")])
    job = JobDescription(required_skills=["Python", "Rust embedded firmware development"])

    coverage = EvidenceRetriever(HashingEmbeddings(1024), settings).retrieve(resume, job).coverage

    assert "Rust embedded firmware development" in coverage.uncovered
    assert coverage.coverage_ratio < 1.0


def test_retrieval_is_a_no_op_without_requirements(profile: Resume, settings: Settings) -> None:
    result = EvidenceRetriever(HashingEmbeddings(256), settings).retrieve(profile, JobDescription())

    assert result.requirement_matches == []
    assert result.section_scores == []


def test_retrieval_is_a_no_op_for_an_empty_profile(
    parsed_job_description: JobDescription,
    settings: Settings,
) -> None:
    result = EvidenceRetriever(HashingEmbeddings(256), settings).retrieve(Resume(), parsed_job_description)

    assert result.chunks == []
    assert result.coverage.uncovered == parsed_job_description.requirement_statements()


def test_top_evidence_is_capped_and_deduplicated(
    profile: Resume,
    parsed_job_description: JobDescription,
    settings: Settings,
) -> None:
    result = EvidenceRetriever(HashingEmbeddings(1024), settings).retrieve(profile, parsed_job_description)

    evidence = result.top_evidence(limit=5)

    assert len(evidence) <= 5
    assert len({chunk.chunk_id for chunk in evidence}) == len(evidence)

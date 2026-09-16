"""Split a profile into atomic, independently retrievable evidence chunks.

Chunking at the level of a single bullet (rather than a whole job) is what
makes retrieval useful: a ten-year career produces one oversized blob under
naive chunking, and the relevant sentence gets averaged away.
"""

from __future__ import annotations

from careerx.models import EvidenceChunk, EvidenceKind, Resume


def _clean(text: str) -> str:
    return " ".join(text.split())


def build_evidence_chunks(resume: Resume) -> list[EvidenceChunk]:
    """Return every retrievable fact in ``resume``, in stable order.

    Chunk ids are derived from position, so the same profile always yields the
    same ids and a tailoring report can be replayed against it.
    """
    chunks: list[EvidenceChunk] = []

    def add(
        kind: EvidenceKind,
        section_index: int,
        item_index: int,
        label: str,
        text: str,
    ) -> None:
        cleaned = _clean(text)
        if cleaned:
            chunks.append(
                EvidenceChunk(
                    chunk_id=f"{kind.value}:{section_index}:{item_index}",
                    kind=kind,
                    section_index=section_index,
                    item_index=item_index,
                    label=_clean(label),
                    text=cleaned,
                )
            )

    if resume.summary:
        add(EvidenceKind.SUMMARY, 0, 0, "Professional summary", resume.summary)

    for index, experience in enumerate(resume.experience):
        label = " - ".join(part for part in (experience.title, experience.company) if part)
        header = ", ".join(
            part
            for part in (
                label,
                experience.location,
                " - ".join(part for part in (experience.start_date, experience.end_date) if part),
            )
            if part
        )

        # The role header is itself evidence (titles and tenure match seniority
        # requirements), separate from each achievement bullet.
        add(EvidenceKind.EXPERIENCE, index, 0, label, header)

        for bullet_index, achievement in enumerate(experience.achievements, start=1):
            add(EvidenceKind.EXPERIENCE, index, bullet_index, label, f"{label}: {achievement}")

    for index, project in enumerate(resume.projects):
        technologies = ", ".join(project.technologies)
        header = f"{project.name} built with {technologies}" if technologies else project.name
        add(EvidenceKind.PROJECT, index, 0, project.name, header)

        for bullet_index, detail in enumerate(project.description, start=1):
            add(EvidenceKind.PROJECT, index, bullet_index, project.name, f"{project.name}: {detail}")

    for index, skill in enumerate(resume.skills):
        if skill.name:
            add(EvidenceKind.SKILL, index, 0, skill.category, f"{skill.category}: {skill.name}")

    for index, education in enumerate(resume.education):
        # Joined conditionally: an entry with only an institution must not
        # produce filler like "in at", which would embed as noise.
        degree = " in ".join(part for part in (education.degree, education.field_of_study) if part)
        text = " at ".join(part for part in (degree, education.institution) if part)
        add(EvidenceKind.EDUCATION, index, 0, education.institution, text)

    for index, certification in enumerate(resume.certifications):
        text = " issued by ".join(part for part in (certification.name, certification.issuer) if part)
        add(EvidenceKind.CERTIFICATION, index, 0, certification.name, text)

    for index, achievement in enumerate(resume.achievements):
        text = ": ".join(part for part in (achievement.title, achievement.description) if part)
        add(EvidenceKind.ACHIEVEMENT, index, 0, achievement.title, text)

    return chunks

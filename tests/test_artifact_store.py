import time
from pathlib import Path

import pytest

from careerx.services.artifact_store import ArtifactNotFoundError, ArtifactStore


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "artifacts", ttl_seconds=60)


def test_written_artifacts_round_trip(store: ArtifactStore) -> None:
    run_id = store.new_run_id()
    store.write(run_id, "resume.tex", "\\documentclass{article}")

    stored = store.read(run_id, "resume.tex")

    assert stored.path.read_text(encoding="utf-8") == "\\documentclass{article}"
    assert stored.media_type == "application/x-tex"


def test_binary_artifacts_keep_their_media_type(store: ArtifactStore) -> None:
    run_id = store.new_run_id()
    store.write(run_id, "resume.pdf", b"%PDF-1.7")

    assert store.read(run_id, "resume.pdf").media_type == "application/pdf"


def test_run_ids_are_unique(store: ArtifactStore) -> None:
    assert len({store.new_run_id() for _ in range(100)}) == 100


def test_missing_artifact_raises(store: ArtifactStore) -> None:
    run_id = store.new_run_id()
    store.write(run_id, "resume.tex", "x")

    with pytest.raises(ArtifactNotFoundError):
        store.read(run_id, "resume.pdf")


def test_unknown_run_raises(store: ArtifactStore) -> None:
    with pytest.raises(ArtifactNotFoundError):
        store.read(store.new_run_id(), "resume.tex")


@pytest.mark.parametrize("run_id", ["..", "../../etc", "not-a-uuid", "", "a" * 31])
def test_malformed_run_ids_are_rejected(store: ArtifactStore, run_id: str) -> None:
    with pytest.raises(ArtifactNotFoundError, match="Invalid run id"):
        store.read(run_id, "resume.tex")


@pytest.mark.parametrize("name", ["../secret", "a/b", "..", "", "x" * 65])
def test_path_traversal_in_the_artifact_name_is_rejected(store: ArtifactStore, name: str) -> None:
    run_id = store.new_run_id()
    store.write(run_id, "resume.tex", "x")

    with pytest.raises(ArtifactNotFoundError, match="Invalid artifact name"):
        store.read(run_id, name)


def test_expired_runs_are_not_served(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts", ttl_seconds=0)
    run_id = store.new_run_id()
    store.write(run_id, "resume.tex", "x")

    time.sleep(0.01)

    with pytest.raises(ArtifactNotFoundError, match="expired"):
        store.read(run_id, "resume.tex")


def test_sweep_removes_expired_runs_and_keeps_fresh_ones(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts", ttl_seconds=3600)
    fresh = store.new_run_id()
    store.write(fresh, "resume.tex", "x")

    stale = store.new_run_id()
    store.write(stale, "resume.tex", "x")
    stale_dir = store.root / stale
    old = time.time() - 7200
    import os

    os.utime(stale_dir, (old, old))

    assert store.sweep() == 1
    assert not stale_dir.exists()
    assert store.read(fresh, "resume.tex")


def test_delete_run_removes_everything(store: ArtifactStore) -> None:
    run_id = store.new_run_id()
    store.write(run_id, "resume.tex", "x")
    store.write(run_id, "resume.pdf", b"y")

    store.delete_run(run_id)

    assert not (store.root / run_id).exists()

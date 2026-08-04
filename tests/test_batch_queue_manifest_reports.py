from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import threading
import time

import pytest

from app.batch.exporter import BatchOutputWriter
from app.batch.manifest import ManifestStore
from app.batch.models import (
    BatchConfig,
    BatchErrorType,
    BatchItemStatus,
    BatchJobStatus,
    ScanOptions,
)
from app.batch.service import (
    MAX_RETRY_CACHE_ITEMS,
    BatchRunControl,
    BatchService,
)
from app.config.settings import AppSettings
from app.errors import (
    BatchConfigurationError,
    BatchManifestError,
    ExportError,
    ModelLoadError,
)
from tests.batch_helpers import (
    FakeBatchTaggingService,
    create_job,
    touch_image,
)


def _images(root: Path, count: int = 3) -> None:
    for index in range(count):
        touch_image(root / f"{index}.png")


def test_queue_runs_in_deterministic_serial_order(tmp_path: Path) -> None:
    _images(tmp_path)
    batch, job, fake = create_job(tmp_path)
    batch.run_job(job)
    assert [path.name for path in fake.calls] == ["0.png", "1.png", "2.png"]
    assert all(item.attempt_count == 1 for item in job.items)


def test_one_inference_failure_does_not_abort_later_items(
    tmp_path: Path,
) -> None:
    _images(tmp_path)
    fake = FakeBatchTaggingService()
    fake.fail_names.add("1.png")
    batch, job, _ = create_job(tmp_path, service=fake)
    batch.run_job(job)
    assert [item.status for item in job.items] == [
        BatchItemStatus.COMPLETED,
        BatchItemStatus.FAILED,
        BatchItemStatus.COMPLETED,
    ]
    assert job.status is BatchJobStatus.COMPLETED_WITH_ERRORS


def test_pause_takes_effect_after_current_item_and_resume_continues(
    tmp_path: Path,
) -> None:
    _images(tmp_path, 2)
    fake = FakeBatchTaggingService()
    fake.started_event = threading.Event()
    fake.release_event = threading.Event()
    batch, job, _ = create_job(tmp_path, service=fake)
    control = BatchRunControl()
    thread = threading.Thread(
        target=batch.run_job,
        kwargs={"job": job, "control": control},
    )
    thread.start()
    assert fake.started_event.wait(3)
    control.pause()
    fake.release_event.set()
    deadline = time.monotonic() + 3
    while job.status is not BatchJobStatus.PAUSED and time.monotonic() < deadline:
        time.sleep(0.01)
    assert job.status is BatchJobStatus.PAUSED
    assert [path.name for path in fake.calls] == ["0.png"]
    control.resume()
    thread.join(5)
    assert not thread.is_alive()
    assert [path.name for path in fake.calls] == ["0.png", "1.png"]
    assert job.status is BatchJobStatus.COMPLETED


def test_cancel_does_not_start_next_item(tmp_path: Path) -> None:
    _images(tmp_path, 3)
    fake = FakeBatchTaggingService()
    fake.started_event = threading.Event()
    fake.release_event = threading.Event()
    batch, job, _ = create_job(tmp_path, service=fake)
    control = BatchRunControl()
    thread = threading.Thread(
        target=batch.run_job,
        kwargs={"job": job, "control": control},
    )
    thread.start()
    assert fake.started_event.wait(3)
    control.cancel()
    fake.release_event.set()
    thread.join(5)
    assert [path.name for path in fake.calls] == ["0.png"]
    assert [item.status for item in job.items[1:]] == [
        BatchItemStatus.CANCELLED,
        BatchItemStatus.CANCELLED,
    ]
    assert job.status is BatchJobStatus.CANCELLED


class FailOnceWriter(BatchOutputWriter):
    def __init__(self) -> None:
        super().__init__()
        self.fail = True

    def write_analysis(self, item, job, analysis) -> None:
        if self.fail:
            self.fail = False
            raise ExportError("fake export failure")
        super().write_analysis(item, job, analysis)


class FailEveryWriteWriter(BatchOutputWriter):
    def write_analysis(self, item, job, analysis) -> None:
        del item, job, analysis
        raise ExportError("fake export failure")


def test_export_failure_retry_reuses_in_memory_inference(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    fake = FakeBatchTaggingService()
    writer = FailOnceWriter()
    batch = BatchService(fake, writer=writer)  # type: ignore[arg-type]
    job = batch.create_job(
        ScanOptions((tmp_path,)),
        BatchConfig(write_csv=False),
        AppSettings(profile="lora_caption"),
    )
    batch.run_job(job)
    assert job.items[0].status is BatchItemStatus.FAILED
    assert len(fake.calls) == 1
    assert batch.retry_failed(job) == 1
    batch.run_job(job)
    assert job.items[0].status is BatchItemStatus.COMPLETED
    assert len(fake.calls) == 1
    assert batch._analysis_cache == {}


def test_export_retry_cache_is_bounded_for_large_failure_sets(
    tmp_path: Path,
) -> None:
    _images(tmp_path, MAX_RETRY_CACHE_ITEMS + 3)
    fake = FakeBatchTaggingService()
    batch = BatchService(
        fake,  # type: ignore[arg-type]
        writer=FailEveryWriteWriter(),
    )
    job = batch.create_job(
        ScanOptions((tmp_path,)),
        BatchConfig(write_csv=False),
        AppSettings(profile="lora_caption"),
    )
    batch.run_job(job)
    assert len(batch._analysis_cache) == MAX_RETRY_CACHE_ITEMS
    assert job.items[0].id not in batch._analysis_cache
    assert job.items[-1].id in batch._analysis_cache


def test_retry_limit_prevents_infinite_retries(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    fake = FakeBatchTaggingService()
    fake.fail_names.add("one.png")
    batch, job, _ = create_job(
        tmp_path,
        service=fake,
        config=BatchConfig(write_csv=False, max_retries=1),
    )
    batch.run_job(job)
    assert batch.retry_failed(job) == 1
    batch.run_job(job)
    assert batch.retry_failed(job) == 0
    assert job.items[0].retry_count == 1


def test_repeated_start_is_rejected_while_job_is_active(tmp_path: Path) -> None:
    _images(tmp_path, 2)
    fake = FakeBatchTaggingService()
    fake.started_event = threading.Event()
    fake.release_event = threading.Event()
    batch, job, _ = create_job(tmp_path, service=fake)
    second = batch.create_job(
        ScanOptions((tmp_path,)),
        BatchConfig(write_csv=False),
        AppSettings(profile="lora_caption"),
    )
    thread = threading.Thread(target=batch.run_job, args=(job,))
    thread.start()
    assert fake.started_event.wait(3)
    with pytest.raises(BatchConfigurationError):
        batch.run_job(second)
    fake.release_event.set()
    thread.join(5)


def test_completed_items_are_not_inferred_twice(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    batch, job, fake = create_job(tmp_path)
    batch.run_job(job)
    batch.run_job(job)
    assert len(fake.calls) == 1


def test_deselected_item_is_skipped_without_inference(tmp_path: Path) -> None:
    _images(tmp_path, 2)
    batch, job, fake = create_job(tmp_path)
    job.items[0].selected = False
    batch.run_job(job)
    assert job.items[0].status is BatchItemStatus.SKIPPED
    assert [path.name for path in fake.calls] == ["1.png"]


def test_missing_source_is_recorded_and_queue_continues(tmp_path: Path) -> None:
    _images(tmp_path, 2)
    batch, job, fake = create_job(tmp_path)
    job.items[0].source_path.unlink()
    batch.run_job(job)
    assert job.items[0].status is BatchItemStatus.MISSING
    assert job.items[0].error_type is BatchErrorType.MISSING_SOURCE
    assert [path.name for path in fake.calls] == ["1.png"]


def test_actual_run_requires_loaded_model_before_writing(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    fake = FakeBatchTaggingService(loaded=False)
    batch, job, _ = create_job(tmp_path, service=fake)
    with pytest.raises(ModelLoadError):
        batch.run_job(job)
    assert not (tmp_path / "one.txt").exists()
    assert job.manifest_path is not None
    assert not job.manifest_path.exists()


def test_dry_run_never_loads_infers_or_writes(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    fake = FakeBatchTaggingService(loaded=False)
    batch, job, _ = create_job(
        tmp_path,
        service=fake,
        config=BatchConfig(dry_run=True),
    )
    batch.run_job(job)
    assert fake.load_calls == 0
    assert fake.calls == []
    assert not (tmp_path / "one.txt").exists()
    assert job.manifest_path is not None
    assert not job.manifest_path.exists()


def test_item_records_timing_provider_and_completion_metadata(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    batch, job, _fake = create_job(tmp_path)
    batch.run_job(job)
    item = job.items[0]
    assert item.elapsed_ms is not None
    assert item.inference_time_ms == 12.0
    assert item.provider
    assert item.model_name == "fake-model"
    assert item.started_at and item.completed_at


def test_manifest_round_trip_preserves_job_and_item_state(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    _batch, job, _fake = create_job(tmp_path)
    job.status = BatchJobStatus.READY
    store = ManifestStore()
    path = store.save(job)
    loaded = store.load(path, recover=False)
    assert loaded.id == job.id
    assert loaded.settings == job.settings
    assert loaded.items[0].id == job.items[0].id
    assert loaded.items[0].caption_path == job.items[0].caption_path


def test_explicit_recovery_requeues_cancelled_manifest(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    _batch, job, _fake = create_job(tmp_path)
    job.items[0].mark(
        BatchItemStatus.CANCELLED,
        error_type=BatchErrorType.CANCELLED,
        error_message="user cancelled",
    )
    job.status = BatchJobStatus.CANCELLED
    store = ManifestStore()

    loaded = store.load(store.save(job), recover=True)

    assert loaded.resumed_from_manifest
    assert loaded.status is BatchJobStatus.READY
    assert loaded.items[0].status is BatchItemStatus.PENDING


def test_manifest_warns_when_current_semantic_settings_changed(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    _batch, job, _fake = create_job(tmp_path)
    current = replace(
        job.settings,
        profile="pony",
        general_threshold=0.91,
    )
    warnings = ManifestStore().warn_if_settings_changed(job, current)
    assert len(warnings) == 1
    assert "Profile 或阈值" in warnings[0]
    assert warnings[0] in job.warnings
    assert job.settings.profile == "lora_caption"


def test_manifest_update_is_atomic_and_leaves_no_temp(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    _batch, job, _fake = create_job(tmp_path)
    store = ManifestStore()
    path = store.save(job)
    first = path.read_text(encoding="utf-8")
    job.warnings.append("updated")
    store.save(job)
    assert path.read_text(encoding="utf-8") != first
    assert not list(path.parent.glob("*.animetagger.tmp"))


@pytest.mark.parametrize("content", ["{", "[]", '{"schema_version": 999}'])
def test_corrupt_or_incompatible_manifest_is_rejected(
    tmp_path: Path,
    content: str,
) -> None:
    path = tmp_path / "bad.manifest.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(BatchManifestError):
        ManifestStore().load(path)


def test_incomplete_manifest_is_discovered_but_terminal_is_not(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    touch_image(source / "one.png")
    _batch, job, _fake = create_job(
        source,
        config=BatchConfig(
            write_csv=False,
            metadata_dir=tmp_path / "jobs",
        ),
    )
    store = ManifestStore()
    job.status = BatchJobStatus.RUNNING
    incomplete = store.save(job)
    other = replace(job)
    other.id = "terminal"
    other.status = BatchJobStatus.COMPLETED
    other.manifest_path = tmp_path / "jobs" / "terminal.manifest.json"
    store.save(other)
    assert store.discover_incomplete((tmp_path / "jobs",)) == (incomplete,)


def test_recovery_keeps_completed_item_when_output_exists(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    _batch, job, _fake = create_job(tmp_path)
    assert job.items[0].caption_path is not None
    job.items[0].caption_path.write_text("done\n", encoding="utf-8")
    job.items[0].mark(BatchItemStatus.COMPLETED)
    job.status = BatchJobStatus.RUNNING
    store = ManifestStore()
    loaded = store.load(store.save(job))
    assert loaded.items[0].status is BatchItemStatus.COMPLETED
    assert loaded.status is BatchJobStatus.RUNNING


def test_recovery_requeues_completed_item_when_output_disappeared(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    _batch, job, _fake = create_job(tmp_path)
    job.items[0].mark(BatchItemStatus.COMPLETED)
    job.status = BatchJobStatus.RUNNING
    store = ManifestStore()
    loaded = store.load(store.save(job))
    assert loaded.items[0].status is BatchItemStatus.PENDING
    assert loaded.status is BatchJobStatus.READY


def test_recovery_marks_deleted_source_missing(tmp_path: Path) -> None:
    source = touch_image(tmp_path / "one.png")
    _batch, job, _fake = create_job(tmp_path)
    job.status = BatchJobStatus.RUNNING
    store = ManifestStore()
    path = store.save(job)
    source.unlink()
    loaded = store.load(path)
    assert loaded.items[0].status is BatchItemStatus.MISSING
    assert loaded.items[0].error_type is BatchErrorType.MISSING_SOURCE


def test_manifest_contains_paths_not_image_binary(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png", b"\x89PNG fake binary marker")
    _batch, job, _fake = create_job(tmp_path)
    path = ManifestStore().save(job)
    payload = path.read_bytes()
    assert b"fake binary marker" not in payload
    assert b"model.onnx" not in payload


def test_csv_default_utf8_has_no_bom_and_required_columns(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    batch, job, _fake = create_job(
        tmp_path,
        config=BatchConfig(write_csv=True),
    )
    batch.run_job(job)
    assert job.summary_csv_path is not None
    data = job.summary_csv_path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")
    header = data.decode("utf-8").splitlines()[0]
    for field in (
        "source_path",
        "status",
        "model_name",
        "execution_provider",
        "positive_prompt",
        "output_txt",
        "completed_at",
    ):
        assert field in header


def test_csv_bom_option_is_excel_compatible(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    batch, job, _fake = create_job(
        tmp_path,
        config=BatchConfig(write_csv=True, csv_bom=True),
    )
    batch.run_job(job)
    assert job.summary_csv_path is not None
    assert job.summary_csv_path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_csv_uses_standard_quoting_for_comma_quote_and_newline(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    _batch, job, _fake = create_job(tmp_path)
    item = job.items[0]
    item.positive_prompt = 'one, "two"\nthree'
    item.mark(BatchItemStatus.COMPLETED)
    target = tmp_path / "quoted.csv"
    BatchOutputWriter().write_csv(job, target)
    text = target.read_text(encoding="utf-8")
    assert '"one, ""two""\nthree"' in text


def test_csv_success_only_excludes_failed_rows(tmp_path: Path) -> None:
    _images(tmp_path, 2)
    _batch, job, _fake = create_job(
        tmp_path,
        config=BatchConfig(
            write_csv=True,
            csv_success_only=True,
        ),
    )
    job.items[0].mark(BatchItemStatus.COMPLETED)
    job.items[1].mark(BatchItemStatus.FAILED)
    target = tmp_path / "success.csv"
    BatchOutputWriter().write_csv(job, target)
    text = target.read_text(encoding="utf-8")
    assert "0.png" in text
    assert "1.png" not in text


def test_csv_default_does_not_overwrite_existing_report(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    _batch, job, _fake = create_job(tmp_path)
    target = tmp_path / "report.csv"
    target.write_text("old", encoding="utf-8")
    with pytest.raises(ExportError):
        BatchOutputWriter().write_csv(job, target)
    assert target.read_text(encoding="utf-8") == "old"


def test_csv_explicit_overwrite_replaces_existing_report(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    _batch, job, _fake = create_job(
        tmp_path,
        config=BatchConfig(
            write_csv=True,
            overwrite_reports=True,
        ),
    )
    target = tmp_path / "report.csv"
    target.write_text("old", encoding="utf-8")
    BatchOutputWriter().write_csv(job, target)
    assert target.read_text(encoding="utf-8").startswith("source_path,")


def test_summary_json_has_schema_counts_settings_and_items(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    _batch, job, _fake = create_job(tmp_path)
    target = tmp_path / "summary.json"
    BatchOutputWriter().write_summary_json(job, target)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["counts"]["total"] == 1
    assert payload["settings"]["profile"] == "lora_caption"
    assert len(payload["items"]) == 1


def test_job_counts_remain_consistent_across_all_statuses(
    tmp_path: Path,
) -> None:
    _images(tmp_path, 3)
    _batch, job, _fake = create_job(tmp_path)
    job.items[0].mark(BatchItemStatus.COMPLETED)
    job.items[1].mark(BatchItemStatus.FAILED)
    job.items[2].mark(BatchItemStatus.SKIPPED)
    counts = job.counts()
    assert counts["total"] == 3
    assert counts["completed"] == 1
    assert counts["failed"] == 1
    assert counts["skipped"] == 1

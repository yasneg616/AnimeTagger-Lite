"""Fresh real-model batch acceptance using only copied user validation images."""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.batch.exporter import BatchOutputWriter
from app.batch.manifest import ManifestStore
from app.batch.models import (
    BatchConfig,
    BatchItemStatus,
    BatchJob,
    BatchJobStatus,
    BatchTextFormat,
    CaptionPolicy,
    OutputMode,
    ScanOptions,
)
from app.batch.service import BatchRunControl, BatchService
from app.config.settings import AppSettings
from app.errors import ExportError
from app.inference.providers import CPU_PROVIDER, CUDA_PROVIDER, Device
from app.inference.wd14_engine import WD14Engine
from app.services.tagging_service import AnalysisResult, TaggingService


SMOKE_ROOT = PROJECT_ROOT / ".final-release-smoke"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = (
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    )


def _process_memory_mib() -> dict[str, float]:
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessMemoryCounters),
        wintypes.DWORD,
    )
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    process = kernel32.GetCurrentProcess()
    ok = psapi.GetProcessMemoryInfo(
        process,
        ctypes.byref(counters),
        counters.cb,
    )
    if not ok:
        return {}
    scale = 1024.0 * 1024.0
    return {
        "working_set_mib": round(counters.WorkingSetSize / scale, 3),
        "peak_working_set_mib": round(counters.PeakWorkingSetSize / scale, 3),
    }


def _nvidia_snapshot() -> dict[str, object]:
    try:
        gpu = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            timeout=20,
        ).stdout.strip()
        processes = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,used_memory",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            timeout=20,
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return {}
    current_pid = str(os.getpid())
    current_used: int | None = None
    for line in processes:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 2 and parts[0] == current_pid:
            try:
                current_used = int(parts[1])
            except ValueError:
                pass
            break
    name, driver, used, total = [part.strip() for part in gpu.split(",", 3)]
    return {
        "gpu": name,
        "driver": driver,
        "system_used_mib": int(used),
        "total_mib": int(total),
        "process_used_mib": current_used,
    }


class CountingTaggingService(TaggingService):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.analysis_calls = 0
        self.inference_times_ms: list[float] = []

    def analyze_image(
        self,
        image_path: Path,
        settings: AppSettings,
    ) -> AnalysisResult:
        result = super().analyze_image(image_path, settings)
        self.analysis_calls += 1
        self.inference_times_ms.append(
            result.inference.inference_seconds * 1000.0
        )
        return result


class FailOneExportOnce(BatchOutputWriter):
    def __init__(self, target_name: str) -> None:
        super().__init__()
        self.target_name = target_name
        self.failed = False

    def write_analysis(
        self,
        item: object,
        job: BatchJob,
        analysis: AnalysisResult,
    ) -> None:
        if (
            not self.failed
            and getattr(item, "source_path").name == self.target_name
        ):
            self.failed = True
            raise ExportError("受控的一次性真实导出失败")
        super().write_analysis(item, job, analysis)  # type: ignore[arg-type]


def _clean_smoke() -> None:
    resolved = SMOKE_ROOT.resolve(strict=False)
    expected = (PROJECT_ROOT / ".final-release-smoke").resolve(strict=False)
    if resolved != expected or PROJECT_ROOT not in resolved.parents:
        raise RuntimeError(f"Refusing unsafe smoke cleanup: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def _copy_validation_images(validation_dir: Path) -> tuple[Path, ...]:
    supported = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".gif",
        ".tif",
        ".tiff",
        ".heic",
        ".heif",
        ".avif",
    }
    sources = tuple(
        sorted(
            (
                path
                for path in validation_dir.iterdir()
                if path.is_file() and path.suffix.casefold() in supported
            ),
            key=lambda path: path.name.casefold(),
        )
    )
    if not 5 <= len(sources) <= 20:
        raise RuntimeError(
            f"Expected 5 to 20 validation images, found {len(sources)}."
        )
    dataset = SMOKE_ROOT / "dataset 中文 空格"
    copied: list[Path] = []
    for index, source in enumerate(sources, start=1):
        parent = dataset if index <= 3 else dataset / "子目录"
        parent.mkdir(parents=True, exist_ok=True)
        target = parent / f"验收 图 {index}{source.suffix.casefold()}"
        shutil.copy2(source, target)
        copied.append(target)
    return tuple(copied)


def _settings(
    model_dir: Path,
    variant: str,
    *,
    profile: str = "lora_caption",
    trigger: str | None = "release_token",
    trigger_position: str = "first",
    negative_mode: str = "none",
) -> AppSettings:
    return AppSettings(
        model_dir=str(model_dir),
        device=variant,
        profile=profile,
        add_profile_prefix=profile != "lora_caption",
        negative_mode=negative_mode,
        negative_preset="basic",
        trigger_word=trigger,
        trigger_word_position=trigger_position,
        include_rating=False,
    )


def _job(
    batch: BatchService,
    roots: tuple[Path, ...],
    scenario: str,
    settings: AppSettings,
    *,
    recursive: bool = True,
    mode: OutputMode = OutputMode.MIRROR,
    policy: CaptionPolicy = CaptionPolicy.SKIP,
    text_format: BatchTextFormat = BatchTextFormat.TXT,
    dry_run: bool = False,
    write_json: bool = True,
    write_csv: bool = True,
    write_summary: bool = True,
    max_retries: int = 1,
) -> BatchJob:
    output = SMOKE_ROOT / "outputs" / scenario
    metadata = SMOKE_ROOT / "metadata" / scenario
    config = BatchConfig(
        output_mode=mode,
        output_root=None if mode is OutputMode.BESIDE else output,
        caption_policy=policy,
        text_format=text_format,
        write_captions=True,
        write_json=write_json,
        write_csv=write_csv,
        write_summary_json=write_summary,
        metadata_dir=metadata,
        dry_run=dry_run,
        manifest_every=1,
        max_retries=max_retries,
    )
    return batch.create_job(
        ScanOptions(roots, recursive=recursive, output_root=config.output_root),
        config,
        settings,
    )


def _run_in_thread(
    batch: BatchService,
    job: BatchJob,
    control: BatchRunControl,
    on_item: object,
) -> threading.Thread:
    errors: list[BaseException] = []

    def target() -> None:
        try:
            batch.run_job(
                job,
                control=control,
                on_item=on_item,  # type: ignore[arg-type]
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=target, name=f"acceptance-{job.id}")
    thread.errors = errors  # type: ignore[attr-defined]
    thread.start()
    return thread


def _join_thread(thread: threading.Thread, timeout: float = 120.0) -> None:
    thread.join(timeout)
    if thread.is_alive():
        raise RuntimeError(f"Batch acceptance thread did not stop: {thread.name}")
    errors = getattr(thread, "errors", [])
    if errors:
        raise errors[0]


def _wait_for(predicate: object, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():  # type: ignore[operator]
            return
        time.sleep(0.02)
    raise RuntimeError("Timed out waiting for batch state.")


def _single_image_copy(source: Path, scenario: str) -> Path:
    parent = SMOKE_ROOT / "single-policy" / scenario
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / f"策略 图片{source.suffix.casefold()}"
    shutil.copy2(source, target)
    return target


def run_acceptance(
    *,
    variant: str,
    model_dir: Path,
    validation_dir: Path,
) -> dict[str, object]:
    _clean_smoke()
    SMOKE_ROOT.mkdir(parents=True)
    source_hashes = {
        path.name: sha256_file(path)
        for path in validation_dir.iterdir()
        if path.is_file()
    }
    copied = _copy_validation_images(validation_dir)
    copied_initial = {str(path): sha256_file(path) for path in copied}
    dataset = copied[0].parent
    if dataset.name != "dataset 中文 空格":
        dataset = dataset.parent

    session_creations = 0

    def engine_factory(*args: object, **kwargs: object) -> WD14Engine:
        nonlocal session_creations
        session_creations += 1
        return WD14Engine(*args, **kwargs)  # type: ignore[arg-type]

    tagging = CountingTaggingService(engine_factory=engine_factory)
    requested_device = Device.CPU if variant == "cpu" else Device.CUDA
    expected_provider = CPU_PROVIDER if variant == "cpu" else CUDA_PROVIDER
    memory_before_load = _process_memory_mib()
    gpu_before_load = _nvidia_snapshot() if variant == "cuda" else {}
    load_started = time.perf_counter()
    info = tagging.load_model(model_dir, requested_device)
    model_load_ms = (time.perf_counter() - load_started) * 1000.0
    memory_after_load = _process_memory_mib()
    gpu_after_load = _nvidia_snapshot() if variant == "cuda" else {}
    if info.active_provider != expected_provider:
        raise RuntimeError(
            f"Expected {expected_provider}, got {info.active_provider}."
        )
    if session_creations != 1:
        raise RuntimeError(f"Expected one initial Session, got {session_creations}.")

    batch = BatchService(tagging)
    base_settings = _settings(model_dir, variant)
    non_recursive = batch.scan(ScanOptions((dataset,), recursive=False))
    recursive = batch.scan(ScanOptions((dataset,), recursive=True))
    if len(non_recursive.items) != 3 or len(recursive.items) != len(copied):
        raise RuntimeError(
            f"Scan counts mismatch: {len(non_recursive.items)} / {len(recursive.items)}"
        )

    dry_job = _job(
        batch,
        (dataset,),
        "dry-run",
        base_settings,
        dry_run=True,
    )
    calls_before_dry = tagging.analysis_calls
    batch.run_job(dry_job)
    if tagging.analysis_calls != calls_before_dry:
        raise RuntimeError("Dry-run unexpectedly performed inference.")
    if (SMOKE_ROOT / "outputs" / "dry-run").exists():
        raise RuntimeError("Dry-run unexpectedly created its output root.")

    pause_job = _job(batch, (dataset,), "pause-resume", base_settings)
    pause_control = BatchRunControl()
    first_done = threading.Event()

    def pause_after_first(item: object, _position: int, _total: int) -> None:
        if (
            getattr(item, "status") is BatchItemStatus.COMPLETED
            and not first_done.is_set()
        ):
            pause_control.pause()
            first_done.set()

    pause_thread = _run_in_thread(
        batch, pause_job, pause_control, pause_after_first
    )
    if not first_done.wait(30):
        raise RuntimeError("Pause scenario did not finish its first item.")
    _wait_for(lambda: pause_job.status is BatchJobStatus.PAUSED)
    completed_while_paused = pause_job.counts()["completed"]
    time.sleep(0.3)
    if pause_job.counts()["completed"] != completed_while_paused:
        raise RuntimeError("A new image started while the job was paused.")
    pause_control.resume()
    _join_thread(pause_thread)
    if pause_job.counts()["completed"] != len(copied):
        raise RuntimeError("Pause/resume scenario did not complete every image.")

    cancel_job = _job(batch, (dataset,), "cancel-recover", base_settings)
    cancel_control = BatchRunControl()
    cancel_requested = threading.Event()

    def cancel_after_first(item: object, _position: int, _total: int) -> None:
        if (
            getattr(item, "status") is BatchItemStatus.COMPLETED
            and not cancel_requested.is_set()
        ):
            cancel_control.cancel()
            cancel_requested.set()

    cancel_thread = _run_in_thread(
        batch, cancel_job, cancel_control, cancel_after_first
    )
    _join_thread(cancel_thread)
    cancel_counts = cancel_job.counts()
    if cancel_counts["completed"] != 1 or cancel_counts["cancelled"] != len(copied) - 1:
        raise RuntimeError(f"Cancel counts mismatch: {cancel_counts}")
    assert cancel_job.manifest_path is not None
    recovered = ManifestStore().load(cancel_job.manifest_path, recover=True)
    if not recovered.resumed_from_manifest:
        raise RuntimeError("Cancelled Manifest was not marked as recovered.")
    recovered.config = replace(recovered.config, overwrite_reports=True)
    batch.run_job(recovered)
    if recovered.counts()["completed"] != len(copied):
        raise RuntimeError("Recovered cancelled job did not complete.")

    target_failure = copied[-1].name
    failing_batch = BatchService(
        tagging,
        writer=FailOneExportOnce(target_failure),
    )
    retry_job = _job(
        failing_batch,
        (dataset,),
        "retry-flat",
        base_settings,
        mode=OutputMode.FLAT,
    )
    failing_batch.run_job(retry_job)
    if retry_job.counts()["failed"] != 1:
        raise RuntimeError("Controlled export failure did not create one failed item.")
    calls_before_retry = tagging.analysis_calls
    if failing_batch.retry_failed(retry_job) != 1:
        raise RuntimeError("Failed item was not reset for retry.")
    failing_batch.run_job(retry_job)
    if retry_job.counts()["completed"] != len(copied):
        raise RuntimeError("Retry did not complete the failed item.")
    if tagging.analysis_calls != calls_before_retry:
        raise RuntimeError("Export-only retry repeated real model inference.")

    policy_results: dict[str, str] = {}
    for policy in CaptionPolicy:
        source = _single_image_copy(copied[0], policy.value)
        policy_settings = base_settings
        policy_batch = BatchService(tagging)
        job = _job(
            policy_batch,
            (source,),
            f"policy-{policy.value}",
            policy_settings,
            recursive=False,
            mode=OutputMode.BESIDE,
            policy=policy,
            write_json=False,
            write_csv=False,
            write_summary=False,
        )
        caption = job.items[0].caption_path
        assert caption is not None
        caption.write_text("manual_tag, keep_me\n", encoding="utf-8")
        policy_batch.run_job(job)
        policy_results[policy.value] = job.items[0].status.value
        if policy is CaptionPolicy.SKIP:
            if caption.read_text(encoding="utf-8") != "manual_tag, keep_me\n":
                raise RuntimeError("Skip policy modified an existing caption.")
        elif policy is CaptionPolicy.BACKUP_AND_OVERWRITE:
            if job.items[0].backup_path is None or not job.items[0].backup_path.is_file():
                raise RuntimeError("Backup policy did not preserve the old caption.")
        elif policy in {CaptionPolicy.APPEND_TRIGGER, CaptionPolicy.MERGE}:
            text = caption.read_text(encoding="utf-8")
            if text.casefold().count("release_token") != 1:
                raise RuntimeError(f"{policy.value} duplicated or lost trigger word.")

    trigger_results: dict[str, str] = {}
    for position in ("first", "last"):
        source = _single_image_copy(copied[1], f"trigger-{position}")
        settings = _settings(
            model_dir,
            variant,
            trigger_position=position,
        )
        trigger_batch = BatchService(tagging)
        job = _job(
            trigger_batch,
            (source,),
            f"trigger-{position}",
            settings,
            recursive=False,
            mode=OutputMode.BESIDE,
            policy=CaptionPolicy.OVERWRITE,
            write_json=False,
            write_csv=False,
            write_summary=False,
        )
        trigger_batch.run_job(job)
        caption = job.items[0].caption_path
        assert caption is not None
        terms = [term.strip() for term in caption.read_text(encoding="utf-8").split(",")]
        expected_index = 0 if position == "first" else -1
        if terms[expected_index] != "release_token":
            raise RuntimeError(f"Trigger word was not {position}.")
        trigger_results[position] = "passed"

    prompt_source = _single_image_copy(copied[2], "prompt-txt")
    prompt_settings = _settings(
        model_dir,
        variant,
        profile="anime",
        trigger=None,
        negative_mode="basic",
    )
    prompt_batch = BatchService(tagging)
    prompt_job = _job(
        prompt_batch,
        (prompt_source,),
        "prompt-txt",
        prompt_settings,
        recursive=False,
        mode=OutputMode.BESIDE,
        policy=CaptionPolicy.OVERWRITE,
        text_format=BatchTextFormat.PROMPT_TXT,
        write_json=True,
        write_csv=False,
        write_summary=False,
    )
    prompt_batch.run_job(prompt_job)
    prompt_caption = prompt_job.items[0].caption_path
    assert prompt_caption is not None
    prompt_text = prompt_caption.read_text(encoding="utf-8")
    if "Positive:" not in prompt_text or "Negative:" not in prompt_text:
        raise RuntimeError("Positive/negative batch TXT is incomplete.")

    batch_session_creations = session_creations
    if batch_session_creations != 1:
        raise RuntimeError(
            f"Batch acceptance created {batch_session_creations} Sessions, expected 1."
        )
    memory_after_batch = _process_memory_mib()
    gpu_after_batch = _nvidia_snapshot() if variant == "cuda" else {}
    tagging.unload_model()
    memory_after_release = _process_memory_mib()
    gpu_after_release = _nvidia_snapshot() if variant == "cuda" else {}
    reload_started = time.perf_counter()
    reloaded = tagging.load_model(model_dir, requested_device)
    model_reload_ms = (time.perf_counter() - reload_started) * 1000.0
    if reloaded.active_provider != expected_provider or session_creations != 2:
        raise RuntimeError("Model reload did not create the expected real Provider Session.")
    tagging.analyze_image(copied[0], base_settings)
    tagging.unload_model()

    source_final = {
        path.name: sha256_file(path)
        for path in validation_dir.iterdir()
        if path.is_file()
    }
    copied_final = {str(path): sha256_file(path) for path in copied}
    if source_final != source_hashes or copied_final != copied_initial:
        raise RuntimeError("Original or copied validation image hashes changed.")
    temporary = tuple(SMOKE_ROOT.rglob("*.animetagger.tmp")) + tuple(
        SMOKE_ROOT.rglob("*.part")
    )
    if temporary:
        raise RuntimeError(f"Temporary files remain: {temporary[:10]!r}")
    live_acceptance_threads = tuple(
        thread.name
        for thread in threading.enumerate()
        if thread.name.startswith("acceptance-")
    )
    if live_acceptance_threads:
        raise RuntimeError(f"Acceptance threads remain: {live_acceptance_threads!r}")

    timings = tagging.inference_times_ms
    return {
        "status": "passed",
        "variant": variant,
        "provider": expected_provider,
        "model_load_ms": round(model_load_ms, 3),
        "model_reload_ms": round(model_reload_ms, 3),
        "session_count_during_batch": batch_session_creations,
        "session_count_after_explicit_reload": session_creations,
        "real_prediction_calls": tagging.analysis_calls,
        "first_inference_ms": round(timings[0], 3),
        "subsequent_average_ms": round(sum(timings[1:]) / len(timings[1:]), 3),
        "process_memory": {
            "before_load": memory_before_load,
            "after_load": memory_after_load,
            "after_batch": memory_after_batch,
            "after_release": memory_after_release,
        },
        "gpu_memory": {
            "before_load": gpu_before_load,
            "after_load": gpu_after_load,
            "after_batch": gpu_after_batch,
            "after_release": gpu_after_release,
        },
        "images": len(copied),
        "non_recursive": len(non_recursive.items),
        "recursive": len(recursive.items),
        "dry_run": "passed",
        "pause": "passed",
        "resume": "passed",
        "cancel": cancel_counts,
        "manifest_recovery": "passed",
        "retry_without_reinference": "passed",
        "caption_policies": policy_results,
        "output_modes": [mode.value for mode in OutputMode],
        "trigger_positions": trigger_results,
        "positive_negative_txt": "passed",
        "json": "passed",
        "csv": "passed",
        "manifest": "passed",
        "source_hashes_unchanged": True,
        "copy_hashes_unchanged": True,
        "temporary_files": 0,
        "residual_threads": 0,
        "completed_at_utc": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--validation-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--keep", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report_path = args.report.resolve(strict=False)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = run_acceptance(
            variant=args.variant,
            model_dir=args.model_dir.resolve(strict=True),
            validation_dir=args.validation_dir.resolve(strict=True),
        )
    except Exception as exc:
        report_path.write_text(
            json.dumps(
                {
                    "status": "failed",
                    "variant": args.variant,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        raise
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not args.keep:
        _clean_smoke()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

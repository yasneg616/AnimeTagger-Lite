"""Extract and exercise a bundled-model portable ZIP without developer PATH."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix="AnimeTagger-backend-smoke-"))
    with zipfile.ZipFile(args.archive) as archive:
        archive.extractall(work)
    roots = list(work.glob("*/AnimeTaggerLite.exe"))
    assert len(roots) == 1, "Expected exactly one portable application"
    cli = roots[0]
    portable = cli.parent
    manifest = json.loads((portable / "BUILD-MANIFEST.json").read_text(encoding="utf-8"))
    cli_command = [str(cli), "--cli"] if manifest.get("program_layout") == "onefile" else [str(portable / "AnimeTaggerLiteCLI.exe")]
    assert manifest["model_included"]
    for relative, digest in manifest["model_sha256"].items():
        with (portable / relative).open("rb") as handle:
            assert hashlib.file_digest(handle, "sha256").hexdigest() == digest, relative
    system = Path(os.environ.get("SystemRoot", "C:/Windows"))
    env = {"SystemRoot": str(system), "WINDIR": str(system),
           "PATH": os.pathsep.join([str(system / "System32"), str(system)]),
           "TEMP": str(work), "TMP": str(work), "USERPROFILE": str(work),
           "QT_QPA_PLATFORM": "offscreen", "HF_HUB_OFFLINE": "1"}
    results = {"portable": str(portable), "source_cwd": False,
               "developer_python_path": False, "model_hashes": "passed", "backends": {}}
    for backend in manifest["tagger_backends"]:
        output = work / f"{backend}.json"
        device = "cpu" if backend == "wd_2026_canary" else "cuda"
        command = [*cli_command, str(args.image.resolve()), "--tagger-backend", backend,
                   "--device", device, "--profile", "cyberillustrious_semireal",
                   "--output-format", "json", "--output", str(output)]
        process = subprocess.run(command, cwd=work, env=env, capture_output=True, timeout=360)
        (work / f"{backend}.stdout.txt").write_bytes(process.stdout)
        (work / f"{backend}.stderr.txt").write_bytes(process.stderr)
        if process.returncode:
            raise RuntimeError(f"{backend} exited {process.returncode}; inspect {work}")
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["backend"] == backend
        assert payload["positive_prompt"]
        assert Path(payload["model_path"]).is_relative_to(portable)
        expected = "PyTorch CPU" if device == "cpu" else "CUDAExecutionProvider"
        assert payload["execution_provider"] == expected, payload["execution_provider"]
        results["backends"][backend] = {"provider": expected, "json_export": "passed"}
        print(f"{backend}: passed ({expected})", flush=True)
    gui = subprocess.run([str(portable / "AnimeTaggerLite.exe"), "--smoke-test"],
                         cwd=work, env=env, capture_output=True, timeout=180)
    assert gui.returncode == 0, f"GUI exited {gui.returncode}"
    results["gui_startup"] = "passed"
    results["status"] = "passed"
    args.report.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Portable smoke passed: {args.report}")


if __name__ == "__main__":
    main()

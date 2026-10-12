"""Verify frozen prompt code and offline semantic resources against this checkout."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import CodeType

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(code):
    if isinstance(code, CodeType):
        return (code.co_code, tuple(fingerprint(value) for value in code.co_consts),
                code.co_names, code.co_varnames, code.co_freevars, code.co_cellvars,
                code.co_argcount, code.co_posonlyargcount, code.co_kwonlyargcount,
                code.co_nlocals, code.co_stacksize, code.co_flags, code.co_exceptiontable)
    return code


def verify(portable, output):
    executable = portable / 'AnimeTaggerLite.exe'
    archive = CArchiveReader(str(executable))
    embedded = next(name for name in archive.toc if name.startswith('PYZ'))
    pyz = archive.open_embedded_archive(embedded)
    matches = {}
    for module in ('app.prompts.semantic_catalog', 'app.prompts.semantic_prompt',
                   'app.prompts.semantic_scene', 'app.prompts.semantic_rules',
                   'app.prompts.random_prompt', 'app.prompts.injection',
                   'app.ui.semantic_prompt_panel', 'app.ui.random_prompt_panel',
                   'app.ui.semantic_prompt_smoke', 'app.ui.application'):
        source = ROOT.joinpath(*module.split('.')).with_suffix('.py')
        matches[module] = fingerprint(pyz.extract(module)) == fingerprint(compile(source.read_bytes(), str(source), 'exec', dont_inherit=True))
    for name in ('catalog.json', 'coverage.json', 'coverage.tsv'):
        original = ROOT / 'resources/prompt_semantics' / name
        packaged = portable / 'resources/prompt_semantics' / name
        matches[name] = original.read_bytes() == packaged.read_bytes()
    coverage = json.loads((portable / 'resources/prompt_semantics/coverage.json').read_bytes())
    report = {'source_equals_frozen': matches,
              'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
              'catalog_sha256': hashlib.sha256((portable / 'resources/prompt_semantics/catalog.json').read_bytes()).hexdigest(),
              'coverage_gate_complete': coverage['minimum_met'], 'usable_reviewed': coverage['usable_reviewed']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if all(matches.values()) and report['coverage_gate_complete'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portable', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'validation/semantic-portable-expanded-integrity.json')
    args = parser.parse_args()
    return verify(args.portable.resolve(), args.output.resolve())


if __name__ == '__main__':
    raise SystemExit(main())

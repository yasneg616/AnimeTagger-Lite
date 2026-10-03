from dataclasses import FrozenInstanceError
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from app.inference.model_loader import TagCategory
from app.prompts.normalizer import canonical_tag_key
from app.runtime_paths import RESOURCE_DIR
from app.tag_visuals import SEMANTIC_STATUSES, STATUSES, TagVisualLibrary


@pytest.fixture(scope="module")
def library():
    result = TagVisualLibrary()
    assert result.available
    return result


@pytest.mark.parametrize("name", ["blue_hair", " BLUE   HAIR ", "Blue_Hair"])
def test_lookup_uses_existing_normalization(library, name):
    visual = library.lookup(name, TagCategory.GENERAL)
    assert visual.key == "blue hair"
    assert visual.label_zh == "蓝色头发"
    assert visual.recipe["color"] == "#579bd4"


def test_category_is_part_of_identity_and_characters_are_excluded(library):
    assert library.lookup("chocobo", TagCategory.CHARACTER).status == "excluded_character"
    assert library.lookup("chocobo", TagCategory.GENERAL).status != "excluded_character"
    assert library.lookup("blue_hair", TagCategory.COPYRIGHT).status == "category_only"
    assert library.lookup("general", TagCategory.RATING).group == "rating"
    assert library.lookup("general", TagCategory.GENERAL).status == "pending"
    assert library.lookup("blue_hair", TagCategory.RATING).status == "pending"


def test_descriptors_are_immutable_and_do_not_own_business_tags(library):
    visual = library.lookup("green_eyes")
    with pytest.raises(TypeError):
        visual.recipe["color"] = "#123456"
    with pytest.raises(FrozenInstanceError):
        visual.label_zh = "changed"


@pytest.mark.parametrize("name,label", [
    ("striped_purple_shirt", "条纹紫色衬衫"),
    ("holding_blue_umbrella", "手持蓝色雨伞"),
    ("tattoo_on_shoulder", "纹身在肩膀"),
    ("hand_on_another's_shoulder", "手放在他人的肩膀"),
    ("black-trimmed_dress", "黑色边饰连衣裙"),
])
def test_bounded_rules_support_new_manual_tags(library, name, label):
    visual = library.lookup(name)
    assert visual.semantic and visual.status == "composed"
    assert visual.label_zh == label


def test_unknown_words_do_not_match_by_substring(library):
    visual = library.lookup("unreviewed_modifier_hair")
    assert visual.status == "pending" and not visual.has_icon
    assert visual.group == "hair" and visual.reason
    assert library.lookup("imaginary_ear_ribbon_machine").status == "pending"
    assert library.lookup("hair_ribbon").group == "clothing"
    assert library.lookup("red_smile").status == "pending"


def test_unavailable_resources_degrade_with_a_log(tmp_path, caplog):
    visual = TagVisualLibrary(tmp_path / "missing").lookup("blue_hair")
    assert visual.status == "pending" and not visual.has_icon
    assert "保留" in visual.reason
    assert "资源不可用" in caplog.text


@pytest.mark.parametrize("filename", ["rules.json", "catalog.json", "primitives.json"])
def test_corrupt_json_is_a_display_failure(tmp_path, caplog, filename):
    target = tmp_path / "visuals"
    shutil.copytree(RESOURCE_DIR / "tag_visuals", target)
    (target / filename).write_text("{broken", encoding="utf-8")
    library = TagVisualLibrary(target)
    assert not library.available
    assert not library.lookup("white_shirt").has_icon
    assert "继续显示原英文标签" in caplog.text


def test_ledger_contains_each_real_model_tag_and_presets(library):
    directory = RESOURCE_DIR / "tag_visuals"
    ledger = list(csv.DictReader((directory / "coverage.tsv").open(encoding="utf-8"), delimiter="\t"))
    keys = {r["key"] for r in ledger}
    assert len(keys) == len(ledger)
    report = json.loads((directory / "coverage.json").read_text(encoding="utf-8"))
    model_sources = {Path(r['path']).parent.name for r in report['source_files']}
    expected = {r['key']:int(r['count']) for r in ledger if r['category']=='general' and any(s in model_sources for s in r['sources'].split('; '))}
    actual_counts = {}
    paths = list((RESOURCE_DIR.parent / "models").glob("*/selected_tags.csv"))
    for path in paths:
        for row in csv.DictReader(path.open(encoding="utf-8-sig")):
            if row["category"] == "0":
                key = "general:"+canonical_tag_key(row["name"])
                count = int(row.get("count") or 0)
                actual_counts[key] = max(actual_counts.get(key, count), count)
    if len(paths) == 3:
        assert expected == actual_counts
    assert len(expected) == 12030
    assert expected.keys() <= keys
    for row in ledger:
        assert row["status"] in STATUSES
        assert row["reference"]
        if row["status"] == "pending":
            assert row["reason"]
        elif row["status"] != "excluded_character":
            assert row["label_zh"] and row["explanation_zh"] and row["visual_method"]
    top = sorted(expected, key=lambda key: (-expected[key], key))[:1000]
    covered = sum(library.entries[key].semantic for key in top)
    assert covered >= 950
    assert report["top_1000"]["semantic"] == covered
    assert report["model_general_tags"] == len(expected)
    assert sum(report["model_general_statuses"].values()) == len(expected)
    for tags in json.loads((RESOURCE_DIR / "negative_presets.json").read_text(encoding="utf-8"))["presets"].values():
        assert all("general:"+canonical_tag_key(name) in keys for name in tags)


def test_every_descriptor_is_a_valid_status_and_shape(library):
    shapes = json.loads((library.directory / "primitives.json").read_text(encoding="utf-8"))["shapes"]
    for identity, visual in library.entries.items():
        assert identity == visual.category+":"+visual.key
        assert visual.status in STATUSES
        if visual.has_icon:
            assert visual.recipe["shape"] in shapes
        if visual.status in SEMANTIC_STATUSES:
            assert visual.semantic


def test_lookup_module_remains_qt_free():
    root = RESOURCE_DIR.parent
    result = subprocess.run([sys.executable, "-c", "import sys; from app.tag_visuals import lookup; "
                             "assert lookup('blue_hair').semantic; "
                             "assert not any(x.startswith('PySide6') for x in sys.modules)"],
                            cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr

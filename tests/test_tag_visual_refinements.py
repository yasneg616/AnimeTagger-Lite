import hashlib
import json
import xml.etree.ElementTree as ET

import pytest

from app.tag_visual_svg import compose_svg
from app.tag_visuals import TagVisualLibrary


@pytest.fixture(scope='module')
def library():
    return TagVisualLibrary()


def test_registered_redraws_are_available_in_every_preview_mode(library):
    registered = json.loads((library.directory / 'refinements.json').read_text(encoding='utf-8'))['entries']
    actual = {key for key,visual in library.entries.items() if (visual.recipe or {}).get('refinement') == 'r1'}
    assert actual == set(registered)
    assert len(actual) == 77
    for key in actual:
        visual = library.entries[key]
        assert visual.has_icon and visual.category == 'general'
        for ink,paper in (('#263443','#f5f6fa'),('#e6edf7','#202b3d')):
            for preview in (False,True):
                svg = compose_svg(visual,library.directory,ink=ink,paper=paper,preview=preview)
                ET.fromstring(svg)
                assert '{' not in svg
                # Qt SVG Tiny must receive trimmed geometry, not unsupported clips.
                assert 'clipPath' not in svg


@pytest.mark.parametrize('name,expected', [
    ('green_tail','007c62b7f9543834f8ed346fe728e8f36cfc6db3412c8b555113bc9c641c6e08'),
    ('sandals','5bb8fa3cf76d2dd02c6569e3b464ee682e46ca40016a2ab03788398adb0fd32d'),
    ('blue_slippers','dbd1b39f0c7cd2b91e2aff9cd9bf518a89684c90be6b21b6074a3d4dbd5d3e89'),
    ('black_shirt','096bb526daa2dc46402328b6ec3be0ff3c4b63c1d36eb28444484a6b61adf761'),
    ('white_socks','ed05c860d738240340e931f1ae618c747ea19f4e2d45b7461a4b9f71e577f435'),
    ('fox_ears','e5c75f7f2f70c89f920ccb66218692daa2576fad0fd110f56613634cee597352'),
    ('flower','f8be6aad32ab30091244e7fe0470f5915cfaed56b79ae93f6e7b16ad328d82a5'),
    ('blue_hair','2c3c6303f217e306e356f230754633c8d21079b9fa3049bee89b336abd18b35f'),
])
def test_unselected_illustrations_keep_their_original_drawing(library,name,expected):
    visual = library.lookup(name)
    assert not visual.recipe.get('refinement')
    assert hashlib.sha256(compose_svg(visual,library.directory).encode()).hexdigest() == expected


@pytest.mark.parametrize('first,second', [
    ('tail','crescent_moon'),('rabbit_tail','red_moon'),('fox_tail','wolf_tail'),
    ('black_sandals','black_slippers'),('slippers','unworn_slippers'),
    ('salute','arms_up'),('clenched_hands','index_finger_raised'),
    ('short_tail','long_tail'),('nurse_cap','newsboy_cap'),
])
def test_confusing_tag_pairs_have_different_drawings(library,first,second):
    assert compose_svg(library.lookup(first),library.directory) != compose_svg(library.lookup(second),library.directory)


import json

import pytest

from scripts.build_prompt_semantics import character_profile
from scripts.fetch_prompt_semantics import Client, write_json


def test_relationship_acquisition_resumes_and_never_counts_failed_page(tmp_path):
    client = Client(tmp_path)
    write_json(tmp_path / "tag_aliases.json", {"rows": [{"id": 80}], "cursor": 80, "complete": False})
    requests = []
    def get(resource, params):
        requests.append(params.copy())
        return [{"id": 50}] if len(requests) == 1 else []
    client.get = get
    assert len(client.relationships("tag_aliases")) == 2
    assert requests[0]["page"] == "b80" and requests[1]["page"] == "b50"
    requests.clear()
    assert len(client.relationships("tag_aliases")) == 2 and requests == []


def test_wiki_results_must_match_the_requested_titles(tmp_path):
    client = Client(tmp_path)
    client.get = lambda *args: [{"title": "unrelated_page"}]
    with pytest.raises(ValueError, match="unrelated"):
        client.wiki_batch(["blue_hair"])


def test_group_resume_discovers_children_from_cached_index(tmp_path):
    client = Client(tmp_path)
    write_json(tmp_path / "groups.json", {"pages": {"tag_groups": {"body": "* [[tag group:hair]]"}}, "checked": ["tag_groups"]})
    client.wiki_batch = lambda names: [{"title": name, "body": ""} for name in names]
    state = client.groups()
    assert "tag_group:hair" in state["pages"]


def test_cached_api_data_never_contacts_network(tmp_path, monkeypatch):
    import hashlib
    import urllib.parse
    import urllib.request
    params = {"limit": 1}
    url = "https://danbooru.donmai.us/wiki_pages.json?" + urllib.parse.urlencode(params)
    write_json(tmp_path / "requests" / (hashlib.sha256(url.encode()).hexdigest() + ".json"), {"data": [{"title": "blue_hair"}]})
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: pytest.fail("Unexpected network"))
    assert Client(tmp_path).get("wiki_pages", params) == [{"title": "blue_hair"}]


def test_character_profile_requires_own_unambiguous_appearance_and_never_guesses_age():
    source = {"body": "She has [[long hair]], [[blue hair]] and [[green eyes]].", "updated_at": "2026-10-10"}
    profile = character_profile("alice", source, {"alice": ["work"]}, {})
    assert profile["age_state"] == "unknown"
    assert profile["identity"]["hair.color"] == "blue_hair"
    assert profile["copyrights"] == ["work"]
    assert character_profile("alice", {"body": "She has [[blue hair]] or [[red hair]] and [[green eyes]]."}, {}, {}) is None
    assert character_profile("alice", {"body": "Her sister has [[blue hair]] and [[green eyes]]."}, {}, {}) is None


def test_literal_character_subject_and_introductory_appearance_are_supported():
    source = {"body": "Alice has [[blue hair]] and [[green eyes]]. She wears a dress."}
    assert character_profile("alice", source, {}, {})["identity"]["hair.color"] == "blue_hair"
    source = {"body": "A young girl with [[blonde hair]] and [[green eyes]]."}
    assert character_profile("alice", source, {}, {})["gender"] == "female"
    for body in ("Alice's sister has [[blue hair]] and [[green eyes]]. She wears a dress.",
                 "A girl with [[blue hair]] or [[red hair]] and [[green eyes]]."):
        assert character_profile("alice", {"body": body}, {}, {}) is None

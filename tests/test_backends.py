from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app.config.settings import AppSettings, load_settings, save_settings
from app.errors import AnimeTaggerError, ConfigurationError, InferenceError, ModelLoadError
from app.inference.backends import (BACKENDS, DEFAULT_BACKEND, PixAiTaggerBackend,
    create_backend, normalize_predictions, resolve_backend_files)
from app.inference.model_loader import TagCategory, TagMetadata
from app.inference.providers import Device
from app.inference.wd14_engine import TagPrediction
from app.main import build_parser, _settings_from_args
from app.services.tagging_service import TaggingService
from tests.test_wd14_engine import FakeRuntime, FakeNode


def prediction(name, score, category=TagCategory.GENERAL, index=0):
    return TagPrediction(TagMetadata(index, index, name, 0, category), score)


def test_defaults_and_old_config(tmp_path):
    assert AppSettings().backend == DEFAULT_BACKEND
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"model_dir": "old-model", "general_threshold": 0.42}))
    settings = load_settings(user_path=old)
    assert settings.backend == DEFAULT_BACKEND
    assert settings.model_dir == "old-model"
    assert settings.general_threshold == 0.42


@pytest.mark.parametrize("backend", BACKENDS)
def test_backend_defaults_and_interface(backend, tmp_path):
    settings = AppSettings.from_mapping({"backend": backend})
    spec = BACKENDS[backend]
    assert settings.general_threshold == spec.general_threshold
    assert settings.top_k == spec.top_k
    engine = create_backend(backend, tmp_path)
    assert engine.metadata() == spec
    assert TagCategory.GENERAL in engine.supported_groups()
    assert not engine.is_loaded
    engine.unload()
    with pytest.raises(AnimeTaggerError) as exc:
        engine.load()
    assert "selected_tags.csv" in str(exc.value)


def test_roundtrip_backend_paths_and_overrides(tmp_path):
    settings = AppSettings.from_mapping({"backend": "pixai_v0_9", "general_threshold": 0.4, "top_k": 16, "model_dir": "pixai-local"})
    settings = settings.select_backend("wd_v3").select_backend("pixai_v0_9")
    assert settings.general_threshold == 0.4
    assert settings.model_dir == "pixai-local"
    save_settings(settings, user_path=tmp_path / "settings.json")
    assert load_settings(user_path=tmp_path / "settings.json") == settings
    assert settings.to_filter_settings().max_tags == 16


def test_user_backend_changes_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"backend":"pixai_v0_9"}')
    settings = load_settings(user_path=path)
    assert settings.general_threshold == 0.3
    assert settings.top_k == 128


@pytest.mark.parametrize("values", [{"backend": "bad"}, {"backend": []}, {"top_k": 0}, {"top_k": True}, {"general_threshold": float("nan")}, {"backend_options": {"wd_v3": {"top_k": -1}}}])
def test_invalid_configuration(values):
    with pytest.raises(ConfigurationError):
        AppSettings.from_mapping(values)


def test_normalization_deduplicates_and_groups():
    values = normalize_predictions([prediction(" long hair ", .2), prediction("long_hair", .9),
                                    prediction("hero", .8, TagCategory.CHARACTER)])
    assert [p.tag.name for p in values] == ["long_hair", "hero"]
    assert type(values[0].confidence) is float


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1])
def test_reject_invalid_scores(score):
    with pytest.raises(InferenceError):
        normalize_predictions([prediction("tag", score)])


@pytest.mark.parametrize("backend", ["wd_v3", "pixai_v0_9"])
def test_onnx_adapters_return_structured_result(backend, tmp_path):
    (tmp_path / "model.onnx").write_bytes(b"fake")
    (tmp_path / "selected_tags.csv").write_text('name,category,ips\n1girl,0,[]\nhero,4,"[""series""]"\n', encoding="utf-8")
    image = tmp_path / "image.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(image)
    runtime = FakeRuntime(["CPUExecutionProvider"], np.array([[.8, .9]], dtype=np.float32))
    if backend == "pixai_v0_9":
        (tmp_path / "selected_tags.csv").write_text('name,category,ips\n1girl,0,[]\n,0,[]\nhero,4,"[""series""]"\n', encoding="utf-8")
        class Session:
            def get_inputs(self): return [FakeNode("input", [1, 3, 448, 448])]
            def get_outputs(self): return [FakeNode("prediction", [1, 3]), FakeNode("embedding", [1, 1024])]
            def get_providers(self): return ["CPUExecutionProvider"]
            def run(self, outputs, feeds):
                assert outputs == ["prediction"]
                assert feeds["input"].shape == (1, 3, 448, 448)
                assert feeds["input"][0, 0, 0, 0] == 1
                assert feeds["input"][0, 2, 0, 0] == -1
                return [np.array([[.8, .999, .9]])]
        runtime.InferenceSession = lambda *a, **k: Session()
    engine = create_backend(backend, tmp_path, runtime=runtime, device=Device.CPU)
    result = engine.predict(image)
    assert set(result.grouped) >= {"general", "character", "rating", "copyright", "raw"}
    assert result.model_info.backend == backend
    assert len(result.grouped["character"]) == 1
    assert bool(result.grouped["copyright"]) == (backend == "pixai_v0_9")
    if backend == "pixai_v0_9":
        assert result.grouped["character"][0].tag.index == 2
        assert result.grouped["character"][0].confidence == pytest.approx(.9)
        assert all(p.tag.name for p in result.predictions)
    engine.unload()
    assert not engine.is_loaded


@pytest.mark.parametrize("mode", ["raw", "anime", "pony", "lora_caption", "cyberillustrious_semireal"])
@pytest.mark.parametrize("backend", BACKENDS)
def test_prompt_modes_and_bounded_output(mode, backend):
    from app.prompts.pipeline import tag_results_from_predictions
    tags = tag_results_from_predictions([prediction("1girl", .99)] + [prediction(f"tag_{i}", .8, index=i+1) for i in range(200)])
    settings = AppSettings.from_mapping({"backend": backend, "profile": mode, "top_k": 12})
    result = TaggingService().rebuild_prompts(tags, settings)
    assert result.positive_prompt
    assert len(result.filtered_tags) <= 12


def test_cli_old_and_new_aliases():
    args = build_parser().parse_args(["image.png", "--tagger-backend", "pixai_v0_9", "--threshold-general", ".4", "--threshold-character", ".8", "--threshold-rating", ".6", "--top-k", "16"])
    settings = _settings_from_args(AppSettings(), args)
    assert (settings.backend, settings.general_threshold, settings.character_threshold, settings.rating_threshold, settings.top_k) == ("pixai_v0_9", .4, .8, .6, 16)
    assert build_parser().parse_args(["image.png", "--general-threshold", ".7"]).general_threshold == .7


def test_gui_switch_and_missing_model(qtbot, tmp_path):
    from app.ui.settings_dialog import SettingsDialog
    service = TaggingService()
    dialog = SettingsDialog(AppSettings(model_dir=str(tmp_path)), service.validate_model_directory)
    qtbot.addWidget(dialog)
    dialog.backend_combo.setCurrentIndex(dialog.backend_combo.findData("pixai_v0_9"))
    dialog.model_dir_edit.setText(str(tmp_path / "missing"))
    result = dialog.validate_now()
    assert not result.valid
    assert "model.onnx" in dialog.validation_label.text()
    assert dialog.general_spin.value() == .3
    assert dialog.top_k_spin.value() == 128
    dialog.general_spin.setValue(.45)
    dialog.backend_combo.setCurrentIndex(dialog.backend_combo.findData("wd_v3"))
    dialog.backend_combo.setCurrentIndex(dialog.backend_combo.findData("pixai_v0_9"))
    assert dialog.general_spin.value() == .45


def test_canary_local_inference_contract(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    timm = pytest.importorskip("timm")
    from safetensors.torch import save_file
    (tmp_path / "selected_tags.csv").write_text("name,category\nsafe,9\n1girl,0\nhero,4\n")
    (tmp_path / "config.json").write_text(json.dumps({"architecture": "eva02_large_patch14_448", "num_classes": 3}))
    save_file({"dummy": torch.zeros(1)}, str(tmp_path / "model.safetensors"))
    class Model:
        def load_state_dict(self, state, strict): assert strict and "dummy" in state
        def eval(self): return self
        def to(self, device): assert device == "cpu"; return self
        def __call__(self, tensor):
            assert tuple(tensor.shape) == (1, 3, 448, 448)
            assert tensor[0, 0, 224, 224] == -1  # BGR, not RGB
            assert tensor[0, 2, 224, 224] == 1
            return torch.tensor([[0., 2., -2.]])
    def factory(name, **kwargs):
        assert name == "eva02_large_patch14_448"
        assert kwargs == {"pretrained": False, "num_classes": 3}
        return Model()
    monkeypatch.setattr(timm, "create_model", factory)
    image = tmp_path / "image.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(image)
    engine = create_backend(DEFAULT_BACKEND, tmp_path, device=Device.CPU)
    result = engine.predict(image)
    assert result.grouped["rating"][0].confidence == .5
    assert result.grouped["copyright"] == ()
    assert result.grouped["general"][0].confidence == pytest.approx(.880797, abs=1e-5)
    engine.unload()
    assert not engine.is_loaded


def test_cli_legacy_model_dir_preserves_threshold(tmp_path):
    (tmp_path / "model.onnx").write_bytes(b"fake")
    args = build_parser().parse_args(["image.png", "--model-dir", str(tmp_path)])
    settings = _settings_from_args(AppSettings(general_threshold=.6), args)
    assert settings.backend == "wd_v3"
    assert settings.general_threshold == .6


@pytest.mark.parametrize("args", [["--top-k", "0"], ["--threshold-general", "nan"], ["--tagger-backend", "bad"]])
def test_cli_illegal_options(args):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["image.png", *args])


def test_batch_cli_backend_options():
    from app.batch_cli import build_parser as parser, _settings_from_args as settings_from
    args = parser().parse_args(["images", "--tagger-backend", "pixai_v0_9", "--threshold-rating", ".7", "--top-k", "10"])
    settings = settings_from(AppSettings(), args)
    assert settings.backend == "pixai_v0_9"
    assert settings.general_threshold == .3
    assert settings.rating_threshold == .7
    assert settings.top_k == 10


@pytest.mark.parametrize("shape,outputs", [([1,448,448,3],[FakeNode("prediction",[1,2])]), ([1,3,448,448],[FakeNode("logits",[1,2])]), ([1,3,448,448],[FakeNode("prediction",[1,3])])])
def test_pixai_rejects_incompatible_graph(shape, outputs):
    session = SimpleNamespace(get_inputs=lambda:[FakeNode("input",shape)], get_outputs=lambda:outputs)
    with pytest.raises(ModelLoadError):
        PixAiTaggerBackend._inspect_session(session, [None,None])


def test_cross_backend_atomic_load_and_mismatch(tmp_path, monkeypatch):
    import app.services.tagging_service as module
    from tests.test_tagging_service import FakeEngine
    calls = []
    def factory(backend, path, device):
        engine = FakeEngine(path, device=device, fail=backend == "pixai_v0_9")
        calls.append((backend, engine))
        return engine
    monkeypatch.setattr(module, "create_backend", factory)
    service = TaggingService()
    service.load_model(tmp_path, Device.CPU, backend="wd_v3")
    assert service.loaded_backend == "wd_v3"
    with pytest.raises(RuntimeError, match="bad candidate"):
        service.load_model(tmp_path, Device.CPU, backend="pixai_v0_9")
    assert service.is_model_loaded
    assert service.loaded_backend == "wd_v3"
    assert not calls[0][1].released
    service.load_model(tmp_path, Device.CPU, backend=DEFAULT_BACKEND)
    assert service.loaded_backend == DEFAULT_BACKEND
    assert calls[0][1].released
    with pytest.raises(ModelLoadError, match="切换"):
        service.analyze_image(tmp_path / "image.png", AppSettings.from_mapping({"backend":"wd_v3"}))
    service.unload_model()
    assert service.loaded_backend is None


def test_default_file_backend_specific_defaults(tmp_path):
    default = tmp_path / "default.json"
    default.write_text('{"backend":"pixai_v0_9"}')
    settings = load_settings(default_path=default, user_path=tmp_path / "missing.json")
    assert settings.general_threshold == .3
    assert settings.top_k == 128


def test_copyright_uses_character_threshold():
    from app.prompts.pipeline import tag_results_from_predictions
    tags = tag_results_from_predictions([prediction("series", .6, TagCategory.COPYRIGHT)])
    service = TaggingService()
    settings = AppSettings.from_mapping({"backend":"pixai_v0_9"})
    assert not service.rebuild_prompts(tags, settings).filtered_tags
    assert service.rebuild_prompts(tags, replace(settings, character_threshold=.5)).filtered_tags


def test_configured_pixai_not_overridden_by_legacy_cli(tmp_path):
    (tmp_path / "model.onnx").write_bytes(b"fake")
    args = build_parser().parse_args(["image.png", "--model-dir", str(tmp_path)])
    settings = _settings_from_args(AppSettings.from_mapping({"backend":"pixai_v0_9"}), args)
    assert settings.backend == "pixai_v0_9"
    assert settings.model_dir == str(tmp_path)

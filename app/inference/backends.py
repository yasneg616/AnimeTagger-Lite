"""Local-only tagger adapters. No model or executable code is downloaded here."""
from __future__ import annotations

import csv
from dataclasses import dataclass, replace
import json
from pathlib import Path
import time
from typing import Protocol

import numpy as np
from PIL import Image

from app.errors import ConfigurationError, InferenceError, ModelLoadError
from app.image.image_loader import ImageLoadOptions, load_rgb_image
from app.inference.model_loader import ModelFiles, TagCategory, TagMetadata, load_selected_tags, resolve_model_files
from app.inference.providers import Device
from app.inference.wd14_engine import InferenceResult, ModelInfo, TagPrediction, WD14Engine

DEFAULT_BACKEND = "wd_2026_canary"


@dataclass(frozen=True)
class BackendSpec:
    label: str
    directory: str
    general_threshold: float = 0.35
    character_threshold: float = 0.75
    rating_threshold: float = 0.5
    top_k: int | None = None


BACKENDS = {
    "wd_v3": BackendSpec("WD EVA02 v3 / WD v3", "models/wd-vit-tagger-v3"),
    DEFAULT_BACKEND: BackendSpec("WD EVA02 2026 Canary", "models/wd-eva02-tagger-2026-canary"),
    "pixai_v0_9": BackendSpec("PixAI Tagger v0.9", "models/pixai-tagger-v0.9", 0.30, top_k=128),
}


def backend_spec(backend: str) -> BackendSpec:
    if not isinstance(backend, str) or backend not in BACKENDS:
        raise ConfigurationError(f"未知 tagger backend：{backend}；可选：{', '.join(BACKENDS)}")
    return BACKENDS[backend]


class TaggerBackend(Protocol):
    @property
    def is_loaded(self) -> bool: ...
    @property
    def model_info(self) -> ModelInfo | None: ...
    def load(self) -> ModelInfo: ...
    def unload(self) -> None: ...
    def release(self) -> None: ...
    def predict(self, image_path: Path, *, image_options: ImageLoadOptions | None = None) -> InferenceResult: ...
    def metadata(self) -> BackendSpec: ...
    def supported_groups(self) -> tuple[TagCategory, ...]: ...


def normalize_predictions(predictions) -> tuple[TagPrediction, ...]:
    """Preserve Danbooru punctuation, normalize whitespace, retain best duplicate."""
    unique = {}
    for prediction in predictions:
        name = "_".join(prediction.tag.name.strip().split())
        score = float(prediction.confidence)
        if not name or not np.isfinite(score) or not 0 <= score <= 1:
            raise InferenceError("标签名称为空或置信度不在 0 到 1 范围。")
        key = (prediction.tag.category, name.casefold())
        candidate = TagPrediction(replace(prediction.tag, name=name), score)
        if key not in unique or unique[key].confidence < score:
            unique[key] = candidate
    return tuple(sorted(unique.values(), key=lambda p: (-p.confidence, p.tag.index)))


def resolve_backend_files(directory: Path, backend: str) -> ModelFiles:
    backend_spec(backend)
    if backend != DEFAULT_BACKEND:
        return resolve_model_files(directory)
    directory = Path(directory)
    names = ("model.safetensors", "selected_tags.csv", "config.json")
    missing = [name for name in names if not (directory / name).is_file() or (directory / name).stat().st_size == 0]
    if missing:
        raise ModelLoadError(f"{backend} 模型目录缺少必要文件或文件为空：{', '.join(missing)}；目录：{directory}")
    return ModelFiles(directory, directory / names[0], directory / names[1])


def load_backend_tags(path: Path, backend: str):
    # PixAI export has an unnamed output at index 8968. Never remove the
    # CSV row before pairing with scores, because all following IDs would shift.
    return load_selected_tags(path, allow_empty_names=backend == "pixai_v0_9")


class WdEva02V3Backend(WD14Engine):
    backend_id = "wd_v3"

    def metadata(self):
        return backend_spec(self.backend_id)

    def supported_groups(self):
        return (TagCategory.RATING, TagCategory.GENERAL, TagCategory.CHARACTER)

    def unload(self):
        self.release()

    def predict(self, image_path, *, image_options=None):
        result = super().predict(image_path, image_options=image_options)
        return replace(result, model_info=replace(result.model_info, backend=self.backend_id),
                       predictions=normalize_predictions(result.predictions))


class PixAiTaggerBackend(WdEva02V3Backend):
    """deepghs v0.9 export: NCHW RGB [-1,1], prediction output already sigmoid."""
    backend_id = "pixai_v0_9"

    @staticmethod
    def _load_tags(path):
        return load_backend_tags(path, "pixai_v0_9")

    def supported_groups(self):
        return (TagCategory.GENERAL, TagCategory.CHARACTER, TagCategory.COPYRIGHT)

    @staticmethod
    def _inspect_session(session, tags):
        inputs = session.get_inputs()
        outputs = {node.name: node for node in session.get_outputs()}
        if len(inputs) != 1 or "prediction" not in outputs:
            raise ModelLoadError("PixAI 需要 deepghs ONNX 导出（单输入及 prediction 概率输出）。")
        node, output = inputs[0], outputs["prediction"]
        if tuple(node.shape[1:]) != (3, 448, 448) or len(node.shape) != 4:
            raise ModelLoadError("PixAI 输入应为 [N, 3, 448, 448]。")
        if len(output.shape) != 2 or output.shape[1] != len(tags):
            raise ModelLoadError("PixAI 标签数量与 prediction 输出不一致。")
        if node.type != "tensor(float)" or output.type != "tensor(float)":
            raise ModelLoadError("PixAI 输入和 prediction 必须是 float32。")
        return node.name, output.name, 448, len(tags)

    @staticmethod
    def _preprocess_image(image_path, target_size, *, options=None):
        image = load_rgb_image(image_path, options=options)
        image = image.resize((target_size, target_size), Image.Resampling.BILINEAR)
        array = (np.asarray(image, dtype=np.float32) / 255.0 - 0.5) / 0.5
        return np.ascontiguousarray(array.transpose(2, 0, 1)[None])

    def load(self):
        if self.is_loaded:
            return self._model_info
        info = super().load()
        try:
            with info.files.tags_path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self._ips = {}
            for row in rows:
                ips = json.loads(row.get("ips") or "[]")
                if not isinstance(ips, list) or any(not isinstance(ip, str) for ip in ips):
                    raise ValueError("ips 必须是字符串数组")
                if ips:
                    self._ips[row["name"]] = ips
        except (OSError, ValueError, KeyError) as exc:
            self.release()
            raise ModelLoadError(f"PixAI CSV 的 ips 映射无效：{exc}") from exc
        warning = info.provider_warning
        if not self._ips:
            warning = (warning + "；" if warning else "") + "PixAI 标签文件没有 ips 映射，copyright 分组为空。"
        self._model_info = replace(info, backend=self.backend_id, provider_warning=warning)
        return self._model_info

    def predict(self, image_path, *, image_options=None):
        result = WD14Engine.predict(self, image_path, image_options=image_options)
        named = tuple(p for p in result.predictions if p.tag.name.strip())
        predictions = list(named)
        for prediction in named:
            if prediction.tag.category is TagCategory.CHARACTER:
                for ip in self._ips.get(prediction.tag.name, []):
                    # Derived IP confidence is the supporting character score,
                    # never an independent classifier probability.
                    tag = TagMetadata(result.model_info.output_count + len(predictions), -1, ip, 3, TagCategory.COPYRIGHT)
                    predictions.append(TagPrediction(tag, prediction.confidence))
        return replace(result, predictions=normalize_predictions(predictions))


class WdEva02Canary2026Backend(WdEva02V3Backend):
    backend_id = DEFAULT_BACKEND

    def load(self):
        if self.is_loaded:
            return self._model_info
        files = resolve_backend_files(self._model_dir, self.backend_id)
        tags = load_selected_tags(files.tags_path)
        try:
            import torch
            import timm
            from safetensors.torch import load_file
        except (ImportError, OSError) as exc:
            raise ModelLoadError("Canary 需要可选 PyTorch/timm/safetensors 依赖；请安装 requirements-tagger-torch.txt，或选择 wd_v3 / pixai_v0_9 ONNX 后端。") from exc
        try:
            config = json.loads((files.directory / "config.json").read_text(encoding="utf-8"))
            if config["architecture"] != "eva02_large_patch14_448" or config["num_classes"] != len(tags):
                raise ValueError("Canary 架构或标签数量不匹配")
            model = timm.create_model("eva02_large_patch14_448", pretrained=False, num_classes=len(tags))
            model.load_state_dict(load_file(str(files.model_path)), strict=True)
            use_cuda = self._device is not Device.CPU and torch.cuda.is_available()
            self._torch_device = "cuda" if use_cuda else "cpu"
            model = model.eval().to(self._torch_device)
            warning = "CUDA 不可用，Canary 已回退到 PyTorch CPU。" if self._device is Device.CUDA and not use_cuda else None
            info = ModelInfo(files, "input", "probabilities", 448, len(tags),
                             f"PyTorch {self._torch_device.upper()}", warning, self.backend_id)
        except Exception as exc:
            raise ModelLoadError(f"Canary 本地模型加载失败：{exc}") from exc
        self._session, self._tags, self._model_info = model, tags, info
        return info

    def predict(self, image_path, *, image_options=None):
        info = self.load()
        import torch
        options = image_options or ImageLoadOptions()
        image = load_rgb_image(image_path, options=options)
        size = max(image.size)
        square = Image.new("RGB", (size, size), options.background)
        square.paste(image, ((size - image.width) // 2, (size - image.height) // 2))
        square = square.resize((448, 448), Image.Resampling.BICUBIC)
        array = (np.asarray(square, dtype=np.float32) / 255.0 - 0.5) / 0.5
        array = np.ascontiguousarray(array[:, :, ::-1].transpose(2, 0, 1)[None])
        start = time.perf_counter()
        try:
            with torch.inference_mode():
                scores = self._session(torch.from_numpy(array).to(self._torch_device)).sigmoid().cpu().numpy()
            if scores.shape != (1, len(self._tags)):
                raise ValueError("输出形状与标签不一致")
            predictions = normalize_predictions(TagPrediction(tag, score) for tag, score in zip(self._tags, scores[0]))
        except Exception as exc:
            raise InferenceError(f"Canary 推理失败：{exc}") from exc
        return InferenceResult(Path(image_path), info, predictions, time.perf_counter() - start)


def create_backend(backend: str, model_dir: Path, *, device=Device.AUTO, **kwargs) -> TaggerBackend:
    backend_spec(backend)
    cls = {"wd_v3": WdEva02V3Backend, DEFAULT_BACKEND: WdEva02Canary2026Backend,
           "pixai_v0_9": PixAiTaggerBackend}[backend]
    return cls(model_dir, device=device, **kwargs)

"""Offline, Qt-free tag illustrations. These descriptors never modify tags."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
import logging
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping

from app.prompts.normalizer import canonical_tag_key
from app.runtime_paths import RESOURCE_DIR

logger = logging.getLogger(__name__)
STATUSES = frozenset({"direct", "composed", "schematic", "category_only", "pending", "excluded_character"})
SEMANTIC_STATUSES = frozenset({"direct", "composed", "schematic"})
GROUP_LABELS = {
    "hair": "头发", "eyes": "眼睛", "face": "表情与面部", "body": "身体特征",
    "clothing": "服装与配饰", "pose": "姿势与动作", "interaction": "人物互动",
    "object": "主体与物品", "scene": "场景与天气", "composition": "构图与画面",
    "lighting": "光照", "style": "画风与特效", "symbol": "文字与标记",
    "rating": "内容评级", "copyright": "作品名称", "other": "其他",
}
_SAFE_SHAPE = re.compile(r"^[a-z0-9_-]+$")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True, slots=True)
class TagVisual:
    key: str
    category: str
    group: str = "other"
    label_zh: str = ""
    explanation_zh: str = ""
    status: str = "pending"
    recipe: Mapping[str, object] | None = None
    reason: str = "尚未核对该标签的含义与图示。"

    @property
    def has_icon(self) -> bool:
        return self.recipe is not None and self.status not in {"pending", "excluded_character"}

    @property
    def semantic(self) -> bool:
        return self.status in SEMANTIC_STATUSES and self.has_icon

    @property
    def search_text(self) -> str:
        return " ".join((self.key, self.label_zh, self.explanation_zh)).casefold()


def _category_key(category: object) -> str:
    value = getattr(category, "value", category)
    return {"0": "general", "4": "character", "9": "rating", "3": "copyright"}.get(str(value), str(value))


def _freeze_recipe(raw: object) -> Mapping[str, object] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or not _SAFE_SHAPE.fullmatch(str(raw.get("shape", ""))):
        raise ValueError("图示 recipe/shape 无效")
    result: dict[str, object] = {}
    for key, value in raw.items():
        if key in {"color", "accent"} and not _HEX_COLOR.fullmatch(str(value)):
            raise ValueError("图示颜色无效")
        if key == "features" and not isinstance(value, (list, tuple)):
            raise ValueError("图示 features 必须是列表")
        if isinstance(value, list):
            if not all(isinstance(v, str) for v in value):
                raise ValueError("图示 features 无效")
            value = tuple(value)
        elif not isinstance(value, (str, int, float, bool)):
            raise ValueError("图示参数无效")
        result[key] = value
    return MappingProxyType(result)


def _descriptor(key: str, category: str, raw: object) -> TagVisual:
    if not isinstance(raw, dict):
        raise ValueError("图示条目必须是对象")
    status = raw.get("status", "direct")
    group = raw.get("group", "other")
    if status not in STATUSES or group not in GROUP_LABELS:
        raise ValueError("图示状态或分组无效")
    for field in ("label_zh", "explanation_zh", "reason"):
        if field in raw and not isinstance(raw[field], str):
            raise ValueError("图示说明必须是文字")
    recipe = _freeze_recipe(raw.get("recipe"))
    if status in SEMANTIC_STATUSES | {"category_only"} and recipe is None:
        raise ValueError("已覆盖条目缺少 recipe")
    return TagVisual(key, category, group, raw.get("label_zh", ""), raw.get("explanation_zh", ""),
                     status, recipe, raw.get("reason", ""))


class TagVisualLibrary:
    """Read the shipped catalog; bounded composition also supports manual tags.

    Missing/bad resources are a display limitation, never an inference error.
    Catalog entries use category + canonical name, so character collisions do
    not hide general tags such as chocobo.
    """

    def __init__(self, resource_dir: Path | None = None, *, load_catalog: bool = True) -> None:
        self.directory = Path(resource_dir) if resource_dir is not None else RESOURCE_DIR / "tag_visuals"
        self.entries: dict[str, TagVisual] = {}
        self.terms: dict[str, TagVisual] = {}
        self.colors: dict[str, tuple[str, str]] = {}
        self.modifiers: dict[str, dict[str, str]] = {}
        self.available = False
        try:
            rules = json.loads((self.directory / "rules.json").read_text(encoding="utf-8"))
            if rules.get("schema_version") != 1:
                raise ValueError("不支持的图示规则版本")
            for key, raw in rules["terms"].items():
                self.terms[canonical_tag_key(key)] = _descriptor(canonical_tag_key(key), "general", raw)
            for key, value in rules["colors"].items():
                if not isinstance(value, list) or len(value) != 2 or not _HEX_COLOR.fullmatch(value[1]):
                    raise ValueError("颜色词典无效")
                self.colors[canonical_tag_key(key)] = (str(value[0]), value[1])
            for key, value in rules.get("modifiers", {}).items():
                if not isinstance(value, dict) or not isinstance(value.get("zh"), str) or not isinstance(value.get("feature"), str):
                    raise ValueError("修饰词典无效")
                if value.get("color") is not None and not _HEX_COLOR.fullmatch(str(value["color"])):
                    raise ValueError("修饰词颜色无效")
                self.modifiers[canonical_tag_key(key)] = value
            catalog_path = self.directory / "catalog.json"
            if load_catalog and catalog_path.is_file():
                catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
                if catalog.get("schema_version") != 1:
                    raise ValueError("不支持的图示目录版本")
                for identity, raw in catalog["entries"].items():
                    category, key = identity.split(":", 1)
                    self.entries[identity] = _descriptor(key, category, raw)
            # Assets are required even if the lookup only needs Chinese text.
            assets = json.loads((self.directory / "primitives.json").read_text(encoding="utf-8"))
            if assets.get("schema_version") != 1 or not isinstance(assets.get("shapes"), dict):
                raise ValueError("图示素材无效")
            self._term_order = tuple(sorted(self.terms, key=len, reverse=True))
            self.available = True
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError) as exc:
            self.entries.clear()
            self.terms.clear()
            self._term_order = ()
            logger.warning("标签图示资源不可用，继续显示原英文标签：%s", exc)

    @lru_cache(maxsize=8192)
    def lookup(self, name: str, category: object = "general") -> TagVisual:
        key = canonical_tag_key(name)
        category_key = _category_key(category)
        if category_key == "character":
            return TagVisual(key, category_key, status="excluded_character", reason="角色名称保留文字，不制作头像或身份图示。")
        if not self.available:
            return TagVisual(key, category_key, reason="图示资源不可用，当前保留原英文文字。")
        exact = self.entries.get(f"{category_key}:{key}")
        if exact is not None:
            return exact
        if category_key == "rating" and key not in {"general", "sensitive", "questionable", "explicit"}:
            return TagVisual(key, category_key, "rating", reason="该评级名称尚未建立释义，不采用一般标签的图示。")
        if category_key == "copyright":
            return TagVisual(key, category_key, "copyright", "作品名称", "作品或系列的专有名称；图标仅表示作品类别。",
                             "category_only", _freeze_recipe({"shape": "book", "family": "object"}), "专有名称需要单独的作品资料，不能由字面推断形象。")
        if category_key in {"general", "other", "rating"}:
            return self.compose(key, category_key)
        return TagVisual(key, category_key)

    def compose(self, name: str, category: str = "general") -> TagVisual:
        key = canonical_tag_key(name)
        if key in self.terms:
            return self._exact_term(key, category)
        # Relationships consume whole, verified terms. Unknown object names
        # cannot acquire a misleading icon just by containing "hair"/"eye".
        for prefix, feature, zh, groups in (
            ("holding ", "held", "手持", {"object", "clothing"}),
            ("mouth hold ", "mouth-held", "用嘴衔住", {"object", "clothing"}),
            ("no ", "excluded", "没有", {"object", "clothing", "hair", "body"}),
            ("unworn ", "unworn", "未穿戴的", {"clothing"}),
            ("missing ", "excluded", "缺少", {"clothing", "body"}),
        ):
            if key.startswith(prefix):
                rest_key = key[len(prefix):]
                base = self.compose(rest_key, category) if rest_key.startswith(('unworn ', 'no ')) else self._compose_simple(rest_key, category)
                if base.semantic and base.group in groups:
                    recipe = dict(base.recipe or {})
                    recipe["features"] = list(recipe.get("features", ())) + [feature]
                    label = zh + base.label_zh
                    return TagVisual(key, category, "pose" if feature in {"held", "mouth-held"} else base.group,
                                     label, label + "；以物品轮廓与动作标记组合说明。", "composed", _freeze_recipe(recipe), "")
        for suffix, feature, zh in ((" focus", "focus", "画面突出"), (" lift", "lifted", "向上提起"),
                                    (" pull", "pulled", "拉动"), (" aside", "aside", "移到一侧的"),
                                    (" hold", "held", "手扶")):
            if key.endswith(suffix):
                base = self._compose_simple(key[:-len(suffix)], category)
                allowed = {"body", "object", "clothing", "face", "eyes"} if feature == "focus" else {"clothing"}
                if base.semantic and base.group in allowed:
                    recipe = dict(base.recipe or {})
                    recipe["features"] = list(recipe.get("features", ())) + [feature]
                    label = zh + base.label_zh
                    return TagVisual(key, category, "composition" if feature == "focus" else "pose", label,
                                     label + "；圆框／箭头表示重点或移动方向。", "composed", _freeze_recipe(recipe), "")
        for suffix, part, zh in ((" on head","head","戴在头上的"), (" on shoulders","shoulder","搭在肩上的"),
                                 (" around neck","neck","围在颈部的"), (" on back","back","放在背部的")):
            if key.endswith(suffix):
                base = self._compose_simple(key[:-len(suffix)], category)
                if base.semantic and base.group in {"clothing", "object"}:
                    recipe = dict(base.recipe or {})
                    recipe.update(features=list(recipe.get("features", ()))+["on-body"], part=part)
                    label = zh+base.label_zh
                    return TagVisual(key, category, "clothing", label, label+"；人物轮廓标明所处位置。", "composed", _freeze_recipe(recipe), "")
        if key.endswith(" print"):
            base = self._compose_simple(key[:-6], category)
            if base.semantic and base.group == "object":
                recipe = {"shape":"frame", "family":"object", "pattern_shape":base.recipe["shape"], "features":["object-pattern"]}
                label = base.label_zh+"图案"
                return TagVisual(key, category, "clothing", label, label+"；表示织物或物品上的图案。", "composed", _freeze_recipe(recipe), "")
        body_parts = {"head":"头部", "face":"脸部", "cheek":"脸颊", "chin":"下巴", "hair":"头发", "mouth":"嘴部", "ear":"耳朵",
                      "neck":"颈部", "shoulder":"肩膀", "arm":"手臂", "hand":"手部", "chest":"胸前", "stomach":"腹部",
                      "back":"背部", "hip":"髋部", "waist":"腰部", "thigh":"大腿", "knee":"膝部", "leg":"腿部", "foot":"足部"}
        for prefix, zh in (("scar on ","疤痕在"), ("tattoo on ","纹身在"), ("mole on ","痣在"),
                           ("bandaid on ","创可贴在"), ("bandaged ","绷带包扎")):
            if key.startswith(prefix) and key[len(prefix):] in body_parts:
                part = key[len(prefix):]
                label = zh + body_parts[part]
                recipe = {"shape":"body", "family":"body", "variant":key.replace(" ","_"), "features":[]}
                return TagVisual(key, category, "body", label, label+"；圆点标记对应部位。", "composed", _freeze_recipe(recipe), "")
        for prefix, zh in (("hand on own ","一只手放在自己的"), ("hands on own ","双手放在自己的"),
                           ("hand in own ","一只手放进自己的"), ("hand on another's ","手放在他人的")):
            if key.startswith(prefix) and key[len(prefix):] in body_parts:
                part = key[len(prefix):]
                label = zh + body_parts[part]
                other = "another's" in prefix
                recipe = {"shape":"people" if other else "pose", "family":"object" if other else "pose",
                          "variant":key.replace(" ","_"), "features":["touch-other"] if other else [], "part":part}
                return TagVisual(key, category, "interaction" if other else "pose", label,
                                 label+"；箭头指出接触位置。", "composed", _freeze_recipe(recipe), "")
        for prefix, pose, zh in (("sitting on ","sitting","坐在"), ("on ","sitting","在")):
            if key.startswith(prefix):
                base = self._compose_simple(key[len(prefix):], category)
                if base.semantic and base.recipe and base.recipe["shape"] in {"chair", "bed", "floor", "couch", "table", "rock"}:
                    label = zh + base.label_zh + "上"
                    recipe = {"shape":"pose", "family":"pose", "variant":pose, "support_shape":base.recipe["shape"], "features":[]}
                    return TagVisual(key, category, "pose", label, label+"；人物与支撑物组合示意。",
                                     "composed", _freeze_recipe(recipe), "")
        return self._compose_simple(key, category)

    def _compose_simple(self, key: str, category: str) -> TagVisual:
        if key in self.terms:
            return self._exact_term(key, category)
        # Only complete, known modifiers followed by a known visual term are
        # accepted. "hair ribbon" must never become a hair style by substring.
        for term_key in self._term_order:
            base = self.terms[term_key]
            if not base.semantic or not key.endswith(" " + term_key):
                continue
            prefix = key[:-(len(term_key) + 1)]
            pieces: list[str] = []
            features = list(base.recipe.get("features", ())) if base.recipe else []
            recipe = dict(base.recipe or {})
            rest = prefix
            parts = 0
            while rest and parts < 4:
                matched = False
                for color in sorted(self.colors, key=len, reverse=True):
                    if base.group not in {"hair", "eyes", "clothing", "body", "object", "scene"} and base.key not in {"border", "outline"}:
                        continue
                    if rest == color or rest.startswith(color + " "):
                        zh, hex_color = self.colors[color]
                        if "color" in recipe:
                            recipe["accent"] = hex_color
                            features.append("two-tone")
                        else:
                            recipe["color"] = hex_color
                        pieces.append(zh)
                        if color == "multicolored":
                            features.append("multicolored")
                        rest = rest[len(color):].strip()
                        matched = True
                        break
                if not matched:
                    for modifier in sorted(self.modifiers, key=len, reverse=True):
                        value = self.modifiers[modifier]
                        allowed = value.get("groups", "").split(",")
                        if base.group not in allowed:
                            continue
                        if rest == modifier or rest.startswith(modifier + " "):
                            features.append(value["feature"])
                            if value.get("color"):
                                recipe["accent"] = value["color"]
                            pieces.append(value["zh"])
                            rest = rest[len(modifier):].strip()
                            matched = True
                            break
                if not matched:
                    break
                parts += 1
            if not rest and pieces:
                recipe["features"] = features
                label = "".join(pieces) + base.label_zh
                return TagVisual(key, category, base.group, label, f"{label}。",
                                 "composed", _freeze_recipe(recipe), "")
        base = next((self.terms[t] for t in self._term_order if key.endswith(" "+t)), None)
        if base is not None:
            return TagVisual(key, category, base.group, reason=f"已识别中心词“{base.label_zh}”，但完整修饰含义或对应细节尚未核对。")
        return TagVisual(key, category, self._pending_group(key), reason="含义或专用造型尚未核对；保留英文，等待补充释义与素材。")

    def _exact_term(self, key: str, category: str) -> TagVisual:
        term = self.terms[key]
        if term.group == "rating" and category != "rating":
            return TagVisual(key, category, reason="同名词仅在 Rating 类别中有已核对的评级含义；一般标签保留文字。")
        return replace(term, key=key, category=category)

    @staticmethod
    def _pending_group(key: str) -> str:
        if any(word in key for word in ("(cosplay)", "official alternate", "(style)", " borrowed")):
            return "symbol"
        families = {
            "hair": {"hair", "bangs", "braid", "ponytail", "twintails", "sidelocks", "bun"},
            "eyes": {"eyes", "eye", "pupils", "pupil", "sclera", "eyelashes"},
            "clothing": {"uniform", "clothes", "outfit", "costume", "dress", "skirt", "shirt", "jacket", "pants", "hat", "cap", "headwear", "legwear", "sleeves", "eyewear", "gloves", "panties", "bikini", "swimsuit", "earrings", "ornament", "belt", "bra", "collar", "trim", "cutout"},
            "body": {"skin", "tail", "ears", "horns", "wings", "breasts", "penis", "pussy", "navel", "tattoo", "scar", "piercing"},
            "pose": {"holding", "sitting", "standing", "kneeling", "reaching", "waving", "grab", "pull", "lift"},
            "composition": {"focus", "frame", "angle", "perspective", "background", "koma"},
            "face": {"mouth", "smile", "eyebrows", "blush", "tongue", "teeth"},
            "symbol": {"text", "logo", "watermark", "symbol", "signature", "print"},
            "lighting": {"light", "lighting", "rays", "shadow", "glow"},
        }
        words = set(key.split())
        if words & {"cum", "sex", "masturbation", "fellatio", "penetration", "fingering"}:
            return "interaction"
        if words & {"ornament", "uniform", "hairband"}:
            return "clothing"
        return next((group for group, tokens in families.items() if words & tokens), "other")


@lru_cache(maxsize=1)
def default_library() -> TagVisualLibrary:
    return TagVisualLibrary()


def lookup(name: str, category: object = "general") -> TagVisual:
    return default_library().lookup(name, category)

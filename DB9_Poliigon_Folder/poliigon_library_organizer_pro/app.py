import ctypes
import datetime
import io
import json
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.parse
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

try:
    from PIL import Image, ImageOps, ImageTk

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# ---------------- Optional dependencies ---------------- #
try:
    import requests  # type: ignore
    REQUESTS_AVAILABLE = True
except Exception:
    REQUESTS_AVAILABLE = False

try:
    from bs4 import BeautifulSoup  # type: ignore
    BS4_AVAILABLE = True
except Exception:
    BS4_AVAILABLE = False

try:
    from OpenGL import GL  # type: ignore
    PYOPENGL_AVAILABLE = True
except Exception:
    PYOPENGL_AVAILABLE = False


# ---------------- Windows DPI awareness ---------------- #
def enable_dpi_awareness():
    """Enable per-monitor DPI awareness on Windows to keep UI crisp on high-DPI screens."""
    if not sys.platform.startswith("win"):
        return
    try:
        # Per-monitor v2 (Windows 10 1703+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


enable_dpi_awareness()

APP_TITLE = "DB9_TextureModelCollectionTool"
WINDOWS_APP_ID = "DB9.Visual.TextureOrganizer"
RES_LABELS = ["2k", "4k", "8k", "16k", "24k", "32k"]
DEFAULT_PRESETS = [
    "Asphalt",
    "Brick",
    "Concrete",
    "Wood",
    "Stone",
    "Rock",
    "Ground",
    "Sand",
    "Gravel",
    "Mud",
    "Snow",
    "Metal",
    "Roof",
    "Wall",
    "Floor",
    "Unsorted",
]
SORT_OPTIONS = [
    "Name A-Z",
    "Name Z-A",
    "Preset A-Z",
    "Newest",
    "Oldest",
    "Most Tags",
    "Resolution High-Low",
]
THUMB_SIZE = (184, 184)
TILE_WIDTH = 248
PREVIEW_THUMB_MAX_DIM = 1024
CANVAS_BG = "#12090B"
SIDEBAR_BG = "#150709"
SIDEBAR_FG = "#F7E9E2"
CONTENT_BG = "#211012"
PRIMARY = "#B4232C"
PRIMARY_HOVER = "#D73741"
SUCCESS = "#D96C2F"
ACCENT = "#7A1C22"
CARD_BG = "#F8F1ED"
CARD_BORDER = "#D6B2A7"
BADGE_BG = "#5F4243"
BADGE_ACTIVE_BG = "#B4232C"
MUTED = "#8E6F6C"
SIDEBAR_CARD = "#261113"
SIDEBAR_BORDER = "#552126"
CONTENT_PANEL = "#2B1518"
CONTENT_TEXT = "#F8EAE4"
TAG_KEYWORDS = [
    "wet",
    "dirty",
    "damaged",
    "clean",
    "rough",
    "smooth",
    "stone",
    "rock",
    "wood",
    "asphalt",
    "brick",
    "concrete",
    "ground",
    "road",
    "gravel",
    "mud",
    "sand",
    "snow",
    "forest",
    "wall",
    "floor",
    "metal",
]
PRESET_TAG_MAP = {
    "Asphalt": ["asphalt", "road"],
    "Brick": ["brick", "wall"],
    "Concrete": ["concrete", "stone"],
    "Wood": ["wood"],
    "Stone": ["stone"],
    "Rock": ["rock", "cliff"],
    "Ground": ["ground", "soil", "dirt"],
    "Sand": ["sand", "desert"],
    "Gravel": ["gravel", "pebble"],
    "Mud": ["mud", "soil"],
    "Snow": ["snow", "ice"],
    "Metal": ["metal", "rust"],
    "Roof": ["roof", "tile"],
    "Wall": ["wall", "plaster"],
    "Floor": ["floor", "tile"],
}
PRESET_ALIASES = {
    "asphalt textures": "Asphalt",
    "brick textures": "Brick",
    "concrete textures": "Concrete",
    "wood textures": "Wood",
    "stone textures": "Stone",
    "rock textures": "Rock",
    "ground textures": "Ground",
    "sand textures": "Sand",
    "gravel textures": "Gravel",
    "mud textures": "Mud",
    "snow textures": "Snow",
    "metal textures": "Metal",
    "roof textures": "Roof",
    "wall textures": "Wall",
    "floor textures": "Floor",
    "unsorted": "Unsorted",
    "asphalt": "Asphalt",
    "brick": "Brick",
    "concrete": "Concrete",
    "wood": "Wood",
    "stone": "Stone",
    "rock": "Rock",
    "ground": "Ground",
    "sand": "Sand",
    "gravel": "Gravel",
    "mud": "Mud",
    "snow": "Snow",
    "metal": "Metal",
    "roof": "Roof",
    "wall": "Wall",
    "floor": "Floor",
}
PRESET_KEYWORDS = [
    ("Asphalt", ["asphalt", "road", "street", "lane", "tarmac", "pavement"]),
    ("Brick", ["brick", "masonry"]),
    ("Concrete", ["concrete", "cement"]),
    ("Wood", ["wood", "timber", "plank", "oak", "walnut"]),
    ("Stone", ["stone", "slate", "marble", "granite", "limestone", "travertine"]),
    ("Rock", ["rock", "cliff", "boulder", "canyon"]),
    ("Ground", ["ground", "soil", "dirt", "earth", "forest", "meadow"]),
    ("Sand", ["sand", "desert", "dune", "beach"]),
    ("Gravel", ["gravel", "pebble", "aggregate"]),
    ("Mud", ["mud", "bog", "swamp"]),
    ("Snow", ["snow", "ice", "frost"]),
    ("Metal", ["metal", "steel", "iron", "rust", "aluminum"]),
    ("Roof", ["roof", "shingle", "tile roof"]),
    ("Wall", ["wall", "plaster", "stucco"]),
    ("Floor", ["floor", "tile", "terrazzo", "parquet"]),
]


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(app_dir(), "poliigon_library_config.json")
LEARNING_FILE = os.path.join(app_dir(), "poliigon_learning_rules.json")
TAGS_FILE = os.path.join(app_dir(), "poliigon_asset_tags.json")
PORTABLE_STATE_DIR = ".poliigon_library_state"
PORTABLE_CONFIG_FILE = "library_config.json"
PORTABLE_RULES_FILE = "learning_rules.json"
PORTABLE_TAGS_FILE = "asset_tags.json"
PORTABLE_ASSET_META_FILE = "asset_meta.json"
PORTABLE_VARIANT_WARNINGS_FILE = "missing_variant_report.json"
PORTABLE_VARIANT_WARNINGS_TXT = "missing_variant_report.txt"

# v2 additions
SEEN_ASSETS_FILE = os.path.join(app_dir(), "poliigon_seen_assets.json")
POLIIGON_CHECK_STATE_FILE = os.path.join(app_dir(), "poliigon_check_state.json")
LOGO_ICO_PATH = os.path.join(app_dir(), "logo.ico")
LOGO_PNG_PATH = os.path.join(app_dir(), "logo.png")


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as file_obj:
                return json.load(file_obj)
        except Exception:
            pass
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as file_obj:
        json.dump(data, file_obj, indent=2, ensure_ascii=False)


def library_state_dir(library_root):
    return os.path.join(library_root, PORTABLE_STATE_DIR)


def library_state_paths(library_root):
    state_root = library_state_dir(library_root)
    return {
        "dir": state_root,
        "config": os.path.join(state_root, PORTABLE_CONFIG_FILE),
        "rules": os.path.join(state_root, PORTABLE_RULES_FILE),
        "tags": os.path.join(state_root, PORTABLE_TAGS_FILE),
        "asset_meta": os.path.join(state_root, PORTABLE_ASSET_META_FILE),
        "variant_warnings": os.path.join(state_root, PORTABLE_VARIANT_WARNINGS_FILE),
        "variant_warnings_txt": os.path.join(state_root, PORTABLE_VARIANT_WARNINGS_TXT),
    }


def infer_custom_presets_from_library(library_root):
    presets = []
    if not library_root or not os.path.isdir(library_root):
        return presets
    for entry in sorted(os.listdir(library_root), key=str.lower):
        if entry == PORTABLE_STATE_DIR:
            continue
        full_path = os.path.join(library_root, entry)
        if not os.path.isdir(full_path):
            continue
        preset = canonical_preset_name(entry)
        if preset and preset not in DEFAULT_PRESETS and preset not in presets:
            presets.append(preset)
    return presets


def normalize(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def clean_base(name):
    base = os.path.splitext(re.sub(r"\(\d+\)", "", name))[0]
    base = re.sub(r"([ _-]?)(2k|4k|8k|16k|24k|32k)$", "", base, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", base).strip(" _-")


def canonical_preset_name(name):
    raw = str(name or "").strip()
    if not raw:
        return ""
    alias = PRESET_ALIASES.get(raw.lower())
    if alias:
        return alias
    return raw


def get_presets_from_config(custom_presets=None):
    presets = []
    for preset in DEFAULT_PRESETS + list(custom_presets or []):
        normalized = canonical_preset_name(preset)
        if normalized and normalized not in presets:
            presets.append(normalized)
    if "Unsorted" not in presets:
        presets.append("Unsorted")
    return presets


def auto_pick(base, presets, rules):
    text = normalize(base)
    for rule in sorted(rules, key=lambda item: -item.get("w", 1)):
        target = canonical_preset_name(rule["t"])
        if rule["p"] in text and target in presets:
            rule["w"] += 1
            rule["t"] = target
            return target
    for preset_name, keywords in PRESET_KEYWORDS:
        if preset_name not in presets:
            continue
        if any(keyword in text for keyword in keywords):
            return preset_name
    return "Unsorted"


def zip_score(path):
    try:
        with zipfile.ZipFile(path) as zip_obj:
            return len(zip_obj.infolist())
    except Exception:
        return 0


def detect_resolution_from_name(name):
    low = str(name).lower()
    for res in RES_LABELS:
        if res in low:
            return res
    return None


def detect_resolutions_from_names(names):
    found = set()
    for name in names:
        res = detect_resolution_from_name(name)
        if res:
            found.add(res)
    return found


def detect_resolutions_in_folder(asset_folder):
    if not os.path.isdir(asset_folder):
        return set()
    return detect_resolutions_from_names(os.listdir(asset_folder))


def resolution_score(resolutions):
    if not resolutions:
        return -1
    indices = [RES_LABELS.index(item) for item in resolutions if item in RES_LABELS]
    return max(indices) if indices else -1


def auto_tags_for_asset(base, preset="", extra_texts=None):
    bag = [normalize(base), normalize(preset)]
    for value in extra_texts or []:
        bag.append(normalize(value))
    text = " ".join(item for item in bag if item)

    tags = set()
    for tag in TAG_KEYWORDS:
        if tag in text:
            tags.add(tag)
    for preset_name, preset_tags in PRESET_TAG_MAP.items():
        if normalize(preset_name) in text or preset == preset_name:
            tags.update(preset_tags)
    for res in RES_LABELS:
        if res in text:
            tags.add(res)
    return sorted(tags)


def merge_tags(existing, detected):
    return sorted(set(existing or []).union(detected or []))


class TaskCancelled(Exception):
    pass


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event):
        if self.tip or not self.text:
            return
        x_pos, y_pos = event.x_root + 10, event.y_root + 10
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.geometry(f"+{x_pos}+{y_pos}")
        tk.Label(
            self.tip,
            text=self.text,
            bg="#1E293B",
            fg="white",
            font=("Segoe UI", 9),
            padx=8,
            pady=4,
        ).pack()

    def hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def label_zip_variants(files):
    named = []
    unnamed = []

    for path in files:
        res = detect_resolution_from_name(os.path.basename(path))
        item = {"path": path, "res": res, "size": os.path.getsize(path)}
        if res:
            named.append(item)
        else:
            unnamed.append(item)

    used = {item["res"] for item in named if item["res"]}
    remaining_labels = [label for label in RES_LABELS if label not in used]
    unnamed.sort(key=lambda item: item["size"])

    for index, item in enumerate(unnamed):
        item["res"] = remaining_labels[index] if index < len(remaining_labels) else f"extra{index + 1}"

    combined = named + unnamed
    combined.sort(
        key=lambda item: RES_LABELS.index(item["res"]) if item["res"] in RES_LABELS else len(RES_LABELS) + 1
    )
    return combined


def find_preview_in_zip(zip_path):
    preview_candidates = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_obj:
            for info in zip_obj.infolist():
                if info.is_dir():
                    continue
                low = info.filename.lower()
                ext = os.path.splitext(low)[1]
                if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
                    continue
                score = 10 if "preview" in low else 0
                score += 4 if "_sphere" in low or "sphere" in low else 0
                score += 2 if "color" in low or "diff" in low or "albedo" in low else 0
                preview_candidates.append((score, len(info.filename), info.filename))
    except Exception:
        return None

    if not preview_candidates:
        return None

    preview_candidates.sort(key=lambda item: (-item[0], item[1], item[2].lower()))
    return preview_candidates[0][2]


def extract_preview_from_zip(zip_path, output_folder, base_name):
    preview_file = find_preview_in_zip(zip_path)
    if not preview_file:
        return None

    ext = os.path.splitext(preview_file)[1].lower() or ".png"
    output_path = os.path.join(output_folder, f"{base_name}_preview{ext}")

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_obj:
            with zip_obj.open(preview_file) as src, open(output_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
        ensure_preview_thumb(output_path, output_folder, base_name)
        return output_path
    except Exception:
        return None


def thumb_output_path(output_folder, base_name):
    return os.path.join(output_folder, f"{base_name}_thumb.jpg")


def ensure_preview_thumb(preview_path, output_folder, base_name, max_dim=PREVIEW_THUMB_MAX_DIM):
    if not (PIL_AVAILABLE and preview_path and os.path.exists(preview_path)):
        return None
    output_path = thumb_output_path(output_folder, base_name)
    try:
        src_mtime = os.path.getmtime(preview_path)
        if os.path.exists(output_path) and os.path.getmtime(output_path) >= src_mtime:
            return output_path
        with Image.open(preview_path) as image:
            image = image.convert("RGB")
            width, height = image.size
            if width <= 0 or height <= 0:
                return None
            scale = min(max_dim / width, max_dim / height, 1.0)
            resized = image.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.Resampling.LANCZOS,
            )
            resized.save(output_path, format="JPEG", quality=88, optimize=True)
        return output_path
    except Exception:
        return None


def top_level_source_group(source_root, file_path):
    if not source_root:
        return "All folders"
    try:
        rel = os.path.relpath(file_path, source_root)
    except ValueError:
        return "Unknown"
    if rel.startswith(".."):
        return "Unknown"
    parts = rel.split(os.sep)
    if len(parts) <= 1:
        return "[Root]"
    return parts[0] or "[Root]"


def collect_zip_groups(folder):
    seen = {}
    if not os.path.isdir(folder):
        return {}

    for root_dir, _dirs, files in os.walk(folder):
        for name in files:
            if not name.lower().endswith(".zip"):
                continue
            full_path = os.path.join(root_dir, name)
            size = os.path.getsize(full_path)
            key = (os.path.basename(name).lower(), size)
            if key in seen:
                best = max([seen[key], full_path], key=zip_score)
                worst = seen[key] if best != seen[key] else full_path
                if os.path.exists(worst):
                    os.remove(worst)
                seen[key] = best
            else:
                seen[key] = full_path

    groups = {}
    for full_path in seen.values():
        base = clean_base(os.path.basename(full_path))
        group = groups.setdefault(base, {"files": [], "source_groups": set()})
        group["files"].append(full_path)
        group["source_groups"].add(top_level_source_group(folder, full_path))
    return groups


def count_group_steps(groups):
    total = 0
    for item in groups.values():
        total += len(item["files"]) + 1
    return total


def infer_asset_meta_from_source(source_root):
    mapping = {}
    groups = collect_zip_groups(source_root)
    for base, group_data in groups.items():
        source_groups = sorted(group_data.get("source_groups", set()), key=str.lower)
        mapping[base] = {
            "source_group": source_groups[0] if source_groups else "[Root]",
            "source_groups": source_groups,
        }
    return mapping


def list_top_level_source_groups(source_root):
    if not source_root or not os.path.isdir(source_root):
        return []
    groups = []
    for name in sorted(os.listdir(source_root), key=str.lower):
        full_path = os.path.join(source_root, name)
        if os.path.isdir(full_path):
            groups.append(name)
    return groups


def list_top_level_library_groups(library_root, show_state=False):
    if not library_root or not os.path.isdir(library_root):
        return []
    groups = []
    for name in sorted(os.listdir(library_root), key=str.lower):
        full_path = os.path.join(library_root, name)
        if not os.path.isdir(full_path):
            continue
        if not show_state and name == PORTABLE_STATE_DIR:
            continue
        groups.append(name)
    return groups


def process_download_folder(folder, library_root, presets, rules, tags_db, asset_meta, log, progress, should_cancel=None):
    should_cancel = should_cancel or (lambda: False)
    groups = collect_zip_groups(folder)
    if not groups:
        raise RuntimeError("No ZIP files were found in the selected source folder.")

    total_steps = max(count_group_steps(groups), 1)
    current_step = 0
    moved = 0
    texture_folders = 0

    for base, group_data in sorted(groups.items()):
        if should_cancel():
            raise TaskCancelled()
        files = group_data["files"]
        preset = auto_pick(base, presets, rules)
        target = os.path.join(library_root, preset, base)
        os.makedirs(target, exist_ok=True)
        texture_folders += 1
        source_groups = sorted(group_data.get("source_groups", set()), key=str.lower)
        primary_group = source_groups[0] if source_groups else "[Root]"

        labeled_files = label_zip_variants(files)
        extra_texts = [os.path.basename(item["path"]) for item in labeled_files] + [item["res"] for item in labeled_files]
        tags_db[base] = merge_tags(tags_db.get(base, []), auto_tags_for_asset(base, preset, extra_texts))
        asset_meta[base] = {
            "source_group": primary_group,
            "source_groups": source_groups,
        }

        preview_source = None

        for item in labeled_files:
            if should_cancel():
                raise TaskCancelled()
            file_path = item["path"]
            res = item["res"]
            ext = os.path.splitext(file_path)[1].lower() or ".zip"
            new_name = f"{base}_{res}{ext}" if res else os.path.basename(file_path)
            destination = os.path.join(target, new_name)
            if os.path.abspath(file_path) == os.path.abspath(destination):
                if res in RES_LABELS and preview_source is None:
                    preview_source = destination
                continue
            if os.path.exists(destination):
                os.remove(destination)
            shutil.move(file_path, destination)
            moved += 1
            current_step += 1
            progress(current_step, total_steps, f"Moving {new_name}")
            log(f"[MOVE] {os.path.basename(file_path)} -> {preset}/{base}/{new_name}")
            if res in RES_LABELS and preview_source is None:
                preview_source = destination

        if preview_source is None and labeled_files:
            preview_source = os.path.join(
                target,
                f"{base}_{labeled_files[0]['res']}{os.path.splitext(labeled_files[0]['path'])[1].lower() or '.zip'}",
            )

        preview_path = extract_preview_from_zip(preview_source, target, base) if preview_source else None
        if preview_path:
            log(f"[PREVIEW] {os.path.basename(preview_path)} extracted from {os.path.basename(preview_source)}")
        else:
            log(f"[WARN] No preview extracted for {base}")

        current_step += 1
        progress(current_step, total_steps, f"Completed {base}")
        tag_text = ", ".join(tags_db[base]) if tags_db[base] else "-"
        log(f"[TEXTURE] {base} | preset={preset} | source={primary_group} | tags={tag_text}")

    return {"moved": moved, "texture_folders": texture_folders}


def collect_existing_assets(library_root):
    assets = []
    if not library_root or not os.path.isdir(library_root):
        return assets
    for preset in sorted(os.listdir(library_root)):
        if preset == PORTABLE_STATE_DIR:
            continue
        preset_path = os.path.join(library_root, preset)
        if not os.path.isdir(preset_path):
            continue
        for name in os.listdir(preset_path):
            asset_path = os.path.join(preset_path, name)
            if os.path.isdir(asset_path):
                assets.append(
                    {
                        "name": clean_base(name),
                        "folder_name": name,
                        "path": asset_path,
                        "preset": preset,
                    }
                )
    return assets


def merge_folder_contents(source_path, target_path, log):
    os.makedirs(target_path, exist_ok=True)
    for item_name in os.listdir(source_path):
        source_item = os.path.join(source_path, item_name)
        target_item = os.path.join(target_path, item_name)
        if os.path.isdir(source_item):
            merge_folder_contents(source_item, target_item, log)
            if os.path.isdir(source_item) and not os.listdir(source_item):
                os.rmdir(source_item)
            continue
        if os.path.exists(target_item):
            os.remove(target_item)
        shutil.move(source_item, target_item)
        log(f"[MERGE] {os.path.basename(source_path)} -> {os.path.basename(target_path)} | {item_name}")


def expected_lower_resolutions(found):
    present = [res for res in RES_LABELS if res in found]
    if not present:
        return []
    highest_index = max(RES_LABELS.index(res) for res in present)
    return [res for res in RES_LABELS[: highest_index + 1] if res not in found]


def missing_variant_chain(found):
    found_set = {res for res in found if res in RES_LABELS}
    missing_lower = expected_lower_resolutions(found_set)
    if not missing_lower:
        return []
    if not any(res in found_set for res in ["4k", "8k", "16k", "24k", "32k"]):
        return []
    return missing_lower


def format_variant_warning(missing_lower):
    if not missing_lower:
        return ""
    return f"Missing lower sizes: {', '.join(res.upper() for res in missing_lower)}"


def save_variant_warning_report(library_root, issues):
    if not library_root or not os.path.isdir(library_root):
        return None
    paths = library_state_paths(library_root)
    os.makedirs(paths["dir"], exist_ok=True)
    payload = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "issue_count": len(issues),
        "issues": issues,
    }
    save_json(paths["variant_warnings"], payload)
    lines = [
        "Missing lower-size variants report",
        f"Generated: {payload['generated_at']}",
        f"Issues: {payload['issue_count']}",
        "",
    ]
    for item in issues:
        lines.append(
            f"{item['preset']}/{item['name']} | found: {', '.join(res.upper() for res in item['found_resolutions']) or '-'} | missing: {', '.join(res.upper() for res in item['missing_lower'])}"
        )
    with open(paths["variant_warnings_txt"], "w", encoding="utf-8") as file_obj:
        file_obj.write("\n".join(lines).rstrip() + "\n")
    return paths["variant_warnings_txt"]


def repair_asset_folder(asset_path, asset_name, log):
    if not os.path.isdir(asset_path):
        return {"renamed": 0, "merged": 0, "warnings": 0, "warning_details": []}

    zip_files = [
        os.path.join(asset_path, name)
        for name in os.listdir(asset_path)
        if os.path.isfile(os.path.join(asset_path, name)) and name.lower().endswith(".zip")
    ]

    renamed = 0
    warnings = 0
    warning_details = []
    preview_source = None

    if zip_files:
        labeled_files = label_zip_variants(zip_files)
        found_res = []
        for item in labeled_files:
            file_path = item["path"]
            res = item["res"]
            ext = os.path.splitext(file_path)[1].lower() or ".zip"
            new_name = f"{asset_name}_{res}{ext}" if res else os.path.basename(file_path)
            destination = os.path.join(asset_path, new_name)
            found_res.append(res)
            if os.path.abspath(file_path) != os.path.abspath(destination):
                if os.path.exists(destination):
                    os.remove(destination)
                os.replace(file_path, destination)
                renamed += 1
                log(f"[RENAME] {os.path.basename(file_path)} -> {new_name}")
            else:
                destination = file_path
            if res in RES_LABELS and preview_source is None:
                preview_source = destination

        missing_lower = missing_variant_chain(found_res)
        if missing_lower:
            warnings += 1
            log(f"[CHECK] {asset_name} missing lower sizes: {', '.join(missing_lower)}")
            warning_details.append(
                {
                    "name": asset_name,
                    "path": asset_path,
                    "found_resolutions": sorted({res for res in found_res if res in RES_LABELS}, key=RES_LABELS.index),
                    "missing_lower": missing_lower,
                }
            )

        if preview_source:
            preview_path = extract_preview_from_zip(preview_source, asset_path, asset_name)
            if preview_path:
                log(f"[PREVIEW] refreshed {os.path.basename(preview_path)}")

    return {"renamed": renamed, "merged": 0, "warnings": warnings, "warning_details": warning_details}


def reorganize_existing_library(library_root, presets, rules, tags_db, log, progress, should_cancel=None):
    should_cancel = should_cancel or (lambda: False)
    assets = collect_existing_assets(library_root)
    total_steps = max(len(assets), 1)
    moved = 0

    for index, asset in enumerate(assets, start=1):
        if should_cancel():
            raise TaskCancelled()
        correct_preset = auto_pick(asset["name"], presets, rules)
        folder_names = os.listdir(asset["path"]) if os.path.isdir(asset["path"]) else []
        tags_db[asset["name"]] = merge_tags(
            tags_db.get(asset["name"], []),
            auto_tags_for_asset(asset["name"], correct_preset, folder_names),
        )
        progress(index, total_steps, f"Checking {asset['name']}")

        if asset["preset"] == correct_preset:
            log(f"[SKIP] {asset['name']} already in {asset['preset']}")
            continue

        target = os.path.join(library_root, correct_preset, asset["name"])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.abspath(asset["path"]) == os.path.abspath(target):
            continue
        if os.path.exists(target):
            merge_folder_contents(asset["path"], target, log)
            try:
                os.rmdir(asset["path"])
            except OSError:
                pass
            moved += 1
            log(f"[MERGED] {asset['folder_name']} -> {correct_preset}/{asset['name']}")
            continue
        shutil.move(asset["path"], target)
        moved += 1
        log(f"[REORG] {asset['folder_name']} : {asset['preset']} -> {correct_preset}/{asset['name']}")

    return {"moved": moved, "checked": len(assets)}


def repair_library_variants(library_root, presets, rules, tags_db, log, progress, should_cancel=None):
    should_cancel = should_cancel or (lambda: False)
    assets = collect_existing_assets(library_root)
    grouped = {}
    for asset in assets:
        key = (asset["preset"], asset["name"])
        grouped.setdefault(key, []).append(asset)

    total_steps = max(len(grouped), 1)
    moved = 0
    renamed = 0
    warnings = 0
    warning_details = []

    for index, ((preset, base_name), items) in enumerate(sorted(grouped.items()), start=1):
        if should_cancel():
            raise TaskCancelled()
        canonical_path = os.path.join(library_root, preset, base_name)
        progress(index, total_steps, f"Repairing {base_name}")

        primary = None
        for item in items:
            if os.path.abspath(item["path"]) == os.path.abspath(canonical_path):
                primary = item
                break
        if primary is None:
            primary = items[0]

        if os.path.abspath(primary["path"]) != os.path.abspath(canonical_path):
            os.makedirs(os.path.dirname(canonical_path), exist_ok=True)
            if os.path.exists(canonical_path):
                merge_folder_contents(primary["path"], canonical_path, log)
                try:
                    os.rmdir(primary["path"])
                except OSError:
                    pass
            else:
                shutil.move(primary["path"], canonical_path)
            moved += 1
            primary["path"] = canonical_path
            log(f"[FIX FOLDER] {primary['folder_name']} -> {base_name}")

        for item in items:
            if os.path.abspath(item["path"]) == os.path.abspath(primary["path"]):
                continue
            merge_folder_contents(item["path"], primary["path"], log)
            try:
                os.rmdir(item["path"])
            except OSError:
                pass
            moved += 1
            log(f"[MERGE FOLDER] {item['folder_name']} -> {base_name}")

        result = repair_asset_folder(primary["path"], base_name, log)
        renamed += result["renamed"]
        warnings += result["warnings"]
        for item in result.get("warning_details", []):
            warning_details.append(
                {
                    "name": base_name,
                    "preset": preset,
                    "path": primary["path"],
                    "found_resolutions": item.get("found_resolutions", []),
                    "missing_lower": item.get("missing_lower", []),
                }
            )

        folder_names = os.listdir(primary["path"]) if os.path.isdir(primary["path"]) else []
        correct_preset = auto_pick(base_name, presets, rules)
        tags_db[base_name] = merge_tags(
            tags_db.get(base_name, []),
            auto_tags_for_asset(base_name, correct_preset, folder_names),
        )

    return {
        "moved": moved,
        "renamed": renamed,
        "warnings": warnings,
        "checked": len(grouped),
        "warning_details": warning_details,
    }


def auto_tag_library_assets(library_root, tags_db, log, progress, should_cancel=None):
    should_cancel = should_cancel or (lambda: False)
    assets = collect_existing_assets(library_root)
    total_steps = max(len(assets), 1)
    updated = 0

    for index, asset in enumerate(assets, start=1):
        if should_cancel():
            raise TaskCancelled()
        names = os.listdir(asset["path"]) if os.path.isdir(asset["path"]) else []
        detected = auto_tags_for_asset(asset["name"], asset["preset"], names)
        merged = merge_tags(tags_db.get(asset["name"], []), detected)
        if merged != tags_db.get(asset["name"], []):
            updated += 1
            tags_db[asset["name"]] = merged
            log(f"[AUTO TAG] {asset['name']} -> {', '.join(merged) if merged else '-'}")
        progress(index, total_steps, f"Tagging {asset['name']}")

    return {"updated": updated, "checked": len(assets)}


def find_preview_image(asset_folder):
    if not os.path.isdir(asset_folder):
        return None
    candidates = []
    for name in os.listdir(asset_folder):
        low = name.lower()
        if "_thumb." in low:
            continue
        if low.endswith((".png", ".jpg", ".jpeg", ".webp")):
            score = 10 if "preview" in low else 0
            candidates.append((score, name))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1].lower()))
    return os.path.join(asset_folder, candidates[0][1])


def make_thumbnail(path, size=THUMB_SIZE):
    if not PIL_AVAILABLE or not path or not os.path.exists(path):
        return None
    try:
        image = Image.open(path).convert("RGB")
        image = ImageOps.contain(image, size)
        canvas = Image.new("RGB", size, CANVAS_BG)
        pos_x = (size[0] - image.width) // 2
        pos_y = (size[1] - image.height) // 2
        canvas.paste(image, (pos_x, pos_y))
        return ImageTk.PhotoImage(canvas)
    except Exception:
        return None


def open_folder(path):
    if not path or not os.path.exists(path):
        return
    try:
        os.startfile(path)
    except AttributeError:
        subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def build_asset_record(library_root, folder_path, asset_name, tags_db, asset_meta=None):
    preset = os.path.basename(os.path.dirname(folder_path))
    clean_name = clean_base(asset_name)
    rel = os.path.relpath(folder_path, library_root)
    file_names = os.listdir(folder_path) if os.path.isdir(folder_path) else []
    detected = auto_tags_for_asset(clean_name, preset, file_names)
    merged_tags = merge_tags(tags_db.get(clean_name, []), detected)
    preview = find_preview_image(folder_path)
    preview_thumb = ensure_preview_thumb(preview, folder_path, clean_name) if preview else None
    resolutions = sorted(
        detect_resolutions_in_folder(folder_path),
        key=lambda item: RES_LABELS.index(item) if item in RES_LABELS else 999,
    )
    missing_lower = missing_variant_chain(resolutions)
    modified = os.path.getmtime(folder_path) if os.path.exists(folder_path) else 0
    meta = (asset_meta or {}).get(clean_name, {})
    source_group = meta.get("source_group", "Unknown")
    source_groups = meta.get("source_groups", [source_group] if source_group else [])
    return {
        "name": clean_name,
        "folder_name": asset_name,
        "path": folder_path,
        "rel": rel,
        "preset": preset,
        "source_group": source_group,
        "source_groups": source_groups,
        "tags": merged_tags,
        "preview": preview,
        "preview_thumb": preview_thumb,
        "resolutions": resolutions,
        "missing_lower": missing_lower,
        "variant_warning": format_variant_warning(missing_lower),
        "modified": modified,
    }


def sort_assets(items, sort_by):
    if sort_by == "Name Z-A":
        return sorted(items, key=lambda item: item["name"].lower(), reverse=True)
    if sort_by == "Preset A-Z":
        return sorted(items, key=lambda item: (item["preset"].lower(), item["name"].lower()))
    if sort_by == "Newest":
        return sorted(items, key=lambda item: item["modified"], reverse=True)
    if sort_by == "Oldest":
        return sorted(items, key=lambda item: item["modified"])
    if sort_by == "Most Tags":
        return sorted(items, key=lambda item: (-len(item["tags"]), item["name"].lower()))
    if sort_by == "Resolution High-Low":
        return sorted(
            items,
            key=lambda item: (-resolution_score(item["resolutions"]), item["name"].lower()),
        )
    return sorted(items, key=lambda item: item["name"].lower())


def search_assets(library_root, search_root, query, tags_db, sort_by, asset_meta=None):
    results = []
    query_norm = normalize(query)
    if not library_root or not os.path.isdir(library_root):
        return results

    base_path = (
        os.path.join(library_root, search_root)
        if search_root and search_root != "All"
        else library_root
    )
    if not os.path.isdir(base_path):
        return results

    for root_dir, dirs, _files in os.walk(base_path):
        dirs[:] = [directory for directory in dirs if directory != PORTABLE_STATE_DIR]
        for directory in dirs:
            folder_path = os.path.join(root_dir, directory)
            if root_dir == library_root:
                continue
            asset = build_asset_record(library_root, folder_path, directory, tags_db, asset_meta)
            haystack = " ".join(
                [
                    normalize(asset["name"]),
                    normalize(asset["rel"]),
                    normalize(asset["preset"]),
                    " ".join(asset["tags"]),
                ]
            )
            if not query_norm or query_norm in haystack:
                results.append(asset)

    unique = {item["path"]: item for item in results}
    return sort_assets(list(unique.values()), sort_by)


def move_asset_to_preset(asset, target_preset, library_root):
    old_path = asset["path"]
    new_path = os.path.join(library_root, target_preset, asset["name"])
    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    if os.path.abspath(old_path) == os.path.abspath(new_path):
        return new_path
    if os.path.exists(new_path):
        merge_folder_contents(old_path, new_path, lambda _msg: None)
        try:
            os.rmdir(old_path)
        except OSError:
            pass
        return new_path
    shutil.move(old_path, new_path)
    return new_path


class ThumbTile(ttk.Frame):
    def __init__(self, master, app, asset, index):
        super().__init__(master, padding=10, style="Card.TFrame")
        self.app = app
        self.asset = asset
        self.index = index
        self.thumb = make_thumbnail(asset.get("preview_thumb") or asset.get("preview"))

        self.columnconfigure(0, weight=1)

        preview_holder = tk.Frame(self, bg=CANVAS_BG, width=THUMB_SIZE[0], height=THUMB_SIZE[1], bd=0)
        preview_holder.grid(row=0, column=0, sticky="ew")
        preview_holder.grid_propagate(False)

        self.img_label = tk.Label(
            preview_holder,
            image=self.thumb,
            text="No preview" if not self.thumb else "",
            compound="center",
            bg=CANVAS_BG,
            fg="#5a6472",
        )
        self.img_label.place(relx=0.5, rely=0.5, anchor="center")
        self.preview_button = tk.Button(
            preview_holder,
            text="🔍",
            command=lambda: self.app.open_asset_preview_by_index(self.index),
            relief="flat",
            bd=0,
            bg="#B4232C",
            activebackground="#8F1D24",
            activeforeground="white",
            fg="white",
            font=("Segoe UI Symbol", 10),
            cursor="hand2",
            padx=6,
            pady=2,
        )
        self.preview_button.place(relx=1.0, rely=0.0, anchor="ne", x=-6, y=6)

        self.name_label = tk.Label(
            self,
            text=asset["name"],
            wraplength=TILE_WIDTH - 28,
            font=("Segoe UI", 11, "bold"),
            bg=CARD_BG,
            fg="#1A1A2E",
            anchor="w",
            justify="left",
        )
        self.name_label.grid(row=1, column=0, sticky="w", pady=(10, 3))

        self.meta_label = ttk.Label(
            self,
            text=f"{asset['preset']} | {os.path.basename(asset['path'])}",
            wraplength=TILE_WIDTH - 28,
            style="Meta.TLabel",
        )
        self.meta_label.grid(row=2, column=0, sticky="w")

        res_frame = ttk.Frame(self)
        res_frame.grid(row=3, column=0, sticky="w", pady=(10, 0))
        found = set(asset.get("resolutions", []))
        for res in RES_LABELS:
            label = tk.Label(
                res_frame,
                text=res.upper(),
                font=("Segoe UI Semibold", 8),
                padx=6,
                pady=3,
                bg="#22C55E" if res in found else BADGE_BG,
                fg="white",
                bd=0,
            )
            label.pack(side="left", padx=2)

        tags = ", ".join(asset.get("tags", [])) if asset.get("tags") else "-"
        self.tags_label = ttk.Label(self, text=f"tags: {tags}", wraplength=TILE_WIDTH - 28, style="Tags.TLabel")
        self.tags_label.grid(row=4, column=0, sticky="w", pady=(10, 0))
        warning_text = asset.get("variant_warning", "")
        self.warning_label = None
        if warning_text:
            self.warning_label = tk.Label(
                self,
                text=warning_text,
                wraplength=TILE_WIDTH - 28,
                bg=CARD_BG,
                fg="#B4232C",
                font=("Segoe UI", 8, "bold"),
                anchor="w",
                justify="left",
            )
            self.warning_label.grid(row=5, column=0, sticky="w", pady=(8, 0))

        for widget in [
            self,
            preview_holder,
            self.img_label,
            self.name_label,
            self.meta_label,
            self.tags_label,
        ]:
            widget.bind("<Button-1>", self.on_click)
            widget.bind("<Double-Button-1>", self.on_double_click)
            widget.bind("<Button-3>", self.on_right_click)
            widget.bind("<ButtonPress-1>", self.on_drag_start)
            widget.bind("<B1-Motion>", self.on_drag_motion)
            widget.bind("<ButtonRelease-1>", self.on_drag_release)
        if self.warning_label is not None:
            self.warning_label.bind("<Button-1>", self.on_click)
            self.warning_label.bind("<Double-Button-1>", self.on_double_click)
            self.warning_label.bind("<Button-3>", self.on_right_click)
            self.warning_label.bind("<ButtonPress-1>", self.on_drag_start)
            self.warning_label.bind("<B1-Motion>", self.on_drag_motion)
            self.warning_label.bind("<ButtonRelease-1>", self.on_drag_release)

    def on_click(self, event=None):
        additive = bool(event and (event.state & 0x0001) != 0)
        self.app.select_thumb(self.index, additive=additive)

    def on_double_click(self, _event=None):
        self.app.open_asset_folder_by_index(self.index)

    def on_right_click(self, event):
        self.app.select_thumb(self.index, additive=False)
        self.app.show_asset_context_menu(event)

    def on_drag_start(self, _event):
        self.app.start_drag_from_index(self.index)

    def on_drag_motion(self, _event=None):
        self.app.update_drag_motion()

    def on_drag_release(self, event):
        self.app.finish_drag_release(event)

    def set_selected(self, value):
        style_name = "SelectedCard.TFrame" if value else "Card.TFrame"
        self.configure(style=style_name)


# ====================================================================== #
#  v2 — Poliigon Weekly Checker                                          #
# ====================================================================== #

POLIIGON_FREE_TEXTURES_URL = "https://www.poliigon.com/textures/free"
POLIIGON_FREE_MODELS_URL = "https://www.poliigon.com/models/free"
POLIIGON_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
POLIIGON_MIN_INTERVAL_SEC = 30  # at most ~2 requests/min combined with random delay


class PoliigonChecker:
    """Lightweight scraper for free textures/models on poliigon.com.

    Heavily rate-limited and dependency-tolerant: returns gracefully if requests
    or beautifulsoup4 are not installed.
    """

    def __init__(self, seen_path=SEEN_ASSETS_FILE, state_path=POLIIGON_CHECK_STATE_FILE):
        self.seen_path = seen_path
        self.state_path = state_path
        self.seen = load_json(self.seen_path, {"textures": [], "models": []})
        self.state = load_json(self.state_path, {"last_check": 0})
        self._lock = threading.Lock()
        self._last_request_ts = 0.0

    # -- persistence -- #
    def save(self):
        save_json(self.seen_path, self.seen)
        save_json(self.state_path, self.state)

    def days_since_last_check(self):
        last = self.state.get("last_check", 0)
        if not last:
            return None
        return (time.time() - last) / 86400.0

    def should_auto_check(self, interval_days=7):
        d = self.days_since_last_check()
        return d is None or d >= interval_days

    # -- low-level fetch -- #
    def _polite_delay(self):
        # ensure at least POLIIGON_MIN_INTERVAL_SEC between requests, plus jitter
        elapsed = time.time() - self._last_request_ts
        wait = max(0.0, POLIIGON_MIN_INTERVAL_SEC - elapsed)
        wait += random.uniform(3.0, 8.0)
        time.sleep(wait)

    def _fetch(self, url, timeout=20):
        if not REQUESTS_AVAILABLE:
            # Fallback to urllib so the feature still works without `requests`.
            req = urllib.request.Request(url, headers={"User-Agent": POLIIGON_USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        headers = {
            "User-Agent": POLIIGON_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.text

    # -- parsing -- #
    def _parse_assets(self, html, kind):
        """Return list[dict(name, url, thumb, category, kind)]. Best-effort parsing."""
        results = []
        if not html:
            return results

        if BS4_AVAILABLE:
            soup = BeautifulSoup(html, "html.parser")
            # Generic strategy: find anchors containing /textures/ or /models/ with images
            link_pattern = "/textures/" if kind == "texture" else "/models/"
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if link_pattern not in href or href.rstrip("/").endswith(link_pattern.strip("/")):
                    continue
                full_url = href if href.startswith("http") else "https://www.poliigon.com" + href
                slug = href.rstrip("/").split("/")[-1]
                if not slug or slug in ("free", "browse"):
                    continue
                img = a.find("img")
                thumb = ""
                if img:
                    thumb = img.get("src") or img.get("data-src") or ""
                name = (img.get("alt") if img else None) or slug.replace("-", " ").title()
                # Try to spot category in nearby text
                category = ""
                parent_text = a.get_text(" ", strip=True)
                if parent_text and len(parent_text) < 80:
                    category = parent_text
                results.append({
                    "id": slug,
                    "name": name,
                    "url": full_url,
                    "thumb": thumb,
                    "category": category,
                    "kind": kind,
                })
        else:
            # naive regex fallback
            pattern = r'href="(/(?:textures|models)/[^"#?]+)"'
            for m in re.finditer(pattern, html):
                href = m.group(1)
                slug = href.rstrip("/").split("/")[-1]
                if slug in ("free", "browse"):
                    continue
                results.append({
                    "id": slug,
                    "name": slug.replace("-", " ").title(),
                    "url": "https://www.poliigon.com" + href,
                    "thumb": "",
                    "category": "",
                    "kind": kind,
                })

        # de-dup within page
        unique = {}
        for item in results:
            unique.setdefault(item["id"], item)
        return list(unique.values())

    # -- public API -- #
    def check(self, on_log=None):
        """Run a check across both feeds; return list of NEW assets."""
        on_log = on_log or (lambda _msg: None)
        new_items = []
        with self._lock:
            for kind, url, key in (
                ("texture", POLIIGON_FREE_TEXTURES_URL, "textures"),
                ("model", POLIIGON_FREE_MODELS_URL, "models"),
            ):
                try:
                    self._polite_delay()
                    on_log(f"[POLIIGON] fetching {url}")
                    html = self._fetch(url)
                    self._last_request_ts = time.time()
                    parsed = self._parse_assets(html, kind)
                    on_log(f"[POLIIGON] parsed {len(parsed)} {kind}(s)")
                    seen_ids = set(self.seen.get(key, []))
                    for item in parsed:
                        if item["id"] not in seen_ids:
                            item["discovered"] = datetime.datetime.now().isoformat(timespec="seconds")
                            new_items.append(item)
                            seen_ids.add(item["id"])
                    self.seen[key] = sorted(seen_ids)
                except Exception as exc:
                    on_log(f"[POLIIGON][ERROR] {kind}: {exc}")
            self.state["last_check"] = time.time()
            self.save()
        return new_items


# ====================================================================== #
#  v2 — Library statistics                                                #
# ====================================================================== #

class LibraryStats:
    """Compute texture/model counts, size, resolutions for a library root."""

    @staticmethod
    def _human_size(num_bytes):
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(num_bytes)
        for unit in units:
            if size < 1024.0 or unit == units[-1]:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{num_bytes} B"

    @classmethod
    def compute(cls, library_root):
        result = {
            "library_root": library_root,
            "total_folders": 0,
            "preset_breakdown": {},
            "total_size_bytes": 0,
            "total_size_human": "0 B",
            "resolutions": {},
            "zip_count": 0,
            "computed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        if not library_root or not os.path.isdir(library_root):
            return result

        for preset in sorted(os.listdir(library_root)):
            preset_path = os.path.join(library_root, preset)
            if not os.path.isdir(preset_path) or preset.startswith("."):
                continue
            preset_count = 0
            for asset_name in os.listdir(preset_path):
                asset_path = os.path.join(preset_path, asset_name)
                if not os.path.isdir(asset_path):
                    continue
                preset_count += 1
                result["total_folders"] += 1
                # walk asset for size, zips, resolutions
                for dirpath, _dirs, files in os.walk(asset_path):
                    for fname in files:
                        full = os.path.join(dirpath, fname)
                        try:
                            result["total_size_bytes"] += os.path.getsize(full)
                        except OSError:
                            pass
                        lower = fname.lower()
                        if lower.endswith(".zip"):
                            result["zip_count"] += 1
                        for res in RES_LABELS:
                            if re.search(rf"(?<![a-z0-9]){res}(?![a-z0-9])", lower):
                                result["resolutions"][res] = result["resolutions"].get(res, 0) + 1
                                break
            if preset_count:
                result["preset_breakdown"][preset] = preset_count

        result["total_size_human"] = cls._human_size(result["total_size_bytes"])
        return result


# ====================================================================== #
#  v2 — Splash screen                                                     #
# ====================================================================== #

def show_splash(parent, duration_ms=2000):
    """Display a simple splash window with the app logo for a couple of seconds."""
    try:
        splash = tk.Toplevel(parent)
        splash.overrideredirect(True)
        splash.configure(bg=CONTENT_BG)
        w, h = 420, 220
        sw = parent.winfo_screenwidth()
        sh = parent.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        splash.geometry(f"{w}x{h}+{x}+{y}")
        splash.attributes("-topmost", True)

        frame = tk.Frame(splash, bg=CONTENT_BG, bd=2, relief="ridge")
        frame.pack(fill="both", expand=True)

        if PIL_AVAILABLE and os.path.exists(LOGO_ICO_PATH):
            try:
                img = Image.open(LOGO_ICO_PATH)
                img.thumbnail((96, 96))
                splash._photo = ImageTk.PhotoImage(img)
                tk.Label(frame, image=splash._photo, bg=CONTENT_BG).pack(pady=(20, 6))
            except Exception:
                pass
        tk.Label(
            frame,
            text=APP_TITLE,
            bg=CONTENT_BG,
            fg=CONTENT_TEXT,
            font=("Segoe UI Semibold", 14),
        ).pack()
        tk.Label(
            frame,
            text="Loading library…",
            bg=CONTENT_BG,
            fg="#DDB9B2",
            font=("Segoe UI", 10),
        ).pack(pady=(4, 0))
        tk.Label(
            frame,
            text="Made by BBBViz · Texture for I8 Studio",
            bg=CONTENT_BG,
            fg="#8E6F6C",
            font=("Segoe UI", 8),
        ).pack(side="bottom", pady=8)

        splash.after(duration_ms, splash.destroy)
        return splash
    except Exception:
        return None


# ====================================================================== #
#  v2 — Embedded addon source code (exported via Tools menu)              #
# ====================================================================== #

BLENDER_ADDON_FILENAME = "blender_addon.py"
MAX_ADDON_FILENAME = "max_addon_macroscript.ms"

BLENDER_ADDON_CODE_PATH = os.path.join(app_dir(), BLENDER_ADDON_FILENAME)
MAX_ADDON_CODE_PATH = os.path.join(app_dir(), MAX_ADDON_FILENAME)


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_json(CONFIG_FILE, {})
        self.rules = load_json(LEARNING_FILE, [])
        self.tags_db = load_json(TAGS_FILE, {})
        self.asset_meta = {}
        self.drag_assets = []
        self._asset_cache = []
        self._search_cache = []
        self._missing_variant_issues = []
        self._missing_variant_report_path = ""
        self.source_group_filter = tk.StringVar(value="All folders")
        self.selected_indices = set()
        self.thumb_tiles = []
        self.ui_queue = queue.Queue()
        self.worker = None
        self._search_timer = None
        self._cancel_flag = threading.Event()
        self._data_lock = threading.Lock()
        self.normalize_preset_config()

        self.poliigon_checker = PoliigonChecker()
        self.poliigon_new_items = []  # latest "new" items returned from Check Now
        self.stats_data = None
        self.preview_data = None  # last 3D preview info
        self._asset_preview_window = None
        self._asset_preview_canvas = None
        self._asset_preview_image_id = None
        self._asset_preview_title = None
        self._asset_preview_source = None
        self._asset_preview_photo = None
        self._asset_preview_zoom = 1.0
        self._asset_preview_cache = {}
        self._asset_preview_base_image = None

        self.root.title(APP_TITLE)
        self.root.geometry("1460x900")
        self.root.configure(bg=CONTENT_BG)
        self.set_window_icon()
        self.configure_styles()

        # Splash screen for ~2s before building UI fully
        try:
            show_splash(self.root, duration_ms=2000)
        except Exception:
            pass

        self.build()
        # auto poliigon check (non-blocking) if more than 7 days passed
        try:
            if self.poliigon_checker.should_auto_check(7):
                self.root.after(3000, self.poliigon_check_async)
        except Exception:
            pass
        initial_library = self.cfg.get("library_root", "")
        if initial_library and os.path.isdir(initial_library):
            self.load_library_state(initial_library)
        else:
            self.refresh_presets_from_library()
            self.refresh_rule_list()
            self.refresh_search_results()
        self.root.after(100, self.process_ui_queue)
        self.root.bind("<Control-s>", lambda _event: self.save_state())
        self.root.bind("<Control-f>", lambda _event: self.focus_search())
        self.root.bind("<Control-a>", lambda _event: self.select_all())

    def set_window_icon(self):
        ico_path = os.path.join(app_dir(), "logo.ico")
        png_path = os.path.join(app_dir(), "logo.png")
        try:
            if sys.platform.startswith("win"):
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
            if os.path.exists(ico_path):
                self.root.iconbitmap(ico_path)
            if PIL_AVAILABLE and os.path.exists(ico_path):
                image = Image.open(ico_path)
                self._icon_img = ImageTk.PhotoImage(image)
                self.root.iconphoto(True, self._icon_img)
            elif os.path.exists(png_path):
                self._icon_img = tk.PhotoImage(file=png_path)
                self.root.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def configure_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Card.TFrame", relief="groove", borderwidth=1, background=CARD_BG, padding=12)
        style.configure("SelectedCard.TFrame", relief="groove", borderwidth=2, background="#F9E0DE", padding=12)
        style.configure("SidebarCard.TFrame", background=SIDEBAR_CARD)
        style.configure("SidebarTitle.TLabel", background=SIDEBAR_BG, foreground=SIDEBAR_FG, font=("Segoe UI Semibold", 11))
        style.configure("SidebarBody.TLabel", background=SIDEBAR_BG, foreground="#D8B4AD", font=("Segoe UI", 9))
        style.configure("ContentTitle.TLabel", background=CONTENT_BG, foreground=CONTENT_TEXT, font=("Segoe UI Semibold", 10))
        style.configure("Meta.TLabel", background=CARD_BG, foreground="#6B4C4C", font=("Segoe UI", 9))
        style.configure("Tags.TLabel", background=CARD_BG, foreground="#8B5E5E", font=("Segoe UI", 9, "italic"))
        style.configure("TLabel", background=CONTENT_BG, foreground=CONTENT_TEXT)
        style.configure(
            "TEntry",
            fieldbackground="#FDF7F4",
            foreground="#2A1315",
            bordercolor=SIDEBAR_BORDER,
            lightcolor=SIDEBAR_BORDER,
            darkcolor=SIDEBAR_BORDER,
            padding=6,
        )
        style.configure(
            "TCombobox",
            fieldbackground="#FDF7F4",
            foreground="#2A1315",
            bordercolor=SIDEBAR_BORDER,
            arrowsize=14,
            padding=5,
        )
        style.map("TCombobox", fieldbackground=[("readonly", "#FDF7F4")], foreground=[("readonly", "#2A1315")])
        style.configure(
            "TProgressbar",
            troughcolor="#432022",
            background=PRIMARY,
            bordercolor="#432022",
            lightcolor=PRIMARY_HOVER,
            darkcolor=PRIMARY,
        )

        # ----- v2 styles ----- #
        style.configure("TNotebook", background=CONTENT_BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            padding=(18, 8),
            background=SIDEBAR_CARD,
            foreground=SIDEBAR_FG,
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", PRIMARY)],
            foreground=[("selected", "white")],
        )
        # Big primary button used for Organize / Reorganize / Repair
        style.configure(
            "Primary.TButton",
            background=PRIMARY,
            foreground="white",
            font=("Segoe UI Semibold", 11),
            padding=(18, 12),
            borderwidth=0,
            focusthickness=3,
            focuscolor=PRIMARY_HOVER,
        )
        style.map(
            "Primary.TButton",
            background=[("active", PRIMARY_HOVER), ("pressed", ACCENT)],
            foreground=[("disabled", "#999999")],
        )
        style.configure(
            "Stat.TLabel",
            background=SIDEBAR_CARD,
            foreground=SIDEBAR_FG,
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "StatValue.TLabel",
            background=SIDEBAR_CARD,
            foreground="#F9E1DC",
            font=("Segoe UI Semibold", 16),
        )
        # Default font for everything: Segoe UI 10
        try:
            self.root.option_add("*Font", "{Segoe UI} 10")
        except Exception:
            pass

    def build(self):
        # v2: top-level notebook. Original three-pane layout becomes the "Library" tab.
        self.build_menubar()
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        library_tab = tk.Frame(self.notebook, bg=CONTENT_BG)
        self.notebook.add(library_tab, text="Library")

        main = ttk.Panedwindow(library_tab, orient=tk.HORIZONTAL)
        main.pack(fill="both", expand=True)

        left = tk.Frame(main, bg=SIDEBAR_BG, padx=12, pady=12)
        mid = tk.Frame(main, bg=SIDEBAR_BG, padx=12, pady=12)
        right = tk.Frame(main, bg=CONTENT_BG, padx=10, pady=10)
        main.add(left, weight=2)
        main.add(mid, weight=2)
        main.add(right, weight=6)

        self.lib = tk.StringVar(value=self.cfg.get("library_root", ""))
        self.src = tk.StringVar(value=self.cfg.get("watch_folder", ""))
        self.search_query = tk.StringVar()
        self.search_root = tk.StringVar(value="All")
        self.sort_by = tk.StringVar(value=self.cfg.get("sort_by", SORT_OPTIONS[0]))
        self.drag_status = tk.StringVar(value="Ready")
        self.status_text = tk.StringVar(value="Idle")
        self.progress_text = tk.StringVar(value="Ready")
        self.tag_entry = tk.StringVar()
        self.collect_target = tk.StringVar(value="All")
        self.show_state_folders = tk.BooleanVar(value=False)

        self.load_logo(left)
        library_section = self.make_sidebar_section(left, "Root Folder", "Folder chứa tất cả thư viện cấp 1 như !!_ASPHAL, !!_BRICK...")
        lib_row = ttk.Frame(library_section)
        lib_row.pack(fill="x")
        self.lib_entry = ttk.Entry(lib_row, textvariable=self.lib)
        self.lib_entry.pack(side="left", fill="x", expand=True)
        self.lib_browse = ttk.Button(lib_row, text="Chọn", command=self.choose_library_root)
        self.lib_browse.pack(side="left", padx=(6, 0))

        self.refresh_presets_button = ttk.Button(
            library_section,
            text="Làm mới preset từ thư viện",
            command=self.refresh_presets_from_library,
        )
        self.refresh_presets_button.pack(fill="x", pady=(6, 0))

        source_section = self.make_sidebar_section(left, "Nguồn ZIP", "Chọn folder gốc chứa ZIP tải về. App sẽ quét đệ quy trong đó.")
        src_row = ttk.Frame(source_section)
        src_row.pack(fill="x")
        self.src_entry = ttk.Entry(src_row, textvariable=self.src)
        self.src_entry.pack(side="left", fill="x", expand=True)
        self.src_browse = ttk.Button(src_row, text="Chọn", command=self.choose_download_folder)
        self.src_browse.pack(side="left", padx=(6, 0))

        actions_section = self.make_sidebar_section(left, "Tác vụ chính", "Mỗi nút có mô tả tiếng Việt ngắn ngay bên dưới.")
        actions_grid = tk.Frame(actions_section, bg=SIDEBAR_CARD)
        actions_grid.pack(fill="x")
        actions_grid.columnconfigure(0, weight=1)
        actions_grid.columnconfigure(1, weight=1)
        self.run_button = self.make_action_card(actions_grid, 0, 0, "Run", "Quét ZIP mới và đưa vào thư viện.", self.run)
        self.rerun_button = self.make_action_card(actions_grid, 0, 1, "Run Again", "Chạy lại nguồn cũ mà không cần chọn lại.", self.run_again)
        self.reorg_button = self.make_action_card(actions_grid, 1, 0, "Reorganize", "Sắp xếp lại thư viện hiện có theo preset.", self.reorganize_library)
        self.repair_button = self.make_action_card(actions_grid, 1, 1, "Repair", "Gộp folder sai và sửa suffix ZIP.", self.repair_library)
        self.autotag_button = self.make_action_card(actions_grid, 2, 0, "Auto Tag", "Tự detect và bổ sung tag cho asset.", self.auto_detect_tags)
        self.cancel_button = self.make_action_card(actions_grid, 2, 1, "Cancel", "Dừng tác vụ nền đang chạy.", self.cancel_task, state="disabled", accent=True)
        self.save_button = self.make_action_card(actions_grid, 3, 0, "Save", "Lưu config, rules và tag hiện tại.", self.save_state)
        self.teach_button = self.make_action_card(actions_grid, 3, 1, "Teach", "Dạy app rule mới cho preset.", self.learn_ui)
        self.help_button = self.make_action_card(actions_grid, 4, 0, "Help", "Mở hướng dẫn sử dụng tiếng Việt.", self.show_help)

        progress_section = self.make_sidebar_section(left, "Tiến trình", "Trạng thái chạy thật và log xử lý.")
        self.progress_bar = ttk.Progressbar(progress_section, mode="determinate", maximum=100)
        self.progress_bar.pack(fill="x", pady=(0, 4))
        tk.Label(progress_section, textvariable=self.progress_text, bg=SIDEBAR_CARD, fg=SIDEBAR_FG, font=("Segoe UI Semibold", 10)).pack(anchor="w")
        tk.Label(progress_section, textvariable=self.status_text, bg=SIDEBAR_CARD, fg="#F7B7B2", wraplength=300, justify="left").pack(anchor="w", pady=(0, 8))

        self.logbox = scrolledtext.ScrolledText(
            progress_section,
            height=18,
            bg="#17090B",
            fg="#FBEDEA",
            insertbackground="#FBEDEA",
            relief="flat",
            padx=10,
            pady=10,
        )
        self.logbox.pack(fill="both", expand=True)

        rules_section = self.make_sidebar_section(mid, "Preset và Rule", "Kéo texture thả vào đây để đổi preset và dạy rule.")
        self.rule_list = tk.Listbox(
            rules_section,
            exportselection=False,
            bg="#16090B",
            fg=SIDEBAR_FG,
            selectbackground=PRIMARY,
            selectforeground="white",
            relief="flat",
            highlightthickness=0,
        )
        self.rule_list.pack(fill="both", expand=True)
        self.rule_list.bind("<ButtonRelease-1>", self.on_rule_drop)

        rule_btns = ttk.Frame(rules_section)
        rule_btns.pack(fill="x", pady=8)
        self.delete_rule_button = ttk.Button(rule_btns, text="Xóa rule", command=self.delete_selected_rule)
        self.delete_rule_button.pack(side="left")
        ttk.Button(rule_btns, text="Làm mới rule", command=self.refresh_rule_list).pack(side="left", padx=6)
        ttk.Button(rule_btns, text="Thêm preset", command=self.add_custom_preset).pack(side="left", padx=6)
        ttk.Button(rule_btns, text="Xóa preset", command=self.delete_custom_preset).pack(side="left", padx=6)
        tk.Label(rules_section, textvariable=self.drag_status, wraplength=280, justify="left", bg=SIDEBAR_CARD, fg="#D7B0A9").pack(anchor="w", pady=(4, 0))

        source_filter_section = self.make_sidebar_section(mid, "Thư viện cấp 1", "Liệt kê các folder cấp 1 trong Root Folder để lọc thumb cho gọn.")
        self.source_group_list = tk.Listbox(
            source_filter_section,
            exportselection=False,
            height=18,
            bg="#16090B",
            fg=SIDEBAR_FG,
            selectbackground=PRIMARY,
            selectforeground="white",
            relief="flat",
            highlightthickness=0,
        )
        self.source_group_list.pack(fill="both", expand=True)
        self.source_group_list.bind("<<ListboxSelect>>", self.on_source_group_selected)
        ttk.Checkbutton(
            source_filter_section,
            text="Hiện state folders",
            variable=self.show_state_folders,
            command=self.on_state_folder_toggle,
        ).pack(anchor="w", pady=(8, 0))

        hero = tk.Frame(right, bg=CONTENT_PANEL, padx=16, pady=14, highlightbackground=SIDEBAR_BORDER, highlightthickness=1)
        hero.pack(fill="x", pady=(0, 10))
        tk.Label(hero, text=APP_TITLE, bg=CONTENT_PANEL, fg=CONTENT_TEXT, font=("Segoe UI Semibold", 15)).pack(anchor="w")
        tk.Label(
            hero,
            text="Giao diện đỏ thẫm, thao tác gọn, tập trung vào preset, preview, suffix size và tag.",
            bg=CONTENT_PANEL,
            fg="#DDB9B2",
            font=("Segoe UI", 9),
            wraplength=760,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        control_panel = tk.Frame(right, bg=CONTENT_PANEL, padx=12, pady=12, highlightbackground=SIDEBAR_BORDER, highlightthickness=1)
        control_panel.pack(fill="x", pady=(0, 10))

        topbar = ttk.Frame(control_panel)
        topbar.pack(fill="x")
        topbar.columnconfigure(0, weight=2)
        topbar.columnconfigure(1, weight=1)
        topbar.columnconfigure(2, weight=1)

        ttk.Label(topbar, text="Tìm kiếm").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(topbar, text="Thư viện cấp 1").grid(row=0, column=1, sticky="w", padx=(12, 0), pady=(0, 6))
        ttk.Label(topbar, text="Sắp xếp").grid(row=0, column=2, sticky="w", padx=(12, 0), pady=(0, 6))

        self.search_entry = ttk.Entry(topbar, textvariable=self.search_query)
        self.search_entry.grid(row=1, column=0, sticky="ew")
        self.search_root_combo = ttk.Combobox(topbar, textvariable=self.search_root, state="readonly")
        self.search_root_combo.grid(row=1, column=1, sticky="ew", padx=(12, 0))
        self.sort_combo = ttk.Combobox(topbar, textvariable=self.sort_by, values=SORT_OPTIONS, state="readonly")
        self.sort_combo.grid(row=1, column=2, sticky="ew", padx=(12, 0))

        self.search_query.trace_add("write", lambda *_args: self.debounced_search())
        self.search_root_combo.bind("<<ComboboxSelected>>", self.on_level1_combo_changed)
        self.sort_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_sort_changed())

        actionbar = tk.Frame(control_panel, bg=CONTENT_PANEL)
        actionbar.pack(fill="x", pady=(12, 10))
        actionbar.columnconfigure(0, weight=1)
        actionbar.columnconfigure(1, weight=1)
        actionbar.columnconfigure(2, weight=1)
        actionbar.columnconfigure(3, weight=1)
        self.make_inline_action(actionbar, "Collect selected", "Gom các tile đã chọn vào thư viện cấp 1 bạn chỉ định.", self.bulk_move_selected).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.make_inline_action(actionbar, "Tag selected", "Gắn tag thủ công cho nhóm đã chọn.", self.bulk_tag_selected).grid(row=0, column=1, sticky="ew", padx=8)
        self.make_inline_action(actionbar, "Auto tag selected", "Tự sinh tag cho nhóm đã chọn.", self.auto_tag_selected).grid(row=0, column=2, sticky="ew", padx=8)
        self.make_inline_action(actionbar, "Clear selection", "Bỏ chọn toàn bộ tile hiện tại.", self.clear_selection).grid(row=0, column=3, sticky="ew", padx=(8, 0))

        tagbar = ttk.Frame(control_panel)
        tagbar.pack(fill="x", pady=(2, 10))
        ttk.Entry(tagbar, textvariable=self.tag_entry).pack(side="left", fill="x", expand=True)
        ttk.Button(tagbar, text="Thêm tag", command=self.add_tag_to_selected_asset).pack(side="left", padx=6)

        collectbar = ttk.Frame(control_panel)
        collectbar.pack(fill="x", pady=(0, 10))
        ttk.Label(collectbar, text="Collect -> Thư viện cấp 1").pack(side="left")
        self.collect_target_combo = ttk.Combobox(collectbar, textvariable=self.collect_target, state="readonly", width=24)
        self.collect_target_combo.pack(side="left", padx=8)
        ttk.Button(collectbar, text="Collect selected", command=self.bulk_move_selected).pack(side="left")

        self.result_info = tk.StringVar(value="0 assets")
        ttk.Label(control_panel, textvariable=self.result_info, foreground="#DDB9B2").pack(anchor="w")

        results_panel = tk.Frame(right, bg=CONTENT_PANEL, padx=1, pady=1, highlightbackground=SIDEBAR_BORDER, highlightthickness=1)
        results_panel.pack(fill="both", expand=True)
        self.thumb_canvas = tk.Canvas(results_panel, background="#1A0C0E", highlightthickness=0)
        self.thumb_scroll = ttk.Scrollbar(results_panel, orient="vertical", command=self.thumb_canvas.yview)
        self.thumb_frame = ttk.Frame(self.thumb_canvas)
        self.thumb_window = self.thumb_canvas.create_window((0, 0), window=self.thumb_frame, anchor="nw")
        self.thumb_canvas.configure(yscrollcommand=self.thumb_scroll.set)
        self.thumb_canvas.pack(side="left", fill="both", expand=True)
        self.thumb_scroll.pack(side="right", fill="y")

        self.thumb_frame.bind("<Configure>", self.on_thumb_frame_configure)
        self.thumb_canvas.bind("<Configure>", self.on_thumb_canvas_configure)
        self.thumb_canvas.bind_all("<MouseWheel>", self.on_mousewheel)

        self.asset_menu = tk.Menu(self.root, tearoff=0)
        self.asset_menu.add_command(label="Open folder", command=self.context_open_folder)
        self.asset_menu.add_command(label="Copy path", command=self.context_copy_path)
        self.asset_menu.add_command(label="Remove tag", command=self.context_remove_tag)
        self.asset_menu.add_command(label="Reassign preset", command=self.context_reassign_preset)

        ToolTip(self.run_button, "Quét ZIP từ nguồn và đưa vào thư viện")
        ToolTip(self.rerun_button, "Chạy lại folder nguồn cũ mà không cần browse lại")
        ToolTip(self.reorg_button, "Sắp xếp lại thư viện hiện có theo preset")
        ToolTip(self.repair_button, "Gộp folder _2k/_4k/_8k và sửa tên ZIP")
        ToolTip(self.autotag_button, "Tự động suy ra tag cho asset hiện có")
        ToolTip(self.cancel_button, "Dừng tác vụ nền đang chạy")
        ToolTip(self.help_button, "Mở hướng dẫn sử dụng tiếng Việt")

        credit = tk.Label(
            self.root,
            text="App made by BBBviz — Material by I8Studio",
            bg=SIDEBAR_BG,
            fg="#D7B0A9",
            font=("Segoe UI", 9),
        )
        credit.config(text="Made by BBBViz - Texture For I8 Studio")
        credit.pack(side="bottom", fill="x", pady=4)

        # v2: status bar + extra tabs
        self.build_v2_statusbar()
        self.build_v2_tabs()

    def on_mousewheel(self, event):
        if self.thumb_canvas.winfo_exists():
            self.thumb_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def on_thumb_frame_configure(self, _event=None):
        self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all"))

    def on_thumb_canvas_configure(self, event):
        self.thumb_canvas.itemconfigure(self.thumb_window, width=event.width)
        self.reflow_thumb_grid(event.width)

    def make_sidebar_section(self, parent, title, description):
        wrapper = tk.Frame(
            parent,
            bg=SIDEBAR_CARD,
            padx=12,
            pady=12,
            highlightbackground=SIDEBAR_BORDER,
            highlightthickness=1,
        )
        wrapper.pack(fill="x", pady=(0, 10))
        tk.Label(wrapper, text=title, bg=SIDEBAR_CARD, fg=SIDEBAR_FG, font=("Segoe UI Semibold", 11)).pack(anchor="w")
        if description:
            tk.Label(
                wrapper,
                text=description,
                bg=SIDEBAR_CARD,
                fg="#D7B0A9",
                font=("Segoe UI", 9),
                wraplength=300,
                justify="left",
            ).pack(anchor="w", pady=(2, 8))
        return wrapper

    def make_action_card(self, parent, row, column, title, description, command, state="normal", accent=False):
        card = tk.Frame(
            parent,
            bg="#341416" if accent else SIDEBAR_BG,
            padx=8,
            pady=8,
            highlightbackground=SIDEBAR_BORDER,
            highlightthickness=1,
        )
        card.grid(row=row, column=column, sticky="nsew", padx=4, pady=4)
        button = tk.Button(
            card,
            text=title,
            command=command,
            state=state,
            relief="flat",
            bd=0,
            bg=PRIMARY_HOVER if accent else PRIMARY,
            activebackground=PRIMARY,
            activeforeground="white",
            fg="white",
            font=("Segoe UI Semibold", 10),
            padx=8,
            pady=8,
            cursor="hand2",
            disabledforeground="#E8C8C3",
        )
        button.pack(fill="x")
        tk.Label(
            card,
            text=description,
            bg=card.cget("bg"),
            fg="#F1D7D1",
            font=("Segoe UI", 8),
            wraplength=135,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))
        return button

    def make_inline_action(self, parent, title, description, command):
        wrapper = tk.Frame(parent, bg="#341416", padx=10, pady=10, highlightbackground=SIDEBAR_BORDER, highlightthickness=1)
        button = tk.Button(
            wrapper,
            text=title,
            command=command,
            relief="flat",
            bd=0,
            bg=PRIMARY,
            activebackground=PRIMARY_HOVER,
            activeforeground="white",
            fg="white",
            font=("Segoe UI Semibold", 9),
            padx=10,
            pady=6,
            cursor="hand2",
        )
        button.pack(fill="x")
        tk.Label(
            wrapper,
            text=description,
            bg="#341416",
            fg="#DDB9B2",
            font=("Segoe UI", 8),
            wraplength=145,
            justify="left",
        ).pack(anchor="w", pady=(5, 0))
        return wrapper

    def load_logo(self, parent):
        header = tk.Frame(parent, bg=SIDEBAR_BG)
        header.pack(fill="x", pady=(0, 14))
        brand_row = tk.Frame(header, bg=SIDEBAR_BG)
        brand_row.pack(fill="x")
        text_col = tk.Frame(brand_row, bg=SIDEBAR_BG)

        def render_brand_text():
            tk.Label(
                text_col,
                text="Thư viện Texture gọn",
                bg=SIDEBAR_BG,
                fg=SIDEBAR_FG,
                font=("Segoe UI Semibold", 14),
                anchor="w",
                justify="left",
            ).pack(anchor="w")
            tk.Label(
                text_col,
                text="Made by DB9.Visual And Texture Collect By I8 Studio",
                bg=SIDEBAR_BG,
                fg="#E5484D",
                font=("Segoe UI Semibold", 9),
                wraplength=220,
                justify="left",
            ).pack(anchor="w", pady=(4, 0))
        logo_candidates = [
            os.path.join(app_dir(), "logo.png"),
            os.path.join(app_dir(), "logo.jpg"),
            os.path.join(app_dir(), "logo.ico"),
        ]
        for logo_path in logo_candidates:
            if not (PIL_AVAILABLE and os.path.exists(logo_path)):
                continue
            try:
                image = Image.open(logo_path).convert("RGBA")
                image = ImageOps.contain(image, (84, 84))
                self._logo_img = ImageTk.PhotoImage(image)
                tk.Label(brand_row, image=self._logo_img, bg=SIDEBAR_BG).pack(side="left", anchor="n")
                text_col.pack(side="left", fill="x", expand=True, padx=(10, 0))
                render_brand_text()
                return
                tk.Label(
                    header,
                    text="Thư viện Poliigon gọn, đúng preset, dễ rà soát variant.",
                    bg=SIDEBAR_BG,
                    fg="#D7B0A9",
                    font=("Segoe UI", 9),
                    wraplength=300,
                    justify="left",
                ).pack(anchor="w", pady=(6, 0))
                return
            except Exception:
                continue
        text_col.pack(side="left", fill="x", expand=True)
        render_brand_text()
        return
        tk.Label(
            header,
            text=APP_TITLE,
            bg=SIDEBAR_BG,
            fg=SIDEBAR_FG,
            font=("Segoe UI Semibold", 15),
            anchor="w",
            justify="left",
        ).pack(fill="x")
        tk.Label(
            header,
            text="Thư viện Poliigon gọn, đúng preset, dễ rà soát variant.",
            bg=SIDEBAR_BG,
            fg="#D7B0A9",
            font=("Segoe UI", 9),
            wraplength=300,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

    def debounced_search(self):
        if self._search_timer:
            self.root.after_cancel(self._search_timer)
        self._search_timer = self.root.after(300, self.refresh_search_results)

    def focus_search(self):
        if hasattr(self, "search_entry"):
            self.search_entry.focus_set()
            self.search_entry.select_range(0, tk.END)

    def select_all(self):
        self.selected_indices = set(range(len(self._search_cache)))
        self.update_tile_selection()

    def cancel_task(self):
        self._cancel_flag.set()
        self.log("[CANCEL] Stopping task...")
        self.set_status("Cancelling current task...")

    def show_help(self):
        window = tk.Toplevel(self.root)
        window.title("Huong dan su dung")
        window.geometry("560x500")
        text = scrolledtext.ScrolledText(window, wrap="word", font=("Segoe UI", 11))
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert(
            "1.0",
            """HUONG DAN SU DUNG DB9_TEXTUREMODELCOLLECTIONTOOL

1. Chon Library Root
   Thu muc dich chua thu vien texture da duoc sap xep.

2. Chon Source Folder
   Thu muc nguon chua cac file ZIP tai ve. App se quet de quy ben trong.

3. Run / Run Again
   Quet ZIP, detect preset, doi ten ZIP theo 2k/4k/8k, trich preview, add tag.

4. Reorganize library
   Sap xep lai thu vien hien co theo rule va preset detect.

5. Repair library
   Gop cac folder _2k/_4k/_8k bi tach sai, rename lai ZIP suffix, refresh preview,
   va canh bao texture bi thieu chain size.

6. Auto detect tags
   Tu dong bo sung tag dua tren ten texture, preset, resolution va file trong folder.

7. Search / Root / Sort by
   Tim theo ten, tag, preset. Search da co debounce de giam lag.

8. Drag & Drop
   Keo tile texture tha vao preset list ben trai de move + teach rule.

9. Shortcut
   Ctrl+S: Save
   Ctrl+F: Focus Search
   Ctrl+A: Select All visible tiles
""",
        )
        text.config(state="disabled")

    def log(self, message):
        self.logbox.insert(tk.END, message + "\n")
        self.logbox.see(tk.END)

    def set_status(self, message):
        self.status_text.set(message)

    def update_progress(self, current, total, message):
        percent = 0 if total <= 0 else int((current / total) * 100)
        self.progress_bar["value"] = percent
        self.progress_text.set(f"{percent}% - {message}")

    def reset_progress(self):
        self.progress_bar["value"] = 0
        self.progress_text.set("Ready")

    def set_busy(self, is_busy):
        state = "disabled" if is_busy else "normal"
        readonly = "disabled" if is_busy else "readonly"
        self.run_button.config(state=state)
        self.rerun_button.config(state=state)
        self.reorg_button.config(state=state)
        self.repair_button.config(state=state)
        self.autotag_button.config(state=state)
        self.save_button.config(state=state)
        self.teach_button.config(state=state)
        self.help_button.config(state=state)
        self.refresh_presets_button.config(state=state)
        self.delete_rule_button.config(state=state)
        self.lib_entry.config(state=state)
        self.src_entry.config(state=state)
        self.lib_browse.config(state=state)
        self.src_browse.config(state=state)
        self.search_root_combo.config(state=readonly)
        self.sort_combo.config(state=readonly)
        self.cancel_button.config(state="normal" if is_busy else "disabled")

    def process_ui_queue(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                event_type = item[0]
                if event_type == "log":
                    self.log(item[1])
                elif event_type == "progress":
                    _, current, total, message = item
                    self.update_progress(current, total, message)
                elif event_type == "task_done":
                    _, task_name, payload = item
                    self.finish_task(task_name, payload)
                elif event_type == "task_cancelled":
                    self.worker = None
                    self.set_busy(False)
                    self.set_status("Task cancelled")
                    self.progress_text.set("Cancelled")
                    self.log("[CANCELLED] Task stopped")
                elif event_type == "task_error":
                    _, message = item
                    self.worker = None
                    self.set_busy(False)
                    self.set_status("Error")
                    self.progress_text.set("Failed")
                    self.log(f"[ERROR] {message}")
                elif event_type == "poliigon_done":
                    self._apply_poliigon_result(item[1])
                elif event_type == "stats_done":
                    self._apply_stats_result(item[1])
        except queue.Empty:
            pass
        finally:
            if self.root.winfo_exists():
                self.root.after(100, self.process_ui_queue)

    def start_background_task(self, task_name, runner):
        if self.worker and self.worker.is_alive():
            self.set_status("A task is already running")
            return

        self._cancel_flag.clear()
        self.reset_progress()
        self.set_busy(True)
        self.set_status(f"Running {task_name}...")

        def log_callback(message):
            self.ui_queue.put(("log", message))

        def progress_callback(current, total, message):
            self.ui_queue.put(("progress", current, total, message))

        def target():
            try:
                result = runner(log_callback, progress_callback)
                self.ui_queue.put(("task_done", task_name, result))
            except TaskCancelled:
                self.ui_queue.put(("task_cancelled",))
            except Exception as exc:
                self.ui_queue.put(("task_error", str(exc)))

        self.worker = threading.Thread(target=target, daemon=True)
        self.worker.start()

    def finish_task(self, task_name, payload):
        self.worker = None
        self.set_busy(False)
        self.update_progress(100, 100, "Done")

        if task_name == "run":
            moved = payload["moved"]
            texture_folders = payload["texture_folders"]
            self.set_status(
                f"Completed: moved {moved} ZIP file(s) into {texture_folders} texture folder(s)"
            )
            self.log(f"[DONE] moved={moved} | texture_folders={texture_folders}")
        elif task_name == "reorganize":
            moved = payload["moved"]
            checked = payload["checked"]
            self.set_status(f"Completed: moved {moved} of {checked} texture folder(s)")
            self.log(f"[DONE] reorganized {moved} of {checked} texture folder(s)")
        elif task_name == "repair":
            moved = payload["moved"]
            renamed = payload["renamed"]
            warnings = payload["warnings"]
            checked = payload["checked"]
            self.set_status(
                f"Completed: repaired {checked} texture folder(s), merged {moved}, renamed {renamed}, warnings {warnings}"
            )
            self.log(
                f"[DONE] repaired={checked} | merged={moved} | renamed={renamed} | warnings={warnings}"
            )
            for item in payload.get("warning_details", []):
                found = ", ".join(res.upper() for res in item.get("found_resolutions", [])) or "-"
                missing = ", ".join(res.upper() for res in item.get("missing_lower", [])) or "-"
                self.log(f"[MISSING] {item['preset']}/{item['name']} | found {found} | missing {missing}")
        elif task_name == "auto_tag":
            updated = payload["updated"]
            checked = payload["checked"]
            self.set_status(f"Completed: updated tags for {updated} of {checked} texture folder(s)")
            self.log(f"[DONE] auto-tag updated {updated} of {checked} texture folder(s)")

        self.save_runtime_data()
        self.refresh_presets_from_library()
        self.rebuild_asset_cache()
        self.refresh_search_results()
        if task_name in {"run", "repair", "reorganize"}:
            self.log_missing_variant_summary()

    def choose_library_root(self):
        folder = filedialog.askdirectory()
        if folder:
            self.lib.set(folder)
            self.load_library_state(folder)
            save_json(CONFIG_FILE, self.cfg)
            self.set_status(f"Library root selected: {folder}")

    def choose_download_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.src.set(folder)
            inferred = infer_asset_meta_from_source(folder)
            if inferred:
                for key, value in inferred.items():
                    self.asset_meta.setdefault(key, value)
                if self.lib.get().strip() and os.path.isdir(self.lib.get().strip()):
                    self.save_portable_library_state()
                    self.rebuild_asset_cache()
                    self.refresh_search_results()
            self.refresh_source_group_list()
            self.set_status(f"Source folder selected: {folder}")

    def normalize_preset_config(self):
        custom = self.cfg.get("custom_presets", [])
        normalized_custom = []
        for preset in custom:
            canonical = canonical_preset_name(preset)
            if canonical and canonical not in DEFAULT_PRESETS and canonical not in normalized_custom:
                normalized_custom.append(canonical)
        self.cfg["custom_presets"] = normalized_custom

        for rule in self.rules:
            rule["t"] = canonical_preset_name(rule.get("t"))

    def portable_cfg_payload(self):
        return {
            "custom_presets": list(self.cfg.get("custom_presets", [])),
            "sort_by": self.sort_by.get() if hasattr(self, "sort_by") else self.cfg.get("sort_by", SORT_OPTIONS[0]),
        }

    def save_portable_library_state(self):
        library_root = self.lib.get().strip()
        if not library_root or not os.path.isdir(library_root):
            return
        paths = library_state_paths(library_root)
        os.makedirs(paths["dir"], exist_ok=True)
        save_json(paths["config"], self.portable_cfg_payload())
        save_json(paths["rules"], self.rules)
        save_json(paths["tags"], self.tags_db)
        save_json(paths["asset_meta"], self.asset_meta)

    def load_library_state(self, library_root):
        if not library_root or not os.path.isdir(library_root):
            return
        paths = library_state_paths(library_root)
        portable_cfg = load_json(paths["config"], None)
        portable_rules = load_json(paths["rules"], None)
        portable_tags = load_json(paths["tags"], None)
        portable_asset_meta = load_json(paths["asset_meta"], None)

        if portable_cfg is not None or portable_rules is not None or portable_tags is not None:
            if isinstance(portable_cfg, dict):
                self.cfg["custom_presets"] = portable_cfg.get("custom_presets", [])
                self.cfg["sort_by"] = portable_cfg.get("sort_by", self.cfg.get("sort_by", SORT_OPTIONS[0]))
            else:
                self.cfg["custom_presets"] = infer_custom_presets_from_library(library_root)
            self.rules = portable_rules if isinstance(portable_rules, list) else []
            self.tags_db = portable_tags if isinstance(portable_tags, dict) else {}
            self.asset_meta = portable_asset_meta if isinstance(portable_asset_meta, dict) else {}
            self.normalize_preset_config()
            if hasattr(self, "sort_by"):
                self.sort_by.set(self.cfg.get("sort_by", SORT_OPTIONS[0]))
            self.set_status(f"Loaded portable library state from {library_root}")
            self.log(f"[LOAD] portable library state loaded from {library_root}")
        else:
            self.cfg["custom_presets"] = infer_custom_presets_from_library(library_root)
            self.rules = []
            self.tags_db = {}
            self.asset_meta = {}
            self.normalize_preset_config()
            if hasattr(self, "sort_by"):
                self.sort_by.set(self.cfg.get("sort_by", SORT_OPTIONS[0]))
            self.set_status(f"Loaded library structure from {library_root}")
            self.log(f"[LOAD] inferred presets from library structure in {library_root}")

        self.cfg["library_root"] = library_root
        source_root = self.src.get().strip()
        if source_root and os.path.isdir(source_root):
            inferred = infer_asset_meta_from_source(source_root)
            for key, value in inferred.items():
                self.asset_meta.setdefault(key, value)
        self.refresh_presets_from_library()
        self.rebuild_asset_cache()
        self.refresh_search_results()

    def refresh_presets_from_library(self):
        presets = get_presets_from_config(self.cfg.get("custom_presets", []))
        self.cfg["dynamic_presets"] = presets
        level1_values = ["All"] + list_top_level_library_groups(self.lib.get().strip(), self.show_state_folders.get())
        self.search_root_combo["values"] = level1_values
        if hasattr(self, "collect_target_combo"):
            collect_values = [item for item in level1_values if item != "All"]
            self.collect_target_combo["values"] = collect_values
            if self.collect_target.get() not in collect_values:
                self.collect_target.set(collect_values[0] if collect_values else "")
        if self.search_root.get() not in level1_values:
            self.search_root.set("All")
        self.refresh_rule_list()
        self.refresh_source_group_list()

    def current_presets(self):
        return self.cfg.get("dynamic_presets") or get_presets_from_config(self.cfg.get("custom_presets", []))

    def current_source_groups(self):
        groups = set(list_top_level_library_groups(self.lib.get().strip(), self.show_state_folders.get()))
        groups = sorted(groups, key=str.lower)
        return ["All folders"] + groups

    def refresh_source_group_list(self):
        if not hasattr(self, "source_group_list"):
            return
        values = self.current_source_groups()
        current = self.source_group_filter.get() or "All folders"
        self.source_group_list.delete(0, tk.END)
        for item in values:
            self.source_group_list.insert(tk.END, item)
        if current not in values:
            current = "All folders"
            self.source_group_filter.set(current)
        try:
            index = values.index(current)
        except ValueError:
            index = 0
        self.source_group_list.selection_clear(0, tk.END)
        self.source_group_list.selection_set(index)
        self.source_group_list.activate(index)

    def on_source_group_selected(self, _event=None):
        if not hasattr(self, "source_group_list"):
            return
        selection = self.source_group_list.curselection()
        if not selection:
            return
        value = self.source_group_list.get(selection[0])
        self.source_group_filter.set(value)
        self.search_root.set("All" if value == "All folders" else value)
        self.refresh_search_results()

    def on_level1_combo_changed(self, _event=None):
        value = self.search_root.get()
        self.source_group_filter.set("All folders" if value == "All" else value)
        self.refresh_source_group_list()
        self.refresh_search_results()

    def on_state_folder_toggle(self):
        self.refresh_presets_from_library()
        self.refresh_search_results()

    def rebuild_asset_cache(self):
        self._asset_cache = []
        self._missing_variant_issues = []
        self._missing_variant_report_path = ""
        library_root = self.lib.get()
        if not library_root or not os.path.isdir(library_root):
            return
        for preset in sorted(os.listdir(library_root), key=str.lower):
            if preset == PORTABLE_STATE_DIR:
                continue
            preset_path = os.path.join(library_root, preset)
            if not os.path.isdir(preset_path):
                continue
            for name in os.listdir(preset_path):
                folder_path = os.path.join(preset_path, name)
                if os.path.isdir(folder_path):
                    asset = build_asset_record(library_root, folder_path, name, self.tags_db, self.asset_meta)
                    self._asset_cache.append(asset)
                    if asset.get("missing_lower"):
                        self._missing_variant_issues.append(
                            {
                                "preset": asset["preset"],
                                "name": asset["name"],
                                "path": asset["path"],
                                "found_resolutions": list(asset.get("resolutions", [])),
                                "missing_lower": list(asset.get("missing_lower", [])),
                            }
                        )
        self._missing_variant_report_path = save_variant_warning_report(library_root, self._missing_variant_issues) or ""
        self.refresh_source_group_list()

    def log_missing_variant_summary(self, issues=None):
        issues = self._missing_variant_issues if issues is None else issues
        if not issues:
            self.log("[CHECK] No missing lower-size variants found")
            return
        self.log(f"[CHECK] Missing lower-size variants: {len(issues)}")
        for item in issues:
            found = ", ".join(res.upper() for res in item.get("found_resolutions", [])) or "-"
            missing = ", ".join(res.upper() for res in item.get("missing_lower", [])) or "-"
            self.log(f"[MISSING] {item['preset']}/{item['name']} | found {found} | missing {missing}")
        if self._missing_variant_report_path:
            self.log(f"[REPORT] {self._missing_variant_report_path}")

    def save_runtime_data(self):
        with self._data_lock:
            save_json(LEARNING_FILE, self.rules)
            save_json(TAGS_FILE, self.tags_db)
            self.save_portable_library_state()

    def save_state(self):
        self.normalize_preset_config()
        self.cfg["library_root"] = self.lib.get()
        self.cfg["watch_folder"] = self.src.get()
        self.cfg["sort_by"] = self.sort_by.get()
        save_json(CONFIG_FILE, self.cfg)
        self.save_runtime_data()
        self.save_portable_library_state()
        self.set_status("Saved config, rules, tags, and sort mode")
        self.log("[SAVE] Config, rules, tags, and sort mode saved")

    def validate_library_root(self):
        if not self.lib.get() or not os.path.isdir(self.lib.get()):
            self.set_status("Library Root is invalid")
            self.log("[ERROR] Library Root is invalid")
            return False
        return True

    def validate_run_inputs(self):
        if not self.validate_library_root():
            return False
        if not self.src.get() or not os.path.isdir(self.src.get()):
            self.set_status("Source Folder is invalid")
            self.log("[ERROR] Source Folder is invalid")
            return False
        return True

    def run(self):
        if not self.validate_run_inputs():
            return

        def runner(log, progress):
            with self._data_lock:
                return process_download_folder(
                    self.src.get(),
                    self.lib.get(),
                    self.current_presets(),
                    self.rules,
                    self.tags_db,
                    self.asset_meta,
                    log,
                    progress,
                    should_cancel=self._cancel_flag.is_set,
                )

        self.log(f"[START] scanning recursively inside {self.src.get()}")
        self.start_background_task("run", runner)

    def run_again(self):
        if not self.validate_run_inputs():
            return
        self.log(f"[RERUN] rescanning current source root: {self.src.get()}")
        self.run()

    def reorganize_library(self):
        if not self.validate_library_root():
            return

        def runner(log, progress):
            with self._data_lock:
                return reorganize_existing_library(
                    self.lib.get(),
                    self.current_presets(),
                    self.rules,
                    self.tags_db,
                    log,
                    progress,
                    should_cancel=self._cancel_flag.is_set,
                )

        self.log(f"[START] reorganizing {self.lib.get()}")
        self.start_background_task("reorganize", runner)

    def repair_library(self):
        if not self.validate_library_root():
            return

        def runner(log, progress):
            with self._data_lock:
                return repair_library_variants(
                    self.lib.get(),
                    self.current_presets(),
                    self.rules,
                    self.tags_db,
                    log,
                    progress,
                    should_cancel=self._cancel_flag.is_set,
                )

        self.log(f"[START] repairing library variants in {self.lib.get()}")
        self.start_background_task("repair", runner)

    def auto_detect_tags(self):
        if not self.validate_library_root():
            return

        def runner(log, progress):
            with self._data_lock:
                return auto_tag_library_assets(
                    self.lib.get(),
                    self.tags_db,
                    log,
                    progress,
                    should_cancel=self._cancel_flag.is_set,
                )

        self.log(f"[START] auto detect tags in {self.lib.get()}")
        self.start_background_task("auto_tag", runner)

    def learn_ui(self):
        presets = self.current_presets()
        if not presets:
            self.set_status("No presets available")
            return

        window = tk.Toplevel(self.root)
        window.title("Teach AI")
        pattern_var = tk.StringVar()
        target_var = tk.StringVar(value=presets[0])
        ttk.Label(window, text="Pattern").pack()
        ttk.Entry(window, textvariable=pattern_var).pack(fill="x")
        ttk.Label(window, text="Target Folder").pack()
        ttk.Combobox(window, textvariable=target_var, state="readonly", values=presets).pack(
            fill="x"
        )

        def add_rule():
            pattern = normalize(pattern_var.get())
            if not pattern:
                return
            with self._data_lock:
                self.rules.append({"p": pattern, "t": target_var.get(), "w": 1})
            self.save_runtime_data()
            self.refresh_rule_list()
            self.set_status(f"Added rule: {pattern} -> {target_var.get()}")
            window.destroy()

        ttk.Button(window, text="Add", command=add_rule).pack(pady=8)

    def add_custom_preset(self):
        preset = simpledialog.askstring("Add preset", "Enter your custom preset name:")
        preset = canonical_preset_name(preset)
        if not preset:
            return
        if preset in DEFAULT_PRESETS:
            self.set_status(f"'{preset}' is already a built-in preset")
            return
        custom = self.cfg.get("custom_presets", [])
        if preset in custom:
            self.set_status(f"Preset '{preset}' already exists")
            return
        custom.append(preset)
        self.cfg["custom_presets"] = sorted(custom, key=str.lower)
        self.refresh_presets_from_library()
        save_json(CONFIG_FILE, self.cfg)
        self.save_portable_library_state()
        self.set_status(f"Added custom preset: {preset}")
        self.log(f"[PRESET] added {preset}")

    def delete_custom_preset(self):
        selection = self.rule_list.curselection()
        if not selection:
            return
        line = self.rule_list.get(selection[0])
        if not line.startswith("PRESET | "):
            self.set_status("Select a PRESET row to delete a custom preset")
            return
        preset = canonical_preset_name(line.replace("PRESET | ", "").strip())
        if preset in DEFAULT_PRESETS:
            self.set_status(f"Cannot delete built-in preset: {preset}")
            return
        custom = self.cfg.get("custom_presets", [])
        if preset not in custom:
            self.set_status(f"Preset '{preset}' is not a custom preset")
            return
        if not messagebox.askyesno("Confirm", f"Delete custom preset '{preset}'?"):
            return
        self.cfg["custom_presets"] = [item for item in custom if item != preset]
        with self._data_lock:
            for rule in self.rules:
                if canonical_preset_name(rule.get("t")) == preset:
                    rule["t"] = "Unsorted"
        self.refresh_presets_from_library()
        save_json(CONFIG_FILE, self.cfg)
        self.save_runtime_data()
        self.set_status(f"Deleted custom preset: {preset}")
        self.log(f"[PRESET] deleted {preset}")

    def refresh_rule_list(self):
        if not hasattr(self, "rule_list"):
            return
        self.rule_list.delete(0, tk.END)
        for rule in sorted(self.rules, key=lambda item: (-item.get("w", 1), item.get("p", ""))):
            self.rule_list.insert(tk.END, f"RULE | {rule['p']} -> {rule['t']} (w={rule.get('w', 1)})")
        self.rule_list.insert(tk.END, "--- PRESET TARGETS ---")
        for preset in self.current_presets():
            self.rule_list.insert(tk.END, f"PRESET | {preset}")

    def delete_selected_rule(self):
        selection = self.rule_list.curselection()
        if not selection:
            return
        line = self.rule_list.get(selection[0])
        if not line.startswith("RULE | "):
            return
        pattern = line.replace("RULE | ", "").split(" -> ")[0].strip()
        if not messagebox.askyesno("Confirm", f"Delete rule for pattern '{pattern}'?"):
            return
        with self._data_lock:
            self.rules = [rule for rule in self.rules if rule.get("p") != pattern]
        self.save_runtime_data()
        self.refresh_rule_list()
        self.set_status(f"Deleted rule: {pattern}")

    def on_sort_changed(self):
        self.cfg["sort_by"] = self.sort_by.get()
        save_json(CONFIG_FILE, self.cfg)
        self.save_portable_library_state()
        self.refresh_search_results()

    def refresh_search_results(self):
        level1_values = ["All"] + list_top_level_library_groups(self.lib.get().strip(), self.show_state_folders.get())
        self.search_root_combo["values"] = level1_values
        if self.search_root.get() not in level1_values:
            self.search_root.set("All")

        if not self._asset_cache:
            self.rebuild_asset_cache()

        query_norm = normalize(self.search_query.get())
        search_root = self.search_root.get()
        results = []
        for asset in self._asset_cache:
            if search_root and search_root != "All" and asset["preset"] != search_root:
                continue
            haystack = " ".join(
                [
                    normalize(asset["name"]),
                    normalize(asset["rel"]),
                    normalize(asset["preset"]),
                    " ".join(asset["tags"]),
                ]
            )
            if not query_norm or query_norm in haystack:
                results.append(dict(asset))

        self._search_cache = sort_assets(results, self.sort_by.get())

        for asset in self._search_cache:
            merged = merge_tags(self.tags_db.get(asset["name"], []), asset["tags"])
            self.tags_db[asset["name"]] = merged
            asset["tags"] = merged

        info = f"{len(self._search_cache)} texture folder(s)"
        if self._missing_variant_issues:
            info += f" | {len(self._missing_variant_issues)} missing lower-size warning(s)"
        if search_root and search_root != "All":
            info += f" | thư viện cấp 1: {search_root}"
        self.result_info.set(info)
        self.render_thumb_grid()

    def render_thumb_grid(self):
        for child in self.thumb_frame.winfo_children():
            child.destroy()
        self.thumb_tiles = []

        for index, asset in enumerate(self._search_cache):
            tile = ThumbTile(self.thumb_frame, self, asset, index)
            self.thumb_tiles.append(tile)

        self.reflow_thumb_grid(self.thumb_canvas.winfo_width())
        self.update_tile_selection()

    def reflow_thumb_grid(self, width):
        if not self.thumb_tiles:
            return

        usable_width = max(width - 24, TILE_WIDTH)
        cols = max(1, usable_width // TILE_WIDTH)

        for col in range(cols):
            self.thumb_frame.columnconfigure(col, weight=1, minsize=TILE_WIDTH)

        for index, tile in enumerate(self.thumb_tiles):
            row = index // cols
            col = index % cols
            tile.grid(row=row, column=col, padx=8, pady=8, sticky="n")

    def select_thumb(self, index, additive=False):
        if not additive:
            self.selected_indices.clear()
        if index in self.selected_indices and additive:
            self.selected_indices.remove(index)
        else:
            self.selected_indices.add(index)
        self.update_tile_selection()

    def update_tile_selection(self):
        for index, tile in enumerate(self.thumb_tiles):
            tile.set_selected(index in self.selected_indices)

    def clear_selection(self):
        self.selected_indices.clear()
        self.update_tile_selection()

    def selected_assets(self):
        return [
            self._search_cache[index]
            for index in sorted(self.selected_indices)
            if 0 <= index < len(self._search_cache)
        ]

    def open_asset_folder_by_index(self, index):
        if 0 <= index < len(self._search_cache):
            open_folder(self._search_cache[index]["path"])

    def open_asset_preview_by_index(self, index):
        if 0 <= index < len(self._search_cache):
            self.show_asset_preview(self._search_cache[index])

    def show_asset_preview(self, asset):
        preview_path = asset.get("preview")
        if not (PIL_AVAILABLE and preview_path and os.path.exists(preview_path)):
            self.set_status(f"No preview available for {asset['name']}")
            return
        if self._asset_preview_window is None or not self._asset_preview_window.winfo_exists():
            window = tk.Toplevel(self.root)
            window.title(f"Preview - {asset['name']}")
            window.geometry("1180x900")
            window.configure(bg="#120608")
            toolbar = tk.Frame(window, bg="#120608")
            toolbar.pack(fill="x", padx=10, pady=10)
            self._asset_preview_title = tk.Label(
                toolbar,
                text=asset["name"],
                bg="#120608",
                fg="#FBEDEA",
                font=("Segoe UI Semibold", 12),
            )
            self._asset_preview_title.pack(side="left")
            tk.Button(toolbar, text="-", width=3, command=lambda: self.adjust_asset_preview_zoom(0.9)).pack(side="right")
            tk.Button(toolbar, text="+", width=3, command=lambda: self.adjust_asset_preview_zoom(1.1)).pack(side="right", padx=(0, 6))
            tk.Button(toolbar, text="100%", command=lambda: self.set_asset_preview_zoom(1.0)).pack(side="right", padx=(0, 6))
            tk.Button(toolbar, text="Fit", command=self.fit_asset_preview_to_window).pack(side="right", padx=(0, 6))
            body = tk.Frame(window, bg="#120608")
            body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            self._asset_preview_canvas = tk.Canvas(body, bg="#120608", highlightthickness=0)
            self._asset_preview_canvas.pack(fill="both", expand=True)
            self._asset_preview_canvas.bind("<Configure>", lambda _event: self.render_asset_preview())
            self._asset_preview_canvas.bind("<ButtonPress-1>", self.on_asset_preview_pan_start)
            self._asset_preview_canvas.bind("<B1-Motion>", self.on_asset_preview_pan_move)
            self._asset_preview_window = window
            window.bind("<MouseWheel>", self.on_asset_preview_mousewheel)
            window.bind("<Escape>", lambda _event: window.destroy())
        self._asset_preview_source = preview_path
        self._asset_preview_photo = None
        self._asset_preview_image_id = None
        if self._asset_preview_title is not None:
            self._asset_preview_title.config(text=asset["name"])
        if self._asset_preview_window is not None and self._asset_preview_window.winfo_exists():
            self._asset_preview_window.title(f"Preview - {asset['name']}")
            self._asset_preview_window.deiconify()
            self._asset_preview_window.lift()
            self._asset_preview_window.focus_force()
        self.load_asset_preview_source()
        self.fit_asset_preview_to_window()

    def render_asset_preview(self):
        if not (
            PIL_AVAILABLE
            and self._asset_preview_canvas is not None
            and self._asset_preview_base_image is not None
            and self._asset_preview_source
            and os.path.exists(self._asset_preview_source)
        ):
            return
        try:
            width, height = self._asset_preview_base_image.size
            zoom = max(0.1, min(self._asset_preview_zoom, 8.0))
            key = (self._asset_preview_source, round(zoom, 3))
            photo = self._asset_preview_cache.get(key)
            if photo is None:
                resized = self._asset_preview_base_image.resize(
                    (max(1, int(width * zoom)), max(1, int(height * zoom))),
                    Image.Resampling.LANCZOS,
                )
                photo = ImageTk.PhotoImage(resized)
                self._asset_preview_cache[key] = photo
            self._asset_preview_photo = photo
            canvas = self._asset_preview_canvas
            canvas.delete("all")
            image_width = photo.width()
            image_height = photo.height()
            canvas_width = max(canvas.winfo_width(), 1)
            canvas_height = max(canvas.winfo_height(), 1)
            pos_x = max((canvas_width - image_width) // 2, 0)
            pos_y = max((canvas_height - image_height) // 2, 0)
            self._asset_preview_image_id = canvas.create_image(pos_x, pos_y, anchor="nw", image=photo)
            canvas.configure(scrollregion=(0, 0, max(image_width, canvas_width), max(image_height, canvas_height)))
        except Exception:
            if self._asset_preview_canvas is not None:
                self._asset_preview_canvas.delete("all")
                self._asset_preview_canvas.create_text(40, 40, anchor="nw", text="Preview load failed", fill="#FBEDEA")

    def load_asset_preview_source(self):
        if not (PIL_AVAILABLE and self._asset_preview_source and os.path.exists(self._asset_preview_source)):
            self._asset_preview_base_image = None
            return
        try:
            with Image.open(self._asset_preview_source) as image:
                self._asset_preview_base_image = image.convert("RGB")
        except Exception:
            self._asset_preview_base_image = None

    def set_asset_preview_zoom(self, zoom_value):
        self._asset_preview_zoom = zoom_value
        self.render_asset_preview()

    def adjust_asset_preview_zoom(self, factor):
        self._asset_preview_zoom = max(0.1, min(self._asset_preview_zoom * factor, 8.0))
        self.render_asset_preview()

    def on_asset_preview_mousewheel(self, event):
        self.adjust_asset_preview_zoom(1.1 if event.delta > 0 else 0.9)

    def fit_asset_preview_to_window(self):
        if not (self._asset_preview_canvas is not None and self._asset_preview_base_image is not None):
            return
        canvas_width = max(self._asset_preview_canvas.winfo_width(), 1)
        canvas_height = max(self._asset_preview_canvas.winfo_height(), 1)
        width, height = self._asset_preview_base_image.size
        if width <= 0 or height <= 0:
            return
        self._asset_preview_zoom = min(canvas_width / width, canvas_height / height, 1.0)
        self.render_asset_preview()

    def on_asset_preview_pan_start(self, event):
        if self._asset_preview_canvas is not None:
            self._asset_preview_canvas.scan_mark(event.x, event.y)

    def on_asset_preview_pan_move(self, event):
        if self._asset_preview_canvas is not None:
            self._asset_preview_canvas.scan_dragto(event.x, event.y, gain=1)

    def start_drag_from_index(self, index):
        assets = self.selected_assets()
        if not assets or index not in self.selected_indices:
            self.selected_indices = {index}
            assets = [self._search_cache[index]]
            self.update_tile_selection()
        self.drag_assets = assets
        names = ", ".join(asset["name"] for asset in assets[:3])
        extra = "" if len(assets) <= 3 else f" +{len(assets) - 3}"
        self.drag_status.set(f"Dragging: {names}{extra}")

    def update_drag_motion(self):
        if self.drag_assets:
            self.drag_status.set(f"Dragging {len(self.drag_assets)} texture folder(s) -> drop on preset list")

    def finish_drag_release(self, event):
        if not self.drag_assets:
            return
        target_widget = self.root.winfo_containing(event.x_root, event.y_root)
        if target_widget == self.rule_list:
            y_pos = target_widget.winfo_pointery() - target_widget.winfo_rooty()
            index = self.rule_list.nearest(y_pos)
            self.apply_drag_to_rule_index(index, move_now=True)
        else:
            self.drag_status.set("Drag canceled")
            self.drag_assets = []

    def on_rule_drop(self, event):
        if self.drag_assets:
            index = self.rule_list.nearest(event.y)
            self.apply_drag_to_rule_index(index, move_now=True)

    def apply_drag_to_rule_index(self, index, move_now=False):
        if not self.drag_assets or index < 0:
            return
        line = self.rule_list.get(index)
        if not line.startswith("PRESET | "):
            self.drag_status.set("Drop onto a PRESET row to teach the app")
            self.drag_assets = []
            return
        target = line.replace("PRESET | ", "").strip()

        for asset in self.drag_assets:
            pattern = normalize(asset["name"])
            matched = False
            with self._data_lock:
                for rule in self.rules:
                    if rule.get("p") == pattern and rule.get("t") == target:
                        rule["w"] = rule.get("w", 1) + 1
                        matched = True
                        break
                if not matched:
                    self.rules.append({"p": pattern, "t": target, "w": 1})

                merged_tags = merge_tags(
                    self.tags_db.get(asset["name"], []),
                    auto_tags_for_asset(asset["name"], target, [asset["rel"]] + asset["resolutions"]),
                )
                self.tags_db[asset["name"]] = merged_tags
            self.log(f"[LEARN] {pattern} -> {target}")

            if move_now:
                try:
                    move_asset_to_preset(asset, target, self.lib.get())
                    self.log(f"[MOVE] {asset['name']} -> {target}")
                except Exception as exc:
                    self.log(f"[ERROR] {exc}")
                    self.set_status("One or more assets could not be moved")

        self.save_runtime_data()
        self.refresh_rule_list()
        self.drag_status.set(f"Moved {len(self.drag_assets)} texture folder(s) -> {target}")
        self.drag_assets = []
        self.rebuild_asset_cache()
        self.refresh_search_results()
        self.clear_selection()

    def bulk_move_selected(self):
        assets = self.selected_assets()
        if not assets:
            self.set_status("No selected assets")
            return
        target = self.collect_target.get().strip()
        level1_values = [item for item in list_top_level_library_groups(self.lib.get().strip(), self.show_state_folders.get()) if item != PORTABLE_STATE_DIR]
        if not target or target not in level1_values:
            self.set_status("Choose a valid first-level library target")
            return
        if not messagebox.askyesno("Confirm", f"Collect {len(assets)} texture(s) into {target}?"):
            return
        self.drag_assets = assets
        moved = 0
        for asset in assets:
            try:
                move_asset_to_preset(asset, target, self.lib.get())
                moved += 1
                self.log(f"[COLLECT] {asset['name']} -> {target}")
            except Exception as exc:
                self.log(f"[ERROR] {asset['name']} -> {target} | {exc}")
        self.save_runtime_data()
        self.rebuild_asset_cache()
        self.refresh_search_results()
        self.clear_selection()
        self.set_status(f"Collected {moved} texture folder(s) into {target}")

    def bulk_tag_selected(self):
        assets = self.selected_assets()
        if not assets:
            self.set_status("No selected assets")
            return
        tag = normalize(simpledialog.askstring("Tag selected", "Enter tag:") or "")
        if not tag:
            return
        for asset in assets:
            name = asset["name"]
            with self._data_lock:
                self.tags_db[name] = merge_tags(self.tags_db.get(name, []), [tag])
            self.log(f"[TAG] {name} + {tag}")
        self.save_runtime_data()
        self.refresh_search_results()
        self.set_status(f"Applied tag '{tag}' to {len(assets)} texture folder(s)")

    def auto_tag_selected(self):
        assets = self.selected_assets()
        if not assets:
            self.set_status("No selected assets")
            return
        for asset in assets:
            detected = auto_tags_for_asset(asset["name"], asset["preset"], [asset["rel"]] + asset["resolutions"])
            with self._data_lock:
                self.tags_db[asset["name"]] = merge_tags(self.tags_db.get(asset["name"], []), detected)
            self.log(f"[AUTO TAG] {asset['name']} -> {', '.join(self.tags_db[asset['name']]) or '-'}")
        self.save_runtime_data()
        self.refresh_search_results()
        self.set_status(f"Auto tagged {len(assets)} selected texture folder(s)")

    def get_primary_selected_asset(self):
        assets = self.selected_assets()
        return assets[0] if assets else None

    def add_tag_to_selected_asset(self):
        assets = self.selected_assets()
        if not assets:
            self.set_status("No selected assets")
            return
        tag = normalize(self.tag_entry.get())
        if not tag:
            return
        for asset in assets:
            name = asset["name"]
            with self._data_lock:
                self.tags_db[name] = merge_tags(self.tags_db.get(name, []), [tag])
            self.log(f"[TAG] {name} + {tag}")
        self.save_runtime_data()
        self.refresh_search_results()
        self.tag_entry.set("")
        self.set_status(f"Applied tag '{tag}' to {len(assets)} texture folder(s)")

    def show_asset_context_menu(self, event):
        self.asset_menu.tk_popup(event.x_root, event.y_root)

    def context_open_folder(self):
        asset = self.get_primary_selected_asset()
        if asset:
            open_folder(asset["path"])

    def context_copy_path(self):
        assets = self.selected_assets()
        if not assets:
            return
        data = "\n".join(asset["path"] for asset in assets)
        self.root.clipboard_clear()
        self.root.clipboard_append(data)
        self.log(f"[COPY] {len(assets)} path(s)")
        self.set_status(f"Copied {len(assets)} path(s)")

    def context_remove_tag(self):
        assets = self.selected_assets()
        if not assets:
            return
        all_tags = sorted({tag for asset in assets for tag in self.tags_db.get(asset["name"], [])})
        if not all_tags:
            self.set_status("Selected assets do not have tags")
            return
        tag = simpledialog.askstring("Remove tag", f"Current tags: {', '.join(all_tags)}\nEnter tag to remove:")
        if not tag:
            return
        tag = normalize(tag)
        for asset in assets:
            with self._data_lock:
                current_tags = self.tags_db.get(asset["name"], [])
                self.tags_db[asset["name"]] = [item for item in current_tags if item != tag]
            self.log(f"[UNTAG] {asset['name']} - {tag}")
        self.save_runtime_data()
        self.refresh_search_results()
        self.set_status(f"Removed tag '{tag}'")

    def context_reassign_preset(self):
        assets = self.selected_assets()
        if not assets:
            return
        presets = self.current_presets()
        window = tk.Toplevel(self.root)
        window.title("Reassign preset")
        choice = tk.StringVar(value=presets[0])
        ttk.Label(window, text=f"Reassign {len(assets)} texture folder(s)").pack(padx=12, pady=(12, 6))
        ttk.Combobox(window, textvariable=choice, state="readonly", values=presets).pack(fill="x", padx=12, pady=6)

        def apply():
            target = choice.get()
            self.drag_assets = assets
            try:
                index = list(self.rule_list.get(0, tk.END)).index(f"PRESET | {target}")
                self.apply_drag_to_rule_index(index, move_now=True)
                window.destroy()
            except ValueError:
                self.set_status("Preset not found in rule list")

        ttk.Button(window, text="Apply", command=apply).pack(pady=12)



    # ================================================================== #
    # v2 — menubar                                                        #
    # ================================================================== #
    def build_menubar(self):
        menubar = tk.Menu(self.root)
        filem = tk.Menu(menubar, tearoff=0)
        filem.add_command(label="Save config", accelerator="Ctrl+S", command=self.save_state)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=filem)

        tools = tk.Menu(menubar, tearoff=0)
        tools.add_command(label="Reorganize library", command=self.reorganize_library)
        tools.add_command(label="Repair library", command=self.repair_library)
        tools.add_command(label="Auto-tag library", command=self.auto_detect_tags)
        tools.add_separator()
        tools.add_command(label="Check Poliigon now", command=self.poliigon_check_async)
        tools.add_command(label="Refresh statistics", command=self.refresh_stats)
        tools.add_separator()
        tools.add_command(label="Export Blender addon…", command=self.export_blender_addon)
        tools.add_command(label="Export 3ds Max macroscript…", command=self.export_max_macroscript)
        menubar.add_cascade(label="Tools", menu=tools)

        helpm = tk.Menu(menubar, tearoff=0)
        helpm.add_command(label="How to use (VN)", command=self.show_help)
        helpm.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=helpm)

        self.root.config(menu=menubar)

    def _show_about(self):
        messagebox.showinfo(
            "About",
            f"{APP_TITLE}\n\nApp made by BBBviz — Material by I8Studio\n"
            "Features: auto-organize, tags, preset rules, Poliigon weekly checker, "
            "statistics, 3D preview, Blender & 3ds Max export.",
        )

    # ================================================================== #
    # v2 — status bar                                                     #
    # ================================================================== #
    def build_v2_statusbar(self):
        bar = tk.Frame(self.root, bg=SIDEBAR_BG, height=22)
        bar.pack(side="bottom", fill="x")
        self.v2_statusbar_text = tk.StringVar(value="Ready")
        tk.Label(
            bar,
            textvariable=self.v2_statusbar_text,
            bg=SIDEBAR_BG,
            fg="#E9CFC9",
            font=("Segoe UI", 9),
            anchor="w",
            padx=10,
        ).pack(side="left", fill="x", expand=True)

    def set_v2_status(self, text):
        try:
            self.v2_statusbar_text.set(text)
        except Exception:
            pass

    # ================================================================== #
    # v2 — extra tabs                                                     #
    # ================================================================== #
    def build_v2_tabs(self):
        self._build_updates_tab()
        self._build_stats_tab()
        self._build_preview_tab()

    def _build_updates_tab(self):
        tab = tk.Frame(self.notebook, bg=CONTENT_BG)
        self.notebook.add(tab, text="Poliigon Updates")

        header = tk.Frame(tab, bg=CONTENT_PANEL, padx=14, pady=12)
        header.pack(fill="x")
        tk.Label(
            header, text="Poliigon Weekly Checker", bg=CONTENT_PANEL, fg=CONTENT_TEXT,
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w")
        self.updates_status = tk.StringVar(value=self._updates_status_text())
        tk.Label(
            header, textvariable=self.updates_status, bg=CONTENT_PANEL, fg="#DDB9B2",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 8))

        btns = tk.Frame(header, bg=CONTENT_PANEL)
        btns.pack(anchor="w")
        ttk.Button(btns, text="Check Now", command=self.poliigon_check_async).pack(side="left")
        ttk.Button(btns, text="Open poliigon.com/free", command=lambda: self._open_url("https://www.poliigon.com/textures/free")).pack(side="left", padx=6)

        body = tk.Frame(tab, bg=CONTENT_BG, padx=14, pady=10)
        body.pack(fill="both", expand=True)
        cols = ("kind", "name", "category", "discovered")
        self.updates_tree = ttk.Treeview(body, columns=cols, show="headings")
        for c, w in zip(cols, (90, 300, 200, 160)):
            self.updates_tree.heading(c, text=c.title())
            self.updates_tree.column(c, width=w, anchor="w")
        self.updates_tree.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(body, orient="vertical", command=self.updates_tree.yview)
        sb.pack(side="right", fill="y")
        self.updates_tree.configure(yscrollcommand=sb.set)
        self.updates_tree.bind("<Double-1>", self._updates_open_selected)

    def _updates_status_text(self):
        try:
            d = self.poliigon_checker.days_since_last_check()
            if d is None:
                return "No checks yet — click 'Check Now' to scan free textures & models."
            return f"Last check: {d:.1f} days ago. Auto-check weekly."
        except Exception:
            return "Poliigon checker idle."

    def _open_url(self, url):
        try:
            import webbrowser
            webbrowser.open(url, new=2)
        except Exception:
            pass

    def _updates_open_selected(self, _event=None):
        sel = self.updates_tree.selection()
        if not sel:
            return
        item = self.updates_tree.item(sel[0])
        vals = item.get("values") or []
        url = item.get("tags", [None])[0] if item.get("tags") else None
        if not url:
            return
        self._open_url(url)

    def poliigon_check_async(self):
        if getattr(self, "_poliigon_running", False):
            return
        self._poliigon_running = True
        self.set_v2_status("Poliigon: checking…")

        def worker():
            logs = []
            try:
                items = self.poliigon_checker.check(on_log=lambda m: logs.append(m))
            except Exception as exc:
                items = []
                logs.append(f"[POLIIGON][ERROR] {exc}")
            self.ui_queue.put(("poliigon_done", {"items": items, "logs": logs}))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_poliigon_result(self, payload):
        self._poliigon_running = False
        items = payload.get("items", [])
        for line in payload.get("logs", []):
            self.log(line)
        self.poliigon_new_items = items
        # refresh tree: show accumulated seen list plus new
        try:
            self.updates_tree.delete(*self.updates_tree.get_children())
        except Exception:
            return
        for it in items:
            self.updates_tree.insert(
                "", "end",
                values=(it.get("kind", ""), it.get("name", ""), it.get("category", ""), it.get("discovered", "")),
                tags=(it.get("url", ""),),
            )
        self.updates_status.set(self._updates_status_text())
        self.set_v2_status(f"Poliigon: {len(items)} new item(s)")

    # ================================================================== #
    # v2 — statistics tab                                                 #
    # ================================================================== #
    def _build_stats_tab(self):
        tab = tk.Frame(self.notebook, bg=CONTENT_BG)
        self.notebook.add(tab, text="Statistics")

        header = tk.Frame(tab, bg=CONTENT_PANEL, padx=14, pady=12)
        header.pack(fill="x")
        tk.Label(
            header, text="Library Statistics", bg=CONTENT_PANEL, fg=CONTENT_TEXT,
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w")
        self.stats_summary = tk.StringVar(value="Click 'Refresh' to scan the library.")
        tk.Label(
            header, textvariable=self.stats_summary, bg=CONTENT_PANEL,
            fg="#DDB9B2", font=("Segoe UI", 10), justify="left", anchor="w",
        ).pack(anchor="w", pady=(4, 8))
        ttk.Button(header, text="Refresh", command=self.refresh_stats).pack(anchor="w")

        body = tk.Frame(tab, bg=CONTENT_BG, padx=14, pady=10)
        body.pack(fill="both", expand=True)

        left = tk.LabelFrame(body, text="Preset breakdown", bg=CONTENT_BG, fg=CONTENT_TEXT)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.stats_preset_tree = ttk.Treeview(left, columns=("preset", "count"), show="headings")
        self.stats_preset_tree.heading("preset", text="Preset")
        self.stats_preset_tree.heading("count", text="Assets")
        self.stats_preset_tree.column("preset", width=220)
        self.stats_preset_tree.column("count", width=80, anchor="e")
        self.stats_preset_tree.pack(fill="both", expand=True)

        right = tk.LabelFrame(body, text="Resolutions", bg=CONTENT_BG, fg=CONTENT_TEXT)
        right.pack(side="right", fill="both", expand=True, padx=(8, 0))
        self.stats_res_tree = ttk.Treeview(right, columns=("res", "count"), show="headings")
        self.stats_res_tree.heading("res", text="Resolution")
        self.stats_res_tree.heading("count", text="Files")
        self.stats_res_tree.column("res", width=120)
        self.stats_res_tree.column("count", width=80, anchor="e")
        self.stats_res_tree.pack(fill="both", expand=True)

    def refresh_stats(self):
        lib = self.cfg.get("library_root", "") or self.lib.get()
        if not lib or not os.path.isdir(lib):
            messagebox.showwarning("Statistics", "Set a valid Library root first.")
            return
        self.set_v2_status("Statistics: computing…")

        def worker():
            try:
                data = LibraryStats.compute(lib)
            except Exception as exc:
                data = {"error": str(exc)}
            self.ui_queue.put(("stats_done", data))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_stats_result(self, data):
        self.stats_data = data
        if "error" in data:
            self.stats_summary.set(f"Error: {data['error']}")
            self.set_v2_status("Statistics: error")
            return
        summary = (
            f"Assets: {data['total_folders']}   "
            f"ZIPs: {data['zip_count']}   "
            f"Total size: {data['total_size_human']}   "
            f"Resolutions detected: {len(data['resolutions'])}"
        )
        self.stats_summary.set(summary)
        try:
            self.stats_preset_tree.delete(*self.stats_preset_tree.get_children())
            for preset, count in sorted(data["preset_breakdown"].items(), key=lambda kv: -kv[1]):
                self.stats_preset_tree.insert("", "end", values=(preset, count))
            self.stats_res_tree.delete(*self.stats_res_tree.get_children())
            for res in RES_LABELS:
                if res in data["resolutions"]:
                    self.stats_res_tree.insert("", "end", values=(res, data["resolutions"][res]))
        except Exception:
            pass
        self.set_v2_status(f"Statistics: {data['total_folders']} assets, {data['total_size_human']}")

    # ================================================================== #
    # v2 — 3D preview tab                                                 #
    # ================================================================== #
    def _build_preview_tab(self):
        tab = tk.Frame(self.notebook, bg=CONTENT_BG)
        self.notebook.add(tab, text="3D Preview")

        header = tk.Frame(tab, bg=CONTENT_PANEL, padx=14, pady=12)
        header.pack(fill="x")
        tk.Label(
            header, text="3D Preview (OBJ / FBX inside ZIPs)", bg=CONTENT_PANEL,
            fg=CONTENT_TEXT, font=("Segoe UI Semibold", 14),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Pick a ZIP to inspect 3D content. Shows a preview image (if any) and geometry info. "
                 "Interactive OpenGL viewer is optional; falls back to static info.",
            bg=CONTENT_PANEL, fg="#DDB9B2", font=("Segoe UI", 9),
            justify="left", wraplength=900,
        ).pack(anchor="w", pady=(2, 8))
        row = tk.Frame(header, bg=CONTENT_PANEL)
        row.pack(anchor="w")
        ttk.Button(row, text="Open ZIP…", command=self.preview_pick_zip).pack(side="left")
        ttk.Button(row, text="Preview selected asset", command=self.preview_selected_asset).pack(side="left", padx=6)

        body = tk.Frame(tab, bg=CONTENT_BG, padx=14, pady=10)
        body.pack(fill="both", expand=True)
        self.preview_image_label = tk.Label(body, bg="#1A0C0E", text="(no preview)", fg="#DDB9B2")
        self.preview_image_label.pack(side="left", fill="both", expand=True, padx=(0, 10))
        info = tk.LabelFrame(body, text="Info", bg=CONTENT_BG, fg=CONTENT_TEXT)
        info.pack(side="right", fill="both", expand=True)
        self.preview_info_text = scrolledtext.ScrolledText(info, height=20, bg="#17090B", fg="#FBEDEA", relief="flat")
        self.preview_info_text.pack(fill="both", expand=True)
        self._preview_opengl_note()

    def _preview_opengl_note(self):
        try:
            import OpenGL  # noqa: F401
            note = "[OpenGL available — interactive viewer could be launched]"
        except Exception:
            note = "[PyOpenGL not installed — showing static preview & info only]"
        self.preview_info_text.insert("end", note + "\n\n")

    def preview_pick_zip(self):
        path = filedialog.askopenfilename(title="Pick 3D ZIP", filetypes=[("ZIP", "*.zip")])
        if path:
            self._do_preview_zip(path)

    def preview_selected_asset(self):
        assets = self.selected_assets()
        if not assets:
            messagebox.showinfo("Preview", "Select an asset in the Library tab first.")
            return
        asset = assets[0]
        folder = asset.get("folder_path") or asset.get("path")
        if not folder or not os.path.isdir(folder):
            return
        zips = []
        for dirpath, _d, files in os.walk(folder):
            for fn in files:
                if fn.lower().endswith(".zip"):
                    zips.append(os.path.join(dirpath, fn))
        if not zips:
            messagebox.showinfo("Preview", "No ZIP files inside the selected asset.")
            return
        self._do_preview_zip(zips[0])

    def _do_preview_zip(self, zip_path):
        self.preview_info_text.delete("1.0", "end")
        self._preview_opengl_note()
        self.preview_info_text.insert("end", f"ZIP: {zip_path}\n")
        self.set_v2_status(f"Preview: {os.path.basename(zip_path)}")
        obj_found, fbx_found = [], []
        preview_png_bytes = None
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    lower = info.filename.lower()
                    if lower.endswith(".obj"):
                        obj_found.append((info.filename, info.file_size))
                    elif lower.endswith(".fbx"):
                        fbx_found.append((info.filename, info.file_size))
                    elif preview_png_bytes is None and lower.endswith((".png", ".jpg", ".jpeg")) and (
                        "preview" in lower or "thumb" in lower or lower.count("/") == 0
                    ):
                        try:
                            preview_png_bytes = zf.read(info.filename)
                        except Exception:
                            pass
        except Exception as exc:
            self.preview_info_text.insert("end", f"ERROR reading zip: {exc}\n")
            return

        self.preview_info_text.insert("end", f"OBJ files: {len(obj_found)}\n")
        for name, size in obj_found[:10]:
            self.preview_info_text.insert("end", f"  • {name}  ({size/1024:.1f} KB)\n")
        self.preview_info_text.insert("end", f"FBX files: {len(fbx_found)}\n")
        for name, size in fbx_found[:10]:
            self.preview_info_text.insert("end", f"  • {name}  ({size/1024:.1f} KB)\n")

        # Basic OBJ vertex/face count if small enough
        if obj_found:
            name = obj_found[0][0]
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    data = zf.read(name).decode("utf-8", errors="replace")
                verts = sum(1 for ln in data.splitlines() if ln.startswith("v "))
                faces = sum(1 for ln in data.splitlines() if ln.startswith("f "))
                self.preview_info_text.insert(
                    "end", f"\nFirst OBJ stats — vertices: {verts}, faces: {faces}\n"
                )
            except Exception as exc:
                self.preview_info_text.insert("end", f"\nOBJ stats error: {exc}\n")

        # Preview image
        if preview_png_bytes and PIL_AVAILABLE:
            try:
                img = Image.open(io.BytesIO(preview_png_bytes))
                img.thumbnail((480, 480))
                self._preview_photo = ImageTk.PhotoImage(img)
                self.preview_image_label.configure(image=self._preview_photo, text="")
            except Exception:
                self.preview_image_label.configure(image="", text="(preview decode failed)")
        else:
            self.preview_image_label.configure(image="", text="(no preview image in ZIP)")

    # ================================================================== #
    # v2 — addon export                                                   #
    # ================================================================== #
    def _read_local_file(self, fname):
        p = os.path.join(app_dir(), fname)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def export_blender_addon(self):
        default = "blender_addon.py"
        path = filedialog.asksaveasfilename(
            title="Export Blender addon",
            defaultextension=".py",
            initialfile=default,
            filetypes=[("Python", "*.py")],
        )
        if not path:
            return
        content = self._read_local_file("blender_addon.py") or BLENDER_ADDON_FALLBACK
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("Export", f"Blender addon saved:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export", f"Error: {exc}")

    def export_max_macroscript(self):
        default = "max_addon_macroscript.ms"
        path = filedialog.asksaveasfilename(
            title="Export 3ds Max macroscript",
            defaultextension=".ms",
            initialfile=default,
            filetypes=[("MaxScript", "*.ms")],
        )
        if not path:
            return
        content = self._read_local_file("max_addon_macroscript.ms") or MAX_MACROSCRIPT_FALLBACK
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("Export", f"Macroscript saved:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export", f"Error: {exc}")


# Fallback embedded addon sources (used only if local files are missing)
BLENDER_ADDON_FALLBACK = "# Blender addon missing — see blender_addon.py in app folder.\n"
MAX_MACROSCRIPT_FALLBACK = "-- MaxScript missing — see max_addon_macroscript.ms in app folder.\n"



if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()

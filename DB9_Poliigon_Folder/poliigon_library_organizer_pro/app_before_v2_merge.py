import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

try:
    from PIL import Image, ImageOps, ImageTk

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


def enable_dpi_awareness():
    """Keep Tkinter UI crisp on Windows high-DPI displays."""
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


enable_dpi_awareness()

APP_TITLE = "Poliigon Library Organizer PRO"
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
        return output_path
    except Exception:
        return None


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
        groups.setdefault(base, []).append(full_path)
    return groups


def count_group_steps(groups):
    total = 0
    for files in groups.values():
        total += len(files) + 1
    return total


def process_download_folder(folder, library_root, presets, rules, tags_db, log, progress, should_cancel=None):
    should_cancel = should_cancel or (lambda: False)
    groups = collect_zip_groups(folder)
    if not groups:
        raise RuntimeError("No ZIP files were found in the selected source folder.")

    total_steps = max(count_group_steps(groups), 1)
    current_step = 0
    moved = 0
    texture_folders = 0

    for base, files in sorted(groups.items()):
        if should_cancel():
            raise TaskCancelled()
        preset = auto_pick(base, presets, rules)
        target = os.path.join(library_root, preset, base)
        os.makedirs(target, exist_ok=True)
        texture_folders += 1

        labeled_files = label_zip_variants(files)
        extra_texts = [os.path.basename(item["path"]) for item in labeled_files] + [item["res"] for item in labeled_files]
        tags_db[base] = merge_tags(tags_db.get(base, []), auto_tags_for_asset(base, preset, extra_texts))

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
        log(f"[TEXTURE] {base} | preset={preset} | tags={tag_text}")

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


def repair_asset_folder(asset_path, asset_name, log):
    if not os.path.isdir(asset_path):
        return {"renamed": 0, "merged": 0, "warnings": 0}

    zip_files = [
        os.path.join(asset_path, name)
        for name in os.listdir(asset_path)
        if os.path.isfile(os.path.join(asset_path, name)) and name.lower().endswith(".zip")
    ]

    renamed = 0
    warnings = 0
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

        missing_lower = expected_lower_resolutions(set(found_res))
        if missing_lower and any(res in found_res for res in ["4k", "8k", "16k", "24k", "32k"]):
            warnings += 1
            log(f"[CHECK] {asset_name} missing lower sizes: {', '.join(missing_lower)}")

        if preview_source:
            preview_path = extract_preview_from_zip(preview_source, asset_path, asset_name)
            if preview_path:
                log(f"[PREVIEW] refreshed {os.path.basename(preview_path)}")

    return {"renamed": renamed, "merged": 0, "warnings": warnings}


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


def build_asset_record(library_root, folder_path, asset_name, tags_db):
    preset = os.path.basename(os.path.dirname(folder_path))
    clean_name = clean_base(asset_name)
    rel = os.path.relpath(folder_path, library_root)
    file_names = os.listdir(folder_path) if os.path.isdir(folder_path) else []
    detected = auto_tags_for_asset(clean_name, preset, file_names)
    merged_tags = merge_tags(tags_db.get(clean_name, []), detected)
    preview = find_preview_image(folder_path)
    resolutions = sorted(
        detect_resolutions_in_folder(folder_path),
        key=lambda item: RES_LABELS.index(item) if item in RES_LABELS else 999,
    )
    modified = os.path.getmtime(folder_path) if os.path.exists(folder_path) else 0
    return {
        "name": clean_name,
        "folder_name": asset_name,
        "path": folder_path,
        "rel": rel,
        "preset": preset,
        "tags": merged_tags,
        "preview": preview,
        "resolutions": resolutions,
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


def search_assets(library_root, search_root, query, tags_db, sort_by):
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
            asset = build_asset_record(library_root, folder_path, directory, tags_db)
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
        self.thumb = make_thumbnail(asset.get("preview"))

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


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_json(CONFIG_FILE, {})
        self.rules = load_json(LEARNING_FILE, [])
        self.tags_db = load_json(TAGS_FILE, {})
        self.drag_assets = []
        self._asset_cache = []
        self._search_cache = []
        self.selected_indices = set()
        self.thumb_tiles = []
        self.ui_queue = queue.Queue()
        self.worker = None
        self._search_timer = None
        self._cancel_flag = threading.Event()
        self._data_lock = threading.Lock()
        self.normalize_preset_config()

        self.root.title(APP_TITLE)
        self.root.geometry("1460x900")
        self.root.configure(bg=CONTENT_BG)
        self.set_window_icon()
        self.configure_styles()
        self.build()
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

    def build(self):
        main = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
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

        self.load_logo(left)
        library_section = self.make_sidebar_section(left, "Thư viện đích", "Nơi app tạo thư viện texture đã sắp xếp hoàn chỉnh.")
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
        ttk.Label(topbar, text="Preset gốc").grid(row=0, column=1, sticky="w", padx=(12, 0), pady=(0, 6))
        ttk.Label(topbar, text="Sắp xếp").grid(row=0, column=2, sticky="w", padx=(12, 0), pady=(0, 6))

        self.search_entry = ttk.Entry(topbar, textvariable=self.search_query)
        self.search_entry.grid(row=1, column=0, sticky="ew")
        self.search_root_combo = ttk.Combobox(topbar, textvariable=self.search_root, state="readonly")
        self.search_root_combo.grid(row=1, column=1, sticky="ew", padx=(12, 0))
        self.sort_combo = ttk.Combobox(topbar, textvariable=self.sort_by, values=SORT_OPTIONS, state="readonly")
        self.sort_combo.grid(row=1, column=2, sticky="ew", padx=(12, 0))

        self.search_query.trace_add("write", lambda *_args: self.debounced_search())
        self.search_root_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_search_results())
        self.sort_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_sort_changed())

        actionbar = tk.Frame(control_panel, bg=CONTENT_PANEL)
        actionbar.pack(fill="x", pady=(12, 10))
        actionbar.columnconfigure(0, weight=1)
        actionbar.columnconfigure(1, weight=1)
        actionbar.columnconfigure(2, weight=1)
        actionbar.columnconfigure(3, weight=1)
        self.make_inline_action(actionbar, "Move selected", "Chuyển preset cho các tile đang chọn.", self.bulk_move_selected).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.make_inline_action(actionbar, "Tag selected", "Gắn tag thủ công cho nhóm đã chọn.", self.bulk_tag_selected).grid(row=0, column=1, sticky="ew", padx=8)
        self.make_inline_action(actionbar, "Auto tag selected", "Tự sinh tag cho nhóm đã chọn.", self.auto_tag_selected).grid(row=0, column=2, sticky="ew", padx=8)
        self.make_inline_action(actionbar, "Clear selection", "Bỏ chọn toàn bộ tile hiện tại.", self.clear_selection).grid(row=0, column=3, sticky="ew", padx=(8, 0))

        tagbar = ttk.Frame(control_panel)
        tagbar.pack(fill="x", pady=(2, 10))
        ttk.Entry(tagbar, textvariable=self.tag_entry).pack(side="left", fill="x", expand=True)
        ttk.Button(tagbar, text="Thêm tag", command=self.add_tag_to_selected_asset).pack(side="left", padx=6)

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
            """HUONG DAN SU DUNG POLIIGON LIBRARY ORGANIZER PRO

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
        elif task_name == "auto_tag":
            updated = payload["updated"]
            checked = payload["checked"]
            self.set_status(f"Completed: updated tags for {updated} of {checked} texture folder(s)")
            self.log(f"[DONE] auto-tag updated {updated} of {checked} texture folder(s)")

        self.save_runtime_data()
        self.refresh_presets_from_library()
        self.rebuild_asset_cache()
        self.refresh_search_results()

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

    def load_library_state(self, library_root):
        if not library_root or not os.path.isdir(library_root):
            return
        paths = library_state_paths(library_root)
        portable_cfg = load_json(paths["config"], None)
        portable_rules = load_json(paths["rules"], None)
        portable_tags = load_json(paths["tags"], None)

        if portable_cfg is not None or portable_rules is not None or portable_tags is not None:
            if isinstance(portable_cfg, dict):
                self.cfg["custom_presets"] = portable_cfg.get("custom_presets", [])
                self.cfg["sort_by"] = portable_cfg.get("sort_by", self.cfg.get("sort_by", SORT_OPTIONS[0]))
            else:
                self.cfg["custom_presets"] = infer_custom_presets_from_library(library_root)
            self.rules = portable_rules if isinstance(portable_rules, list) else []
            self.tags_db = portable_tags if isinstance(portable_tags, dict) else {}
            self.normalize_preset_config()
            if hasattr(self, "sort_by"):
                self.sort_by.set(self.cfg.get("sort_by", SORT_OPTIONS[0]))
            self.set_status(f"Loaded portable library state from {library_root}")
            self.log(f"[LOAD] portable library state loaded from {library_root}")
        else:
            self.cfg["custom_presets"] = infer_custom_presets_from_library(library_root)
            self.rules = []
            self.tags_db = {}
            self.normalize_preset_config()
            if hasattr(self, "sort_by"):
                self.sort_by.set(self.cfg.get("sort_by", SORT_OPTIONS[0]))
            self.set_status(f"Loaded library structure from {library_root}")
            self.log(f"[LOAD] inferred presets from library structure in {library_root}")

        self.cfg["library_root"] = library_root
        self.refresh_presets_from_library()
        self.rebuild_asset_cache()
        self.refresh_search_results()

    def refresh_presets_from_library(self):
        presets = get_presets_from_config(self.cfg.get("custom_presets", []))
        self.cfg["dynamic_presets"] = presets
        self.search_root_combo["values"] = ["All"] + presets
        if self.search_root.get() not in ["All"] + presets:
            self.search_root.set("All")
        self.refresh_rule_list()

    def current_presets(self):
        return self.cfg.get("dynamic_presets") or get_presets_from_config(self.cfg.get("custom_presets", []))

    def rebuild_asset_cache(self):
        self._asset_cache = []
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
                    asset = build_asset_record(library_root, folder_path, name, self.tags_db)
                    self._asset_cache.append(asset)

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
        presets = self.current_presets()
        self.search_root_combo["values"] = ["All"] + presets
        if self.search_root.get() not in ["All"] + presets:
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

        self.result_info.set(f"{len(self._search_cache)} texture folder(s)")
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
        presets = self.current_presets()
        target = simpledialog.askstring("Move selected", f"Enter target preset:\n{', '.join(presets)}")
        if not target or target not in presets:
            return
        if not messagebox.askyesno("Confirm", f"Move {len(assets)} texture(s) to {target}?"):
            return
        self.drag_assets = assets
        self.apply_drag_to_rule_index(
            list(self.rule_list.get(0, tk.END)).index(f"PRESET | {target}"),
            move_now=True,
        )

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


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()

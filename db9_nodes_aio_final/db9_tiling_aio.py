"""
DB9 Tiling AIO - clean bundle
"""

import json
import math
import shutil
from pathlib import Path

import torch
import torch.nn.functional as F

CORE_WORK_TILE_SCHEMA = "core_work_local_padding_v1"

CONFLICT_FILES = [
    "db9_auto_tiling_full.py",
    "db9_auto_tiling_bundle.py",
    "db9_auto_tiling_bundle_sdvn_compatible.py",
    "db9_auto_tiling_v2.py",
    "db9_auto_tiling_priority_canny.py",
    "__init___patch.txt",
    "__init___sdvn_compatible.py",
    "__init___complete.py",
    "apply_steps.md",
    "merge_notes.md",
    "bundle_with_priority_nodes.md",
    "final_node_list.md",
    "workflow_pass1_canny_template.json",
    "workflow_priority_rerun_template.json",
    "workflow_pass1_canny_sdvn_compatible.json",
    "workflow_priority_rerun_sdvn_compatible.json",
    "priority_rerun_and_canny.md",
    "workflow_replacement_map.md",
]

KEEP_FILES = {
    "__init__.py",
    "requirements.txt",
    "README.md",
    "db9_tiling_aio.py",
    "db9_macro_nodes.py",
    "db9_tone_and_compare.py",
    "db9_live_editor.py",
}

def db9_backup_and_remove_conflicts(repo_dir: str, dry_run: bool = True) -> dict:
    repo = Path(repo_dir)
    backup_dir = repo / "_db9_backup_before_clean_install"
    found = []
    removed = []
    kept = []
    if not repo.exists():
        raise FileNotFoundError(f"Repo folder not found: {repo}")
    if not dry_run:
        backup_dir.mkdir(exist_ok=True)
    for name in CONFLICT_FILES:
        p = repo / name
        if p.exists():
            found.append(name)
            if dry_run:
                continue
            target = backup_dir / name
            if p.is_file():
                shutil.copy2(p, target)
                p.unlink()
            elif p.is_dir():
                shutil.copytree(p, target, dirs_exist_ok=True)
                shutil.rmtree(p)
            removed.append(name)
    for name in KEEP_FILES:
        if (repo / name).exists():
            kept.append(name)
    return {"repo": str(repo), "dry_run": dry_run, "backup_dir": str(backup_dir), "found_conflicts": found, "removed": removed, "kept": kept}

def db9_validate_install(repo_dir: str) -> dict:
    repo = Path(repo_dir)
    required = ["__init__.py", "db9_tiling_aio.py", "README.md"]
    missing = [name for name in required if not (repo / name).exists()]
    return {"repo": str(repo), "missing": missing, "ok": len(missing) == 0}

def db9_write_manifest(repo_dir: str) -> str:
    repo = Path(repo_dir)
    manifest = {"package": "DB9 Tiling AIO", "files": sorted([p.name for p in repo.iterdir() if p.is_file()])}
    manifest_path = repo / "db9_install_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(manifest_path)

def _ensure_bhwc(image):
    if image.ndim != 4:
        raise ValueError(f"Expected IMAGE tensor [B,H,W,C], got {tuple(image.shape)}")
    return image

def _rgb_to_luma(img):
    return 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]

def _parse_tile_sizes(tile_sizes_csv, min_tile_size, max_tile_size):
    vals = []
    for token in tile_sizes_csv.split(","):
        token = token.strip()
        if not token:
            continue
        v = int(token)
        if min_tile_size <= v <= max_tile_size:
            vals.append(v)
    vals = sorted(set(vals), reverse=True)
    if not vals:
        raise ValueError("No valid tile sizes in range.")
    return vals

def _auto_overlap(tile_size):
    if tile_size >= 1984:
        return 224
    elif tile_size >= 1792:
        return 192
    elif tile_size >= 1600:
        return 192
    return 160

def _make_tile_seed(base_seed, row, col, idx, seed_mode, attempt=0):
    if seed_mode == "fixed":
        seed = base_seed
    elif seed_mode == "fixed_with_grid_offset":
        seed = base_seed + row * 131 + col * 17
    elif seed_mode == "row":
        seed = base_seed + row * 100003
    elif seed_mode == "col":
        seed = base_seed + col * 100003
    elif seed_mode == "golden_jitter":
        seed = base_seed + row * 9973 + col * 7919 + idx * 313
    else:
        seed = base_seed + idx * 1000
    return int((seed + attempt * 7919) % (2**31))

def _score_candidate(width, height, tile_size, overlap, prefer_larger_tiles):
    stride = tile_size
    cols = math.ceil(width / tile_size)
    rows = math.ceil(height / tile_size)
    last_w = width - (cols - 1) * tile_size
    last_h = height - (rows - 1) * tile_size
    edge_imbalance = (tile_size - last_w) + (tile_size - last_h)
    total_tiles = cols * rows
    score = total_tiles * 1000 + edge_imbalance * 0.01 + abs(cols - rows) * 10
    if prefer_larger_tiles:
        score -= tile_size * 0.1
    return {"score": score, "tile_size": tile_size, "overlap": overlap, "stride": stride, "cols": cols, "rows": rows, "total_tiles": total_tiles}

def _pad_image_bhwc(image_bhwc, pad_left, pad_right, pad_top, pad_bottom, pad_mode):
    if pad_left == pad_right == pad_top == pad_bottom == 0:
        return image_bhwc
    x = image_bhwc.permute(0, 3, 1, 2)  # BHWC -> BCHW
    _, _, h, w = x.shape
    if pad_mode == "reflect":
        if w <= 1 or h <= 1:
            x = F.pad(x, (pad_left, pad_right, pad_top, pad_bottom), mode="constant", value=0.0)
        elif pad_left >= w or pad_right >= w or pad_top >= h or pad_bottom >= h:
            x = F.pad(x, (pad_left, pad_right, pad_top, pad_bottom), mode="replicate")
        else:
            x = F.pad(x, (pad_left, pad_right, pad_top, pad_bottom), mode="reflect")
    elif pad_mode == "replicate":
        x = F.pad(x, (pad_left, pad_right, pad_top, pad_bottom), mode="replicate")
    else:
        x = F.pad(x, (pad_left, pad_right, pad_top, pad_bottom), mode="constant", value=0.0)

    return x.permute(0, 2, 3, 1)  # BCHW -> BHWC

def _build_core_work_tile_meta(W, H, tile_size, overlap, row, col, idx, base_seed, seed_mode, core_box=None):
    if core_box is None:
        core_x0 = col * tile_size
        core_y0 = row * tile_size
        core_x1 = min(core_x0 + tile_size, W)
        core_y1 = min(core_y0 + tile_size, H)
    else:
        core_x0, core_y0, core_x1, core_y1 = core_box
    work_x0 = core_x0 - overlap
    work_y0 = core_y0 - overlap
    work_x1 = core_x1 + overlap
    work_y1 = core_y1 + overlap
    src_x0 = max(work_x0, 0)
    src_y0 = max(work_y0, 0)
    src_x1 = min(work_x1, W)
    src_y1 = min(work_y1, H)
    pad_left = max(0, -work_x0)
    pad_top = max(0, -work_y0)
    pad_right = max(0, work_x1 - W)
    pad_bottom = max(0, work_y1 - H)
    core_w = core_x1 - core_x0
    core_h = core_y1 - core_y0
    work_w = work_x1 - work_x0
    work_h = work_y1 - work_y0
    batch_work_w = tile_size + overlap * 2
    batch_work_h = tile_size + overlap * 2
    return {
        "index": idx,
        "row": row,
        "col": col,
        "core_x0": core_x0,
        "core_y0": core_y0,
        "core_x1": core_x1,
        "core_y1": core_y1,
        "work_x0": work_x0,
        "work_y0": work_y0,
        "work_x1": work_x1,
        "work_y1": work_y1,
        "src_x0": src_x0,
        "src_y0": src_y0,
        "src_x1": src_x1,
        "src_y1": src_y1,
        "pad_left": pad_left,
        "pad_top": pad_top,
        "pad_right": pad_right,
        "pad_bottom": pad_bottom,
        "core_in_tile_x0": core_x0 - work_x0,
        "core_in_tile_y0": core_y0 - work_y0,
        "core_in_tile_x1": core_x0 - work_x0 + core_w,
        "core_in_tile_y1": core_y0 - work_y0 + core_h,
        "core_w": core_w,
        "core_h": core_h,
        "work_w": work_w,
        "work_h": work_h,
        "batch_work_w": batch_work_w,
        "batch_work_h": batch_work_h,
        "seed": _make_tile_seed(base_seed, row, col, idx, seed_mode),
        "attempt": 0,
        # Legacy aliases keep older QA/debug consumers readable without driving composite.
        "x0": core_x0,
        "y0": core_y0,
        "x1": core_x1,
        "y1": core_y1,
        "tile_w": core_w,
        "tile_h": core_h,
    }

def _extract_core_work_tile(image, tile, tile_size, pad_mode):
    cropped = image[:, tile["src_y0"]:tile["src_y1"], tile["src_x0"]:tile["src_x1"], :]
    padded = _pad_image_bhwc(
        cropped,
        tile["pad_left"],
        tile["pad_right"],
        tile["pad_top"],
        tile["pad_bottom"],
        pad_mode,
    )
    _, ph, pw, _ = padded.shape
    target_h = int(tile.get("batch_work_h", tile_size + int(tile.get("pad_top", 0)) + int(tile.get("pad_bottom", 0))))
    target_w = int(tile.get("batch_work_w", tile_size + int(tile.get("pad_left", 0)) + int(tile.get("pad_right", 0))))
    if ph > target_h or pw > target_w:
        raise ValueError(f"DB9 tile {tile.get('index', '?')} exceeded batch work size: got {pw}x{ph}, target {target_w}x{target_h}")
    if ph < target_h or pw < target_w:
        padded = _pad_image_bhwc(padded, 0, target_w - pw, 0, target_h - ph, pad_mode)
    return padded

def _extract_tile_with_padding(image, tile, tile_size, pad_mode):
    _, H, W, _ = image.shape
    x0, y0, x1, y1 = tile["x0"], tile["y0"], tile["x1"], tile["y1"]
    sx0 = max(0, x0)
    sy0 = max(0, y0)
    sx1 = min(W, x1)
    sy1 = min(H, y1)
    cropped = image[:, sy0:sy1, sx0:sx1, :]
    pad_left = max(0, -x0)
    pad_top = max(0, -y0)
    pad_right = max(0, x1 - W)
    pad_bottom = max(0, y1 - H)
    if any(v > 0 for v in [pad_left, pad_right, pad_top, pad_bottom]) or cropped.shape[1] != tile_size or cropped.shape[2] != tile_size:
        cropped = _pad_image_bhwc(cropped, pad_left, pad_right, pad_top, pad_bottom, pad_mode)
        _, ph, pw, _ = cropped.shape
        if ph < tile_size or pw < tile_size:
            cropped = _pad_image_bhwc(cropped, 0, tile_size - pw, 0, tile_size - ph, pad_mode)
    return cropped

def _avg_blur_bhwc(img, kernel_size=5):
    if kernel_size <= 1:
        return img
    pad = kernel_size // 2
    x = img.permute(0, 3, 1, 2)
    x = F.avg_pool2d(x, kernel_size, stride=1, padding=pad)
    return x.permute(0, 2, 3, 1)

def _soft_clamp_image(img, strength=0.15):
    if strength <= 0:
        return img
    tonemapped = img / (1.0 + img)
    return torch.clamp(img * (1.0 - strength) + tonemapped * strength, 0.0, 1.0)

def _micro_contrast(img, strength=0.08):
    if strength <= 0:
        return img
    blurred = _avg_blur_bhwc(img, kernel_size=5)
    detail = img - blurred
    return torch.clamp(img + detail * strength, 0.0, 1.0)

def _extract_highlight(img, blur_radius=9, threshold=0.72, gain=1.0):
    k = max(1, int(blur_radius) | 1)
    blurred = _avg_blur_bhwc(img, kernel_size=min(k, 31))
    hi = torch.relu(img - blurred)
    luma = _rgb_to_luma(hi)
    mask = (luma >= threshold).float().unsqueeze(-1)
    return torch.clamp(hi * mask * gain, 0.0, 1.0)

def _tile_debug_metrics(img, highlight, seed=-1):
    luma = _rgb_to_luma(img)
    hi_luma = _rgb_to_luma(highlight)
    return {"tile_mean_luma": float(luma.mean().item()), "tile_std_luma": float(luma.std().item()), "highlight_energy": float(hi_luma.mean().item()), "seed": int(seed)}

def _center_priority_mask(tile_h, tile_w, strength=0.9):
    yy = torch.linspace(-1.0, 1.0, steps=tile_h)
    xx = torch.linspace(-1.0, 1.0, steps=tile_w)
    gy, gx = torch.meshgrid(yy, xx, indexing="ij")
    dist = torch.maximum(torch.abs(gx), torch.abs(gy))
    mask = torch.clamp(1.0 - dist, 0.0, 1.0)
    gamma = max(0.1, 1.0 + strength * 2.0)
    return (mask ** gamma).unsqueeze(-1)


_LORA_RATIOS = {
    "none": 1.0, "1:1": 1.0, "4:3": 4/3, "3:2": 3/2,
    "16:9": 16/9, "2:1": 2.0, "9:16": 9/16, "2:3": 2/3, "3:4": 3/4,
}

def _adjust_tile_for_lora_ratio(tile, ratio, W, H):
    """Expand work region so the KSampler sees a window matching the LoRA training ratio."""
    if abs(ratio - 1.0) < 0.01:
        return tile
    t = dict(tile)
    sq = int(t["batch_work_w"])
    if ratio > 1.0:
        new_w = max(sq, (round(sq * ratio) // 8) * 8)
        new_h = sq
    else:
        new_w = sq
        new_h = max(sq, (round(sq / ratio) // 8) * 8)
    extra_x = new_w - sq;  extra_y = new_h - sq
    add_l = extra_x // 2;  add_r = extra_x - add_l
    add_t = extra_y // 2;  add_b = extra_y - add_t
    nwx0 = t["work_x0"] - add_l;  nwx1 = t["work_x1"] + add_r
    nwy0 = t["work_y0"] - add_t;  nwy1 = t["work_y1"] + add_b
    t["src_x0"] = max(0, nwx0);  t["src_y0"] = max(0, nwy0)
    t["src_x1"] = min(W, nwx1);  t["src_y1"] = min(H, nwy1)
    t["pad_left"]   = max(0, -nwx0);  t["pad_top"]    = max(0, -nwy0)
    t["pad_right"]  = max(0, nwx1 - W); t["pad_bottom"] = max(0, nwy1 - H)
    t["work_x0"] = nwx0; t["work_x1"] = nwx1
    t["work_y0"] = nwy0; t["work_y1"] = nwy1
    t["work_w"]  = nwx1 - nwx0; t["work_h"] = nwy1 - nwy0
    t["batch_work_w"] = new_w;   t["batch_work_h"] = new_h
    t["core_in_tile_x0"] = t["core_x0"] - nwx0
    t["core_in_tile_y0"] = t["core_y0"] - nwy0
    t["core_in_tile_x1"] = t["core_x1"] - nwx0
    t["core_in_tile_y1"] = t["core_y1"] - nwy0
    return t

def _build_cosine_feather_mask(h, w, feather_px, has_l, has_r, has_t, has_b, device, dtype):
    mask = torch.ones((h, w, 1), dtype=dtype, device=device)
    f = min(feather_px, w // 2, h // 2)
    if f <= 0:
        return mask
    idx = torch.arange(f, dtype=dtype, device=device)
    ramp = 0.5 * (1.0 - torch.cos(math.pi * idx / max(f, 1)))  # shape [f]
    if has_l:  mask[:, :f,  :] *= ramp.view(1, f, 1)
    if has_r:  mask[:, -f:, :] *= ramp.flip(0).view(1, f, 1)
    if has_t:  mask[:f,  :, :] *= ramp.view(f, 1, 1)
    if has_b:  mask[-f:, :, :] *= ramp.flip(0).view(f, 1, 1)
    return mask

def _accumulate_core_tile_feathered(canvas, weights, tile_img, tile_meta, feather_px, cols, rows):
    _validate_core_meta(tile_meta, tile_img)
    r, c   = int(tile_meta["row"]), int(tile_meta["col"])
    has_l  = c > 0;  has_r = c < cols - 1
    has_t  = r > 0;  has_b = r < rows - 1
    tcx0, tcy0 = int(tile_meta["core_in_tile_x0"]), int(tile_meta["core_in_tile_y0"])
    tcx1, tcy1 = int(tile_meta["core_in_tile_x1"]), int(tile_meta["core_in_tile_y1"])
    cx0, cy0   = int(tile_meta["core_x0"]), int(tile_meta["core_y0"])
    cx1, cy1   = int(tile_meta["core_x1"]), int(tile_meta["core_y1"])
    th, tw = tile_img.shape[0], tile_img.shape[1]
    f = min(feather_px, tcx0, tcy0, tw - tcx1, th - tcy1,
            max(1, (cx1 - cx0) // 2), max(1, (cy1 - cy0) // 2))
    f = max(0, f)
    ex0 = tcx0 - (f if has_l else 0);  ex1 = tcx1 + (f if has_r else 0)
    ey0 = tcy0 - (f if has_t else 0);  ey1 = tcy1 + (f if has_b else 0)
    dx0 = max(0, cx0 - (f if has_l else 0));  dy0 = max(0, cy0 - (f if has_t else 0))
    dx1 = min(canvas.shape[1], cx1 + (f if has_r else 0))
    dy1 = min(canvas.shape[0], cy1 + (f if has_b else 0))
    region = tile_img[ey0:ey1, ex0:ex1, :]
    rh, rw = region.shape[0], region.shape[1]
    if rh == 0 or rw == 0:
        return
    mask = _build_cosine_feather_mask(rh, rw, f, has_l, has_r, has_t, has_b,
                                       tile_img.device, tile_img.dtype)
    ah = min(dy1 - dy0, rh); aw = min(dx1 - dx0, rw)
    canvas[dy0:dy0+ah, dx0:dx0+aw, :] += region[:ah, :aw, :] * mask[:ah, :aw, :]
    weights[dy0:dy0+ah, dx0:dx0+aw, :] += mask[:ah, :aw, :]

def _sobel_edges_from_luma(luma_hw):
    x = luma_hw.unsqueeze(0).unsqueeze(0)
    kx = torch.tensor([[-1., 0., 1.], [-2., 0., 2.], [-1., 0., 1.]], device=x.device, dtype=x.dtype).view(1, 1, 3, 3)
    ky = torch.tensor([[-1., -2., -1.], [0., 0., 0.], [1., 2., 1.]], device=x.device, dtype=x.dtype).view(1, 1, 3, 3)
    gx = F.conv2d(x, kx, padding=1)[0, 0]
    gy = F.conv2d(x, ky, padding=1)[0, 0]
    mag = torch.sqrt(gx * gx + gy * gy + 1e-8)
    return gx, gy, mag

def _canny_like_edge_map(tile_img, low_thresh=0.08, high_thresh=0.18, blur_first=True):
    if tile_img.ndim == 4:
        tile_img = tile_img[0]
    luma = _rgb_to_luma(tile_img)
    if blur_first:
        x = luma.unsqueeze(0).unsqueeze(0)
        x = F.avg_pool2d(x, 3, stride=1, padding=1)
        luma = x[0, 0]
    gx, gy, mag = _sobel_edges_from_luma(luma)
    mag = mag / (mag.mean() + 1e-6)
    strong = (mag >= high_thresh).float()
    weak = ((mag >= low_thresh) & (mag < high_thresh)).float()
    strong_expanded = F.max_pool2d(strong.unsqueeze(0).unsqueeze(0), 3, stride=1, padding=1)[0, 0]
    edge = torch.clamp(strong + weak * (strong_expanded > 0).float(), 0.0, 1.0)
    return torch.clamp(edge * mag, 0.0, 1.0)

def _canny_border_suppressed_mask(tile_img, center_strength=0.95, low_thresh=0.08, high_thresh=0.18, border_edge_penalty=0.85, border_start=0.12):
    if tile_img.ndim == 4:
        tile_img = tile_img[0]
    h, w, _ = tile_img.shape
    device = tile_img.device
    base = _center_priority_mask(h, w, strength=center_strength).to(device)
    edge_map = _canny_like_edge_map(tile_img, low_thresh=low_thresh, high_thresh=high_thresh, blur_first=True)
    yy = torch.linspace(-1.0, 1.0, steps=h, device=device)
    xx = torch.linspace(-1.0, 1.0, steps=w, device=device)
    gy, gx = torch.meshgrid(yy, xx, indexing="ij")
    edge_dist = torch.maximum(torch.abs(gx), torch.abs(gy))
    border_zone = torch.clamp((edge_dist - border_start) / max(1e-6, (1.0 - border_start)), 0.0, 1.0)
    border_zone = border_zone ** 1.6
    penalty = torch.clamp(edge_map * border_zone * border_edge_penalty, 0.0, 0.97).unsqueeze(-1)
    mask = base * (1.0 - penalty)
    return torch.clamp(mask, 0.003, 1.0)

def _accumulate_tile(canvas, weights, tile_img, tile_meta, mask):
    x0 = tile_meta["x0"]; y0 = tile_meta["y0"]; tile_h = tile_meta["tile_h"]; tile_w = tile_meta["tile_w"]
    valid_tile = tile_img[:tile_h, :tile_w, :]; valid_mask = mask[:tile_h, :tile_w, :]
    canvas[y0:y0 + tile_h, x0:x0 + tile_w, :] += valid_tile * valid_mask
    weights[y0:y0 + tile_h, x0:x0 + tile_w, :] += valid_mask

def _validate_core_meta(tile_meta, tile_img):
    core_w = int(tile_meta["core_x1"]) - int(tile_meta["core_x0"])
    core_h = int(tile_meta["core_y1"]) - int(tile_meta["core_y0"])
    tile_core_w = int(tile_meta["core_in_tile_x1"]) - int(tile_meta["core_in_tile_x0"])
    tile_core_h = int(tile_meta["core_in_tile_y1"]) - int(tile_meta["core_in_tile_y0"])
    if core_w != tile_core_w or core_h != tile_core_h:
        raise ValueError(f"DB9 tile {tile_meta.get('index', '?')} core size mismatch: canvas={core_w}x{core_h}, tile={tile_core_w}x{tile_core_h}")
    if int(tile_meta["core_in_tile_x1"]) > tile_img.shape[1] or int(tile_meta["core_in_tile_y1"]) > tile_img.shape[0]:
        raise ValueError(f"DB9 tile {tile_meta.get('index', '?')} core_in_tile exceeds processed tile bounds.")

def _accumulate_core_tile(canvas, weights, tile_img, tile_meta, mask=None):
    _validate_core_meta(tile_meta, tile_img)
    cx0 = int(tile_meta["core_in_tile_x0"])
    cy0 = int(tile_meta["core_in_tile_y0"])
    cx1 = int(tile_meta["core_in_tile_x1"])
    cy1 = int(tile_meta["core_in_tile_y1"])
    x0 = int(tile_meta["core_x0"])
    y0 = int(tile_meta["core_y0"])
    x1 = int(tile_meta["core_x1"])
    y1 = int(tile_meta["core_y1"])
    core = tile_img[cy0:cy1, cx0:cx1, :]
    if mask is None:
        canvas[y0:y1, x0:x1, :] = core
        weights[y0:y1, x0:x1, :] = 1.0
        return
    core_mask = mask[cy0:cy1, cx0:cx1, :]
    canvas[y0:y1, x0:x1, :] += core * core_mask
    weights[y0:y1, x0:x1, :] += core_mask

def _core_region_from_tile(tile_img, tile_meta):
    _validate_core_meta(tile_meta, tile_img)
    return tile_img[
        int(tile_meta["core_in_tile_y0"]):int(tile_meta["core_in_tile_y1"]),
        int(tile_meta["core_in_tile_x0"]):int(tile_meta["core_in_tile_x1"]),
        :,
    ]

def _safe_normalize(canvas, weights, eps=1e-8):
    return canvas / torch.clamp(weights, min=eps)

def _simple_l2(a, b):
    return float(torch.mean((a - b) ** 2).item())

def _simple_ssim_proxy(a, b):
    a_l = _rgb_to_luma(a); b_l = _rgb_to_luma(b)
    a_mean = a_l.mean(); b_mean = b_l.mean(); a_std = a_l.std(); b_std = b_l.std()
    if a_std.item() < 1e-8 or b_std.item() < 1e-8:
        return 1.0
    corr = ((a_l - a_mean) * (b_l - b_mean)).mean() / (a_std * b_std + 1e-8)
    return float(torch.clamp(corr, -1.0, 1.0).item())

def _gradient_mismatch_score(a, b):
    ax = torch.abs(a[:, 1:, :] - a[:, :-1, :]); bx = torch.abs(b[:, 1:, :] - b[:, :-1, :])
    ay = torch.abs(a[1:, :, :] - a[:-1, :, :]); by = torch.abs(b[1:, :, :] - b[:-1, :, :])
    return float((torch.mean(torch.abs(ax - bx)) + torch.mean(torch.abs(ay - by))).item())

class DB9TilePlanV2:
    RETURN_TYPES = ("DB9_TILE_PLAN", "INT", "INT", "INT", "INT", "STRING")
    RETURN_NAMES = ("tile_plan", "total_tiles", "chosen_tile_size", "cols", "rows", "debug_info")
    FUNCTION = "plan_tiles"
    CATEGORY = "DB9/AIO"
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE",), "min_tile_size": ("INT", {"default": 1536, "min": 512, "max": 4096, "step": 64}), "max_tile_size": ("INT", {"default": 2048, "min": 512, "max": 4096, "step": 64}), "overlap_mode": (["auto", "manual"], {"default": "auto"}), "overlap": ("INT", {"default": 224, "min": 0, "max": 1024, "step": 8}), "prefer_larger_tiles": ("BOOLEAN", {"default": True}), "pad_mode": (["reflect", "replicate", "constant"], {"default": "replicate"}), "base_seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}), "seed_mode": (["fixed", "fixed_with_grid_offset", "row", "col", "golden_jitter"], {"default": "fixed_with_grid_offset"}),
             "lora_aspect_ratio": (["none", "1:1", "4:3", "3:2", "16:9", "2:1", "9:16", "2:3", "3:4"], {"default": "none"})}, "optional": {"tile_sizes_csv": ("STRING", {"default": "2048,1920,1792,1664,1536"})}}
    def plan_tiles(self, image, min_tile_size, max_tile_size, overlap_mode, overlap, prefer_larger_tiles, pad_mode, base_seed, seed_mode, tile_sizes_csv="2048,1920,1792,1664,1536", lora_aspect_ratio="none"):
        image = _ensure_bhwc(image); batch, H, W, _ = image.shape
        if batch != 1: raise ValueError("DB9TilePlanV2 expects a single image batch.")
        candidates = _parse_tile_sizes(tile_sizes_csv, min_tile_size, max_tile_size); best = None
        for tile_size in candidates:
            ov = _auto_overlap(tile_size) if overlap_mode == "auto" else overlap
            if ov >= tile_size: continue
            info = _score_candidate(W, H, tile_size, ov, prefer_larger_tiles)
            if best is None or info["score"] < best["score"]: best = info
        tile_size = best["tile_size"]; ov = best["overlap"]; stride = best["stride"]; cols = best["cols"]; rows = best["rows"]
        tiles = []; idx = 0
        xs = [round(i * W / cols) for i in range(cols + 1)]
        ys = [round(i * H / rows) for i in range(rows + 1)]
        for row in range(rows):
            for col in range(cols):
                core_box = (xs[col], ys[row], xs[col + 1], ys[row + 1])
                tiles.append(_build_core_work_tile_meta(W, H, tile_size, ov, row, col, idx, base_seed, seed_mode, core_box=core_box))
                idx += 1
        _lora_ratio = _LORA_RATIOS.get(lora_aspect_ratio, 1.0)
        if abs(_lora_ratio - 1.0) > 0.01:
            tiles = [_adjust_tile_for_lora_ratio(tile, _lora_ratio, W, H) for tile in tiles]
        plan = {"version": CORE_WORK_TILE_SCHEMA, "orig_w": W, "orig_h": H, "image_width": W, "image_height": H, "tile_size": tile_size, "work_tile_size": tile_size + ov * 2, "overlap": ov, "stride": stride, "cols": cols, "rows": rows, "total_tiles": len(tiles), "pad_mode": pad_mode, "padding_mode": pad_mode, "seed_mode": seed_mode, "base_seed": int(base_seed), "lora_aspect_ratio": lora_aspect_ratio, "tiles": tiles}
        dbg = f"DB9 CoreWorkTilePlan: orig={W}x{H}, tile_size={tile_size}, work_tile_size={tile_size + ov * 2}, overlap={ov}, grid={cols}x{rows}, total={len(tiles)}, padding_mode={pad_mode}, schema={CORE_WORK_TILE_SCHEMA}"
        return (plan, len(tiles), tile_size, cols, rows, dbg)

class DB9TileBatchEmitterV2:
    RETURN_TYPES = ("IMAGE", "DB9_TILE_META_STACK", "STRING")
    RETURN_NAMES = ("tile_images", "tile_meta", "debug_info")
    FUNCTION = "emit_tiles"
    CATEGORY = "DB9/AIO"
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"image": ("IMAGE",), "tile_plan": ("DB9_TILE_PLAN",)}}
    def emit_tiles(self, image, tile_plan):
        image = _ensure_bhwc(image); tile_size = tile_plan["tile_size"]; pad_mode = tile_plan["pad_mode"]; images = []; meta = []
        for tile in tile_plan["tiles"]:
            if tile_plan.get("version") == CORE_WORK_TILE_SCHEMA:
                tile_img = _extract_core_work_tile(image, tile, tile_size, pad_mode)
            else:
                tile_img = _extract_tile_with_padding(image, tile, tile_size, pad_mode)
            images.append(tile_img[0]); meta.append(dict(tile))
        return (torch.stack(images, dim=0), meta, f"Emitted {len(images)} tiles.")

class DB9TileResultCollectorV2:
    RETURN_TYPES = ("DB9_TILE_IMAGE_STACK", "DB9_TILE_IMAGE_STACK", "DB9_TILE_DEBUG_STACK", "STRING")
    RETURN_NAMES = ("base_tiles", "highlight_tiles", "debug_stack", "debug_info")
    FUNCTION = "collect_results"
    CATEGORY = "DB9/AIO"
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"processed_tiles": ("IMAGE",), "tile_meta": ("DB9_TILE_META_STACK",), "extract_highlight": ("BOOLEAN", {"default": True}), "highlight_extract_blur": ("INT", {"default": 9, "min": 1, "max": 101, "step": 2}), "highlight_threshold": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}), "highlight_gain": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.01}), "soft_clamp_strength": ("FLOAT", {"default": 0.15, "min": 0.0, "max": 1.0, "step": 0.01}), "micro_contrast_strength": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 1.0, "step": 0.01})}}
    def collect_results(self, processed_tiles, tile_meta, extract_highlight, highlight_extract_blur, highlight_threshold, highlight_gain, soft_clamp_strength, micro_contrast_strength):
        processed_tiles = _ensure_bhwc(processed_tiles)
        if processed_tiles.shape[0] != len(tile_meta): raise ValueError(f"Tile count mismatch: processed={processed_tiles.shape[0]} meta={len(tile_meta)}")
        base_images, hi_images, debug_stack = [], [], []
        for i in range(processed_tiles.shape[0]):
            tile_img = processed_tiles[i:i+1]; base = _soft_clamp_image(tile_img, soft_clamp_strength); base = _micro_contrast(base, micro_contrast_strength)
            hi = _extract_highlight(base, blur_radius=highlight_extract_blur, threshold=highlight_threshold, gain=highlight_gain) if extract_highlight else torch.zeros_like(base)
            debug_stack.append(_tile_debug_metrics(base, hi, seed=tile_meta[i].get("seed", -1))); base_images.append(base[0]); hi_images.append(hi[0])
        return ({"images": torch.stack(base_images, dim=0), "meta": tile_meta}, {"images": torch.stack(hi_images, dim=0), "meta": tile_meta}, debug_stack, f"Collected {len(base_images)} tiles.")

class DB9HighlightPreserveCompositeCanny:
    RETURN_TYPES = ("IMAGE", "IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("base_composite", "highlight_composite", "final_image", "debug_info")
    FUNCTION = "composite"
    CATEGORY = "DB9/AIO"
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"base_tiles": ("DB9_TILE_IMAGE_STACK",), "highlight_tiles": ("DB9_TILE_IMAGE_STACK",), "tile_plan": ("DB9_TILE_PLAN",), "highlight_blend_mode": (["add", "screen"], {"default": "screen"}), "center_priority_strength": ("FLOAT", {"default": 0.95, "min": 0.0, "max": 2.0, "step": 0.01}), "canny_low_thresh": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 5.0, "step": 0.01}), "canny_high_thresh": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 5.0, "step": 0.01}), "border_edge_penalty": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.01}), "border_start": ("FLOAT", {"default": 0.12, "min": 0.0, "max": 0.95, "step": 0.01}), "highlight_amount": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 2.0, "step": 0.01}),
            "seam_feather_px": ("INT", {"default": 64, "min": 0, "max": 256, "step": 8})}}
    def composite(self, base_tiles, highlight_tiles, tile_plan, highlight_blend_mode, center_priority_strength, canny_low_thresh, canny_high_thresh, border_edge_penalty, border_start, highlight_amount, seam_feather_px=64):
        H = int(tile_plan.get("orig_h", tile_plan["image_height"])); W = int(tile_plan.get("orig_w", tile_plan["image_width"]))
        expected = int(tile_plan.get("total_tiles", len(tile_plan["tiles"])))
        actual = int(base_tiles["images"].shape[0])
        if actual != expected or int(highlight_tiles["images"].shape[0]) != expected:
            raise ValueError(f"DB9 composite tile count mismatch: got base={actual}, highlight={highlight_tiles['images'].shape[0]}, expected={expected}. Do not pass rerun subset into full Seam Finish. Merge subset first.")
        device = base_tiles["images"].device
        dtype = base_tiles["images"].dtype
        base_canvas = torch.zeros((H, W, 3), dtype=dtype, device=device); base_weights = torch.zeros((H, W, 3), dtype=dtype, device=device)
        hi_canvas = torch.zeros((H, W, 3), dtype=dtype, device=device); hi_weights = torch.zeros((H, W, 3), dtype=dtype, device=device)
        use_core_schema = tile_plan.get("version") == CORE_WORK_TILE_SCHEMA
        _cols = int(tile_plan.get("cols", 1)); _rows = int(tile_plan.get("rows", 1))
        for i, tile_meta in enumerate(tile_plan["tiles"]):
            base_tile = base_tiles["images"][i].float(); hi_tile = highlight_tiles["images"][i].float()
            if use_core_schema:
                if seam_feather_px > 0:
                    _accumulate_core_tile_feathered(base_canvas, base_weights, base_tile, tile_meta, seam_feather_px, _cols, _rows)
                    _accumulate_core_tile_feathered(hi_canvas, hi_weights, hi_tile, tile_meta, seam_feather_px, _cols, _rows)
                else:
                    _accumulate_core_tile(base_canvas, base_weights, base_tile, tile_meta)
                    _accumulate_core_tile(hi_canvas, hi_weights, hi_tile, tile_meta)
            else:
                base_mask = _canny_border_suppressed_mask(base_tile, center_strength=center_priority_strength, low_thresh=canny_low_thresh, high_thresh=canny_high_thresh, border_edge_penalty=border_edge_penalty, border_start=border_start)
                hi_mask = _canny_border_suppressed_mask(hi_tile, center_strength=center_priority_strength + 0.15, low_thresh=max(0.0, canny_low_thresh * 0.9), high_thresh=max(0.0, canny_high_thresh * 0.9), border_edge_penalty=min(1.0, border_edge_penalty + 0.05), border_start=border_start)
                _accumulate_tile(base_canvas, base_weights, base_tile, tile_meta, base_mask); _accumulate_tile(hi_canvas, hi_weights, hi_tile, tile_meta, hi_mask)
        base_comp = _safe_normalize(base_canvas, base_weights); hi_comp = _safe_normalize(hi_canvas, hi_weights)
        final = 1.0 - (1.0 - base_comp) * (1.0 - hi_comp * highlight_amount) if highlight_blend_mode == "screen" else base_comp + hi_comp * highlight_amount
        final = torch.clamp(final, 0.0, 1.0)
        if final.shape[0] != H or final.shape[1] != W:
            raise ValueError(f"DB9 composite final size mismatch: got {final.shape[1]}x{final.shape[0]}, expected {W}x{H}")
        mode = "core_only" if use_core_schema else "legacy_weighted"
        return (base_comp.unsqueeze(0), hi_comp.unsqueeze(0), final.unsqueeze(0), f"Composite: processed_tiles={actual}, expected_tiles={expected}, final={W}x{H}, paste_mode={mode}")

class DB9TileQAPriority:
    RETURN_TYPES = ("DB9_QA_REPORT", "STRING", "BOOLEAN")
    RETURN_NAMES = ("qa_report", "debug_info", "recommend_rerun")
    FUNCTION = "evaluate"
    CATEGORY = "DB9/AIO"
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"final_image": ("IMAGE",), "tile_plan": ("DB9_TILE_PLAN",), "base_tiles": ("DB9_TILE_IMAGE_STACK",), "ssim_threshold": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}), "l2_threshold": ("FLOAT", {"default": 0.12, "min": 0.0, "max": 10.0, "step": 0.01}), "ghost_threshold": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 10.0, "step": 0.01}), "severity_weight_ssim": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01}), "severity_weight_l2": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01}), "severity_weight_ghost": ("FLOAT", {"default": 1.25, "min": 0.0, "max": 10.0, "step": 0.01})}}
    def evaluate(self, final_image, tile_plan, base_tiles, ssim_threshold, l2_threshold, ghost_threshold, severity_weight_ssim, severity_weight_l2, severity_weight_ghost):
        images = base_tiles["images"]; overlap = int(tile_plan["overlap"]); cols = int(tile_plan["cols"]); rows = int(tile_plan["rows"])
        seam_px = max(8, min(64, overlap // 3))  # boundary-focused comparison zone
        use_core_schema = tile_plan.get("version") == CORE_WORK_TILE_SCHEMA
        metas = tile_plan["tiles"]
        pair_scores = []; failing = set()
        def index_of(row, col): return row * cols + col
        for row in range(rows):
            for col in range(cols):
                idx = index_of(row, col)
                if col + 1 < cols:
                    j = index_of(row, col + 1)
                    a = _core_region_from_tile(images[idx], metas[idx]) if use_core_schema else images[idx]
                    b = _core_region_from_tile(images[j], metas[j]) if use_core_schema else images[j]
                    ov = min(seam_px, a.shape[1], b.shape[1])
                    if ov > 0:
                        a_overlap = a[:, -ov:, :]; b_overlap = b[:, :ov, :]
                        ssim_v = _simple_ssim_proxy(a_overlap, b_overlap); l2_v = _simple_l2(a_overlap, b_overlap); ghost_v = _gradient_mismatch_score(a_overlap, b_overlap)
                        severity = max(0.0, ssim_threshold - ssim_v) * severity_weight_ssim + max(0.0, l2_v - l2_threshold) * severity_weight_l2 + max(0.0, ghost_v - ghost_threshold) * severity_weight_ghost
                        pair_scores.append({"tile_a": idx, "tile_b": j, "dir": "h", "ssim": ssim_v, "l2": l2_v, "ghost": ghost_v, "severity": severity})
                        if severity > 0: failing.update([idx, j])
                if row + 1 < rows:
                    j = index_of(row + 1, col)
                    a = _core_region_from_tile(images[idx], metas[idx]) if use_core_schema else images[idx]
                    b = _core_region_from_tile(images[j], metas[j]) if use_core_schema else images[j]
                    ov = min(seam_px, a.shape[0], b.shape[0])
                    if ov > 0:
                        a_overlap = a[-ov:, :, :]; b_overlap = b[:ov, :, :]
                        ssim_v = _simple_ssim_proxy(a_overlap, b_overlap); l2_v = _simple_l2(a_overlap, b_overlap); ghost_v = _gradient_mismatch_score(a_overlap, b_overlap)
                        severity = max(0.0, ssim_threshold - ssim_v) * severity_weight_ssim + max(0.0, l2_v - l2_threshold) * severity_weight_l2 + max(0.0, ghost_v - ghost_threshold) * severity_weight_ghost
                        pair_scores.append({"tile_a": idx, "tile_b": j, "dir": "v", "ssim": ssim_v, "l2": l2_v, "ghost": ghost_v, "severity": severity})
                        if severity > 0: failing.update([idx, j])
        pair_scores = sorted(pair_scores, key=lambda p: p["severity"], reverse=True)
        seam_score = 0.0 if not pair_scores else sum(max(0.0, 1.0 - p["ssim"]) for p in pair_scores) / len(pair_scores)
        ghost_score = 0.0 if not pair_scores else sum(p["ghost"] for p in pair_scores) / len(pair_scores)
        report = {"seam_score": float(seam_score), "ghost_score": float(ghost_score), "failing_tiles": sorted(list(failing)), "pair_scores": pair_scores, "recommend_rerun": len(failing) > 0}
        return (report, f"QA Priority: failing_pairs={sum(1 for p in pair_scores if p['severity'] > 0)}, failing_tiles={len(failing)}", len(failing) > 0)

class DB9TilePriorityRerunPlanner:
    RETURN_TYPES = ("BOOLEAN", "DB9_TILE_PLAN", "STRING", "STRING")
    RETURN_NAMES = ("should_continue", "rerun_plan", "rerun_indices", "debug_info")
    FUNCTION = "plan_rerun"
    CATEGORY = "DB9/AIO"
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"tile_plan": ("DB9_TILE_PLAN",), "qa_report": ("DB9_QA_REPORT",), "attempt": ("INT", {"default": 1, "min": 1, "max": 10}), "max_attempts": ("INT", {"default": 2, "min": 1, "max": 10}), "max_seam_pairs_to_rerun": ("INT", {"default": 3, "min": 1, "max": 100}), "expand_neighbors": ("BOOLEAN", {"default": True}), "rerun_seed_mode": (["same", "attempt_offset", "golden_jitter"], {"default": "attempt_offset"})}}
    def plan_rerun(self, tile_plan, qa_report, attempt, max_attempts, max_seam_pairs_to_rerun, expand_neighbors, rerun_seed_mode):
        pair_scores = qa_report.get("pair_scores", []); bad_pairs = [p for p in pair_scores if p.get("severity", 0.0) > 0.0]
        should_continue = len(bad_pairs) > 0 and attempt <= max_attempts
        new_plan = dict(tile_plan); new_tiles = [dict(t) for t in tile_plan["tiles"]]
        cols = int(tile_plan["cols"]); rows = int(tile_plan["rows"]); base_seed = int(tile_plan.get("base_seed", 0))
        orig_seed_mode = tile_plan.get("seed_mode", "fixed_with_grid_offset"); seed_mode = orig_seed_mode if rerun_seed_mode == "same" else rerun_seed_mode
        selected_pairs = bad_pairs[:max_seam_pairs_to_rerun]; rerun_set = set()
        for p in selected_pairs:
            rerun_set.add(int(p["tile_a"])); rerun_set.add(int(p["tile_b"]))
        if expand_neighbors:
            expanded = set(rerun_set)
            for idx in list(rerun_set):
                r = idx // cols; c = idx % cols
                for rr, cc in [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]:
                    if 0 <= rr < rows and 0 <= cc < cols: expanded.add(rr * cols + cc)
            rerun_set = expanded
        for t in new_tiles:
            idx = int(t["index"])
            if idx in rerun_set:
                t["rerun"] = True; t["attempt"] = int(attempt)
                if rerun_seed_mode != "same": t["seed"] = _make_tile_seed(base_seed, t["row"], t["col"], idx, seed_mode, attempt=attempt)
            else:
                t["rerun"] = False
        new_plan["tiles"] = new_tiles; new_plan["rerun_indices"] = sorted(list(rerun_set))
        rerun_indices = ",".join(str(i) for i in sorted(list(rerun_set)))
        return (should_continue, new_plan, rerun_indices, f"Priority rerun: seams={len(selected_pairs)}, tiles={len(rerun_set)}, attempt={attempt}/{max_attempts}")

class DB9TileBatchEmitterSubsetV2:
    RETURN_TYPES = ("IMAGE", "DB9_TILE_META_STACK", "STRING")
    RETURN_NAMES = ("tile_images", "tile_meta", "debug_info")
    FUNCTION = "emit_subset"
    CATEGORY = "DB9/AIO"
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"image": ("IMAGE",), "tile_plan": ("DB9_TILE_PLAN",)}}
    def emit_subset(self, image, tile_plan):
        image = _ensure_bhwc(image); tile_size = tile_plan["tile_size"]; pad_mode = tile_plan["pad_mode"]; images = []; meta = []
        for tile in tile_plan["tiles"]:
            if not tile.get("rerun", False): continue
            if tile_plan.get("version") == CORE_WORK_TILE_SCHEMA:
                tile_img = _extract_core_work_tile(image, tile, tile_size, pad_mode)
            else:
                tile_img = _extract_tile_with_padding(image, tile, tile_size, pad_mode)
            images.append(tile_img[0]); meta.append(dict(tile))
        if not images:
            empty_size = int(tile_plan.get("work_tile_size", tile_size))
            empty = torch.zeros((0, empty_size, empty_size, 3), dtype=image.dtype, device=image.device)
            return (empty, meta, "Subset emitter: 0 tiles.")
        return (torch.stack(images, dim=0), meta, f"Subset emitter: {len(images)} tiles.")

class DB9TileResultMergeV2:
    RETURN_TYPES = ("DB9_TILE_IMAGE_STACK", "DB9_TILE_IMAGE_STACK", "STRING")
    RETURN_NAMES = ("base_tiles", "highlight_tiles", "debug_info")
    FUNCTION = "merge_results"
    CATEGORY = "DB9/AIO"
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"full_base_tiles": ("DB9_TILE_IMAGE_STACK",), "full_highlight_tiles": ("DB9_TILE_IMAGE_STACK",), "rerun_base_tiles": ("DB9_TILE_IMAGE_STACK",), "rerun_highlight_tiles": ("DB9_TILE_IMAGE_STACK",)}}
    def merge_results(self, full_base_tiles, full_highlight_tiles, rerun_base_tiles, rerun_highlight_tiles):
        full_base = full_base_tiles["images"].clone(); full_hi = full_highlight_tiles["images"].clone(); full_meta = [dict(m) for m in full_base_tiles["meta"]]
        rerun_base = rerun_base_tiles["images"]; rerun_hi = rerun_highlight_tiles["images"]; rerun_meta = rerun_base_tiles["meta"]
        if len(rerun_meta) != rerun_base.shape[0] or len(rerun_meta) != rerun_hi.shape[0]: raise ValueError("Rerun merge count mismatch.")
        for i, meta in enumerate(rerun_meta):
            idx = int(meta["index"]); full_base[idx] = rerun_base[i]; full_hi[idx] = rerun_hi[i]; full_meta[idx] = dict(meta)
        return ({"images": full_base, "meta": full_meta}, {"images": full_hi, "meta": full_meta}, f"Merged {len(rerun_meta)} rerun tiles back into full stacks.")


def _safe_center_crop(img, crop_ratio=0.12):
    h, w, c = img.shape
    cy = int(h * crop_ratio)
    cx = int(w * crop_ratio)
    y0 = min(max(cy, 0), h - 1)
    y1 = max(min(h - cy, h), y0 + 1)
    x0 = min(max(cx, 0), w - 1)
    x1 = max(min(w - cx, w), x0 + 1)
    return img[y0:y1, x0:x1, :]

def _tile_mean_std(img, eps=1e-6, crop_ratio=0.12):
    crop = _safe_center_crop(img, crop_ratio=crop_ratio)
    mean = crop.mean(dim=(0, 1), keepdim=True)
    std = crop.std(dim=(0, 1), keepdim=True)
    std = torch.clamp(std, min=eps)
    return mean, std

def _match_tile_stats(img, target_mean, target_std, strength=0.65, max_luma_shift=0.08):
    mean, std = _tile_mean_std(img)
    matched = (img - mean) / std
    matched = matched * target_std + target_mean

    src_luma = 0.2126 * img[..., 0:1] + 0.7152 * img[..., 1:2] + 0.0722 * img[..., 2:3]
    dst_luma = 0.2126 * matched[..., 0:1] + 0.7152 * matched[..., 1:2] + 0.0722 * matched[..., 2:3]
    luma_delta = torch.clamp(dst_luma - src_luma, min=-max_luma_shift, max=max_luma_shift)
    matched = matched - (dst_luma - src_luma) + luma_delta

    out = img * (1.0 - strength) + matched * strength
    return torch.clamp(out, 0.0, 1.0)

class DB9TileColorNormalize:
    RETURN_TYPES = ("DB9_TILE_IMAGE_STACK", "STRING")
    RETURN_NAMES = ("base_tiles", "debug_info")
    FUNCTION = "normalize_tiles"
    CATEGORY = "DB9/AIO"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_tiles": ("DB9_TILE_IMAGE_STACK",),
                "strength": ("FLOAT", {"default": 0.65, "min": 0.0, "max": 1.0, "step": 0.01}),
                "crop_ratio": ("FLOAT", {"default": 0.12, "min": 0.0, "max": 0.45, "step": 0.01}),
                "max_luma_shift": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 0.25, "step": 0.01}),
            }
        }

    def normalize_tiles(self, base_tiles, strength, crop_ratio, max_luma_shift):
        imgs = base_tiles["images"]
        meta = base_tiles["meta"]

        if imgs.shape[0] == 0:
            return (base_tiles, "TileColorNormalize: empty stack")

        means = []
        stds = []
        for i in range(imgs.shape[0]):
            mean, std = _tile_mean_std(imgs[i], crop_ratio=crop_ratio)
            means.append(mean)
            stds.append(std)

        stacked_means = torch.stack(means, dim=0)
        stacked_stds  = torch.stack(stds,  dim=0)
        target_mean = stacked_means.median(dim=0).values
        target_std  = stacked_stds.median(dim=0).values

        out_imgs = []
        for i in range(imgs.shape[0]):
            fixed = _match_tile_stats(
                imgs[i],
                target_mean=target_mean,
                target_std=target_std,
                strength=strength,
                max_luma_shift=max_luma_shift,
            )
            out_imgs.append(fixed)

        out = {
            "images": torch.stack(out_imgs, dim=0),
            "meta": meta,
        }
        dbg = f"TileColorNormalize: tiles={imgs.shape[0]}, strength={strength:.2f}, crop={crop_ratio:.2f}, max_luma_shift={max_luma_shift:.2f}"
        return (out, dbg)


NODE_CLASS_MAPPINGS = {
    "DB9TilePlanV2": DB9TilePlanV2,
    "DB9TileBatchEmitterV2": DB9TileBatchEmitterV2,
    "DB9TileResultCollectorV2": DB9TileResultCollectorV2,
    "DB9HighlightPreserveCompositeCanny": DB9HighlightPreserveCompositeCanny,
    "DB9TileQAPriority": DB9TileQAPriority,
    "DB9TilePriorityRerunPlanner": DB9TilePriorityRerunPlanner,
    "DB9TileBatchEmitterSubsetV2": DB9TileBatchEmitterSubsetV2,
    "DB9TileResultMergeV2": DB9TileResultMergeV2,
    "DB9TileColorNormalize": DB9TileColorNormalize,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DB9TilePlanV2": "DB9 Tile Plan V2",
    "DB9TileBatchEmitterV2": "DB9 Tile Batch Emitter V2",
    "DB9TileResultCollectorV2": "DB9 Tile Result Collector V2",
    "DB9HighlightPreserveCompositeCanny": "DB9 Highlight Preserve Composite Canny",
    "DB9TileQAPriority": "DB9 Tile QA Priority",
    "DB9TilePriorityRerunPlanner": "DB9 Tile Priority Rerun Planner",
    "DB9TileBatchEmitterSubsetV2": "DB9 Tile Batch Emitter Subset V2",
    "DB9TileResultMergeV2": "DB9 Tile Result Merge V2",
    "DB9TileColorNormalize": "DB9 Tile Color Normalize",
}

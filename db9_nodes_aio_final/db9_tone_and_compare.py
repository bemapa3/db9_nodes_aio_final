"""
DB9 Tone Match & Compare - final merged extension nodes for DB9 Tiling AIO.

Adds 2 nodes:
- DB9ToneMatch: balance color, contrast, and tone between upscaled and original images
- DB9CompareAndSave: split compare + color editor + save

Final merged version:
- keeps save-to-disk logic
- keeps histogram / mean_std / lab_l_only
- adds shm_match
- adds compare_strip
- adds difference compare mode
"""

import os
import importlib
import math
from pathlib import Path

import torch
import torch.nn.functional as F
import numpy as np

def _resolve_output_dir():
    try:
        folder_paths = importlib.import_module("folder_paths")
        return folder_paths.get_output_directory()
    except Exception:
        return str(Path.cwd() / "output")


_COMFY_OUTPUT_DIR = _resolve_output_dir()


# ============================================================
# Helpers
# ============================================================

def _ensure_bhwc(image):
    if image.ndim != 4:
        raise ValueError(f"Expected IMAGE [B,H,W,C], got {tuple(image.shape)}")
    return image


def _resize_to(img_bhwc, target_h, target_w):
    x = img_bhwc.permute(0, 3, 1, 2)
    x = F.interpolate(x, size=(target_h, target_w), mode="bilinear", align_corners=False)
    return x.permute(0, 2, 3, 1)


def _match_size(a_bhwc, b_bhwc):
    if a_bhwc.shape[1] == b_bhwc.shape[1] and a_bhwc.shape[2] == b_bhwc.shape[2]:
        return a_bhwc, b_bhwc
    b2 = _resize_to(b_bhwc, a_bhwc.shape[1], a_bhwc.shape[2])
    return a_bhwc, b2


def _broadcast_batch(ref_bhwc, other_bhwc):
    if ref_bhwc.shape[0] == other_bhwc.shape[0]:
        return other_bhwc
    if other_bhwc.shape[0] == 1 and ref_bhwc.shape[0] > 1:
        return other_bhwc.repeat(ref_bhwc.shape[0], 1, 1, 1)
    return other_bhwc[:1].repeat(ref_bhwc.shape[0], 1, 1, 1)


def _rgb_to_luma(img):
    return 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]


def _safe_mean_std(x, eps=1e-6):
    mean = x.mean(dim=(1, 2), keepdim=True)
    std = x.std(dim=(1, 2), keepdim=True)
    std = torch.clamp(std, min=eps)
    return mean, std


# ============================================================
# Color space helpers
# ============================================================

def _rgb_to_lab_approx(img):
    """Approximate sRGB -> Lab. img: BHWC in [0,1]. Returns (L, a, b) each BHW."""
    lin = torch.where(img <= 0.04045, img / 12.92, ((img + 0.055) / 1.055) ** 2.4)
    r, g, b = lin[..., 0], lin[..., 1], lin[..., 2]
    X = r * 0.4124 + g * 0.3576 + b * 0.1805
    Y = r * 0.2126 + g * 0.7152 + b * 0.0722
    Z = r * 0.0193 + g * 0.1192 + b * 0.9505

    Xn, Yn, Zn = 0.95047, 1.0, 1.08883
    fx = torch.where(X / Xn > 0.008856, (X / Xn) ** (1 / 3), 7.787 * (X / Xn) + 16 / 116)
    fy = torch.where(Y / Yn > 0.008856, (Y / Yn) ** (1 / 3), 7.787 * (Y / Yn) + 16 / 116)
    fz = torch.where(Z / Zn > 0.008856, (Z / Zn) ** (1 / 3), 7.787 * (Z / Zn) + 16 / 116)
    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b_ch = 200.0 * (fy - fz)
    return L, a, b_ch


def _lab_to_rgb_approx(L, a, b_ch):
    """Approximate Lab -> sRGB. Returns BHWC in [0,1]."""
    Xn, Yn, Zn = 0.95047, 1.0, 1.08883
    fy = (L + 16.0) / 116.0
    fx = a / 500.0 + fy
    fz = fy - b_ch / 200.0

    def _f_inv(t):
        return torch.where(t ** 3 > 0.008856, t ** 3, (t - 16 / 116) / 7.787)

    X = Xn * _f_inv(fx)
    Y = Yn * _f_inv(fy)
    Z = Zn * _f_inv(fz)
    r = X * 3.2406 + Y * -1.5372 + Z * -0.4986
    g = X * -0.9689 + Y * 1.8758 + Z * 0.0415
    b = X * 0.0557 + Y * -0.2040 + Z * 1.0570

    def _g(c):
        return torch.where(c <= 0.0031308, 12.92 * c, 1.055 * torch.clamp(c, min=1e-8) ** (1 / 2.4) - 0.055)

    r = _g(r)
    g = _g(g)
    b = _g(b)
    out = torch.stack([r, g, b], dim=-1)
    return torch.clamp(out, 0.0, 1.0)


def _rgb_to_hsv(img):
    """img BHWC [0,1] -> H[0,1], S[0,1], V[0,1] as BHW tensors."""
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    mx, _ = img.max(dim=-1)
    mn, _ = img.min(dim=-1)
    diff = mx - mn
    v = mx
    s = torch.where(mx > 1e-8, diff / torch.clamp(mx, min=1e-8), torch.zeros_like(mx))

    rc = (mx - r) / torch.clamp(diff, min=1e-8)
    gc = (mx - g) / torch.clamp(diff, min=1e-8)
    bc = (mx - b) / torch.clamp(diff, min=1e-8)

    h = torch.zeros_like(mx)
    mask_r = (mx == r) & (diff > 1e-8)
    mask_g = (mx == g) & (diff > 1e-8) & (~mask_r)
    mask_b = (mx == b) & (diff > 1e-8) & (~mask_r) & (~mask_g)
    h = torch.where(mask_r, (bc - gc) / 6.0, h)
    h = torch.where(mask_g, (2.0 + rc - bc) / 6.0, h)
    h = torch.where(mask_b, (4.0 + gc - rc) / 6.0, h)
    h = h % 1.0
    return h, s, v


def _hsv_to_rgb(h, s, v):
    """H,S,V BHW [0,1] -> BHWC RGB [0,1]."""
    i = torch.floor(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i_mod = (i % 6).long()

    r = torch.zeros_like(v)
    g = torch.zeros_like(v)
    b = torch.zeros_like(v)
    for idx, (rr, gg, bb) in enumerate([(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]):
        mask = (i_mod == idx)
        r = torch.where(mask, rr, r)
        g = torch.where(mask, gg, g)
        b = torch.where(mask, bb, b)
    return torch.stack([r, g, b], dim=-1)


# ============================================================
# Tone match kernels
# ============================================================

def _histogram_match_channel(src, ref):
    """Histogram match 1 channel. src/ref are 2D tensors in [0,1]."""
    src_flat = src.detach().flatten().cpu().numpy()
    ref_flat = ref.detach().flatten().cpu().numpy()
    _, bin_idx, s_counts = np.unique(src_flat, return_inverse=True, return_counts=True)
    r_values, r_counts = np.unique(ref_flat, return_counts=True)
    s_quantiles = np.cumsum(s_counts).astype(np.float64) / src_flat.size
    r_quantiles = np.cumsum(r_counts).astype(np.float64) / ref_flat.size
    interp_values = np.interp(s_quantiles, r_quantiles, r_values)
    mapped = interp_values[bin_idx].reshape(src.shape)
    return torch.from_numpy(mapped).to(src.device).float()


def _histogram_match_rgb(upscaled, original):
    """Batch-safe RGB histogram match."""
    out = torch.zeros_like(upscaled)
    for b in range(upscaled.shape[0]):
        for c in range(3):
            out[b, ..., c] = _histogram_match_channel(upscaled[b, ..., c], original[b, ..., c])
    return torch.clamp(out, 0.0, 1.0)


def _mean_std_match(upscaled, original):
    out = upscaled.clone()
    for c in range(3):
        m_s = out[..., c].mean(dim=(1, 2), keepdim=True)
        s_s = out[..., c].std(dim=(1, 2), keepdim=True).clamp(min=1e-6)
        m_r = original[..., c].mean(dim=(1, 2), keepdim=True)
        s_r = original[..., c].std(dim=(1, 2), keepdim=True).clamp(min=1e-6)
        out[..., c] = (out[..., c] - m_s) / s_s * s_r + m_r
    return torch.clamp(out, 0.0, 1.0)


def _lab_l_match(upscaled, original):
    L_s, a_s, b_s = _rgb_to_lab_approx(upscaled)
    L_r, _, _ = _rgb_to_lab_approx(original)

    m_s = L_s.mean(dim=(1, 2), keepdim=True)
    sd_s = L_s.std(dim=(1, 2), keepdim=True).clamp(min=1e-6)
    m_r = L_r.mean(dim=(1, 2), keepdim=True)
    sd_r = L_r.std(dim=(1, 2), keepdim=True).clamp(min=1e-6)

    L_out = (L_s - m_s) / sd_s * sd_r + m_r
    return _lab_to_rgb_approx(L_out, a_s, b_s)


def _match_luma_only(upscaled, original, max_exposure_shift=0.10):
    src_l = _rgb_to_luma(original).unsqueeze(-1)
    tgt_l = _rgb_to_luma(upscaled).unsqueeze(-1)
    src_mean = src_l.mean(dim=(1, 2), keepdim=True)
    tgt_mean = tgt_l.mean(dim=(1, 2), keepdim=True)
    delta = torch.clamp(src_mean - tgt_mean, -max_exposure_shift, max_exposure_shift)
    return torch.clamp(upscaled + delta, 0.0, 1.0)


def _build_shm_masks(luma_bhw1, shadow_protect, midtone_bias, preserve_highlight):
    shadow = torch.clamp((0.5 - luma_bhw1) / 0.5, 0.0, 1.0) * shadow_protect
    highlight = torch.clamp((luma_bhw1 - 0.6) / 0.4, 0.0, 1.0) * preserve_highlight
    mid = 1.0 - torch.abs(luma_bhw1 - midtone_bias) / 0.5
    mid = torch.clamp(mid, 0.0, 1.0)
    return shadow, mid, highlight


def _shm_match(upscaled, original, preserve_contrast=0.85, preserve_highlight=0.90, shadow_protect=0.15, midtone_bias=0.55, max_exposure_shift=0.10):
    src_l = _rgb_to_luma(original).unsqueeze(-1)
    tgt_l = _rgb_to_luma(upscaled).unsqueeze(-1)

    delta = torch.clamp(
        src_l.mean(dim=(1, 2), keepdim=True) - tgt_l.mean(dim=(1, 2), keepdim=True),
        -max_exposure_shift,
        max_exposure_shift,
    )
    tgt_adj = upscaled + delta

    src_mean, src_std = _safe_mean_std(original)
    tgt_mean, tgt_std = _safe_mean_std(tgt_adj)

    matched = (tgt_adj - tgt_mean) / tgt_std
    matched = matched * src_std + src_mean

    matched = tgt_adj * preserve_contrast + matched * (1.0 - preserve_contrast)

    shadow_mask, mid_mask, hi_mask = _build_shm_masks(
        _rgb_to_luma(tgt_adj).unsqueeze(-1),
        shadow_protect,
        midtone_bias,
        preserve_highlight,
    )

    out = matched * (1.0 - hi_mask) + tgt_adj * hi_mask
    out = out * (1.0 - shadow_mask) + tgt_adj * shadow_mask
    out = out * (1.0 - mid_mask) + matched * mid_mask
    return torch.clamp(out, 0.0, 1.0)


def _apply_highlight_protect(result, upscaled, protect_strength):
    if protect_strength <= 0:
        return result
    luma_up = _rgb_to_luma(upscaled)
    mask = torch.clamp((luma_up - 0.75) / 0.25, 0.0, 1.0).unsqueeze(-1)
    mask = mask * protect_strength
    return result * (1.0 - mask) + upscaled * mask


def _make_compare_strip(original, upscaled, corrected):
    return torch.cat([original, upscaled, corrected], dim=2)


# ============================================================
# DB9ToneMatch
# ============================================================

class DB9ToneMatch:
    """
    Balance color, contrast, and tone between upscaled and original images.
    Final merged version:
    - histogram
    - mean_std
    - lab_l_only
    - shm_match
    """
    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("corrected_image", "compare_strip", "debug_info")
    FUNCTION = "tone_match"
    CATEGORY = "DB9/AIO"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "upscaled_image": ("IMAGE",),
                "original_image": ("IMAGE",),
                "match_mode": (["lab_l_only", "mean_std", "histogram", "shm_match", "luma_only"], {"default": "lab_l_only"}),
                "match_strength": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.01}),
                "preserve_detail": ("FLOAT", {"default": 0.30, "min": 0.0, "max": 1.0, "step": 0.01}),
                "highlight_protect": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.01}),
                "contrast_boost": ("FLOAT", {"default": 0.0, "min": -0.5, "max": 0.5, "step": 0.01}),
                "saturation_boost": ("FLOAT", {"default": 0.0, "min": -0.5, "max": 0.5, "step": 0.01}),
                "shadow_lift": ("FLOAT", {"default": 0.0, "min": -0.3, "max": 0.3, "step": 0.01}),
            },
            "optional": {
                "preserve_contrast": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.01}),
                "preserve_highlight": ("FLOAT", {"default": 0.90, "min": 0.0, "max": 1.0, "step": 0.01}),
                "midtone_bias": ("FLOAT", {"default": 0.55, "min": 0.0, "max": 1.0, "step": 0.01}),
                "max_exposure_shift": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 0.5, "step": 0.01}),
            }
        }

    def tone_match(
        self,
        upscaled_image,
        original_image,
        match_mode,
        match_strength,
        preserve_detail,
        highlight_protect,
        contrast_boost,
        saturation_boost,
        shadow_lift,
        preserve_contrast=0.85,
        preserve_highlight=0.90,
        midtone_bias=0.55,
        max_exposure_shift=0.10,
    ):
        upscaled = _ensure_bhwc(upscaled_image).float()
        original = _ensure_bhwc(original_image).float()

        upscaled, original = _match_size(upscaled, original)
        original = _broadcast_batch(upscaled, original)

        if match_mode == "histogram":
            matched = _histogram_match_rgb(upscaled, original)
        elif match_mode == "mean_std":
            matched = _mean_std_match(upscaled, original)
        elif match_mode == "lab_l_only":
            matched = _lab_l_match(upscaled, original)
        elif match_mode == "luma_only":
            matched = _match_luma_only(upscaled, original, max_exposure_shift=max_exposure_shift)
        else:  # shm_match
            matched = _shm_match(
                upscaled,
                original,
                preserve_contrast=preserve_contrast,
                preserve_highlight=preserve_highlight,
                shadow_protect=shadow_lift if shadow_lift > 0 else 0.15,
                midtone_bias=midtone_bias,
                max_exposure_shift=max_exposure_shift,
            )

        out = upscaled * (1.0 - match_strength) + matched * match_strength

        if preserve_detail > 0:
            x = upscaled.permute(0, 3, 1, 2)
            blurred = F.avg_pool2d(x, 5, stride=1, padding=2)
            detail = (x - blurred).permute(0, 2, 3, 1)
            out = out + detail * preserve_detail

        out = _apply_highlight_protect(out, upscaled, highlight_protect)

        if abs(contrast_boost) > 1e-6:
            out = (out - 0.5) * (1.0 + contrast_boost * 2.0) + 0.5

        if abs(shadow_lift) > 1e-6:
            luma = _rgb_to_luma(out).unsqueeze(-1)
            shadow_mask = torch.clamp(1.0 - luma / 0.5, 0.0, 1.0) ** 2
            out = out + shadow_lift * shadow_mask

        if abs(saturation_boost) > 1e-6:
            h, s, v = _rgb_to_hsv(torch.clamp(out, 0.0, 1.0))
            s = torch.clamp(s * (1.0 + saturation_boost * 2.0), 0.0, 1.0)
            out = _hsv_to_rgb(h, s, v)

        out = torch.clamp(out, 0.0, 1.0)
        compare_strip = _make_compare_strip(original, upscaled, out)

        dbg = (
            f"ToneMatch mode={match_mode} strength={match_strength:.2f} "
            f"preserve_detail={preserve_detail:.2f} highlight_protect={highlight_protect:.2f} "
            f"contrast={contrast_boost:+.2f} sat={saturation_boost:+.2f} shadow={shadow_lift:+.2f} "
            f"preserve_contrast={preserve_contrast:.2f} preserve_highlight={preserve_highlight:.2f}"
        )
        return (out, compare_strip, dbg)


# ============================================================
# Compare / editor / save helpers
# ============================================================

def _apply_exposure(img, ev):
    if abs(ev) < 1e-6:
        return img
    return torch.clamp(img * (2.0 ** ev), 0.0, 1.0)


def _apply_contrast(img, amount):
    if abs(amount) < 1e-6:
        return img
    x = (img - 0.5) * 2.0
    if amount < 0:
        # Reduce contrast by linearly compressing values toward mid gray
        factor = max(0.0, 1.0 + amount)
        return torch.clamp(x * factor * 0.5 + 0.5, 0.0, 1.0)

    curve = 1.0 + amount * 3.0
    denom = max(abs(math.tanh(curve)), 1e-6)
    curved = torch.tanh(x * curve) / denom
    return torch.clamp(curved * 0.5 + 0.5, 0.0, 1.0)


def _apply_highlights_shadows(img, highlights, shadows):
    if abs(highlights) < 1e-6 and abs(shadows) < 1e-6:
        return img
    luma = _rgb_to_luma(img).unsqueeze(-1)
    hi_mask = torch.clamp((luma - 0.5) / 0.5, 0.0, 1.0) ** 2
    sh_mask = torch.clamp((0.5 - luma) / 0.5, 0.0, 1.0) ** 2
    img = img + highlights * 0.5 * hi_mask + shadows * 0.5 * sh_mask
    return torch.clamp(img, 0.0, 1.0)


def _apply_whites_blacks(img, whites, blacks):
    if abs(whites) < 1e-6 and abs(blacks) < 1e-6:
        return img
    w_point = 1.0 - whites * 0.3
    b_point = -blacks * 0.3
    scaled = (img - b_point) / max(w_point - b_point, 1e-6)
    return torch.clamp(scaled, 0.0, 1.0)


def _apply_saturation(img, saturation, vibrance):
    if abs(saturation) < 1e-6 and abs(vibrance) < 1e-6:
        return img
    h, s, v = _rgb_to_hsv(img)
    s = s * (1.0 + saturation)
    if abs(vibrance) > 1e-6:
        vib_factor = (1.0 - s) * vibrance
        s = s + vib_factor
    s = torch.clamp(s, 0.0, 1.0)
    return _hsv_to_rgb(h, s, v)


def _apply_white_balance(img, temperature, tint):
    if abs(temperature) < 1e-6 and abs(tint) < 1e-6:
        return img
    out = img.clone()
    out[..., 0] = out[..., 0] + temperature * 0.1
    out[..., 2] = out[..., 2] - temperature * 0.1
    out[..., 1] = out[..., 1] - tint * 0.1
    return torch.clamp(out, 0.0, 1.0)


def _make_split_image(img_a, img_b, split_mode, split_pos, difference_gain=4.0):
    _, H, W, _ = img_a.shape

    if split_mode == "difference":
        return torch.clamp(torch.abs(img_a - img_b) * difference_gain, 0.0, 1.0)

    out = img_a.clone()
    if split_mode == "vertical":
        cut = int(W * split_pos)
        out[:, :, cut:, :] = img_b[:, :, cut:, :]
        if 0 <= cut < W:
            line_w = max(1, W // 500)
            out[:, :, max(0, cut - line_w):min(W, cut + line_w), :] = 1.0
    elif split_mode == "horizontal":
        cut = int(H * split_pos)
        out[:, cut:, :, :] = img_b[:, cut:, :, :]
        if 0 <= cut < H:
            line_h = max(1, H // 500)
            out[:, max(0, cut - line_h):min(H, cut + line_h), :, :] = 1.0
    elif split_mode == "grid_2x2":
        half_h, half_w = H // 2, W // 2
        out = img_a.clone()
        out[:, :half_h, half_w:, :] = img_b[:, :half_h, half_w:, :]
        out[:, half_h:, :half_w, :] = img_b[:, half_h:, :half_w, :]
    elif split_mode == "side_by_side":
        out = torch.cat([img_a, img_b], dim=2)
    return out


def _save_image_tensor(img_bhwc, output_dir, filename, fmt, jpeg_quality):
    from PIL import Image

    arr = (torch.clamp(img_bhwc[0], 0.0, 1.0).detach().cpu().numpy() * 255).astype(np.uint8)
    pil = Image.fromarray(arr)
    os.makedirs(output_dir, exist_ok=True)

    ext = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[fmt]
    i = 0
    while True:
        suffix = f"_{i:05d}" if i > 0 else ""
        path = os.path.join(output_dir, f"{filename}{suffix}.{ext}")
        if not os.path.exists(path):
            break
        i += 1

    if fmt == "JPEG":
        pil.save(path, quality=int(jpeg_quality), subsampling=0)
    elif fmt == "WEBP":
        pil.save(path, quality=int(jpeg_quality))
    else:
        pil.save(path, compress_level=4)

    return path


# ============================================================
# DB9CompareAndSave
# ============================================================

class DB9CompareAndSave:
    """
    Split compare (original vs upscaled) + inline color editor + save to disk.
    Final merged version:
    - keeps save-to-disk logic
    - adds difference mode
    """
    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("corrected_image", "compare_image", "debug_info")
    FUNCTION = "compare_and_save"
    CATEGORY = "DB9/AIO"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_a": ("IMAGE",),
                "image_b": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "DB9_Output"}),
                "split_mode": (["vertical", "horizontal", "grid_2x2", "side_by_side", "difference"], {"default": "vertical"}),
                "split_position": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "difference_gain": ("FLOAT", {"default": 4.0, "min": 1.0, "max": 16.0, "step": 0.1}),
                "exposure": ("FLOAT", {"default": 0.0, "min": -2.0, "max": 2.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "highlights": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "shadows": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "whites": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "blacks": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "vibrance": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "saturation": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "temperature": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "tint": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "save_corrected": ("BOOLEAN", {"default": True}),
                "save_compare": ("BOOLEAN", {"default": True}),
                "save_original": ("BOOLEAN", {"default": False}),
                "output_format": (["PNG", "JPEG", "WEBP"], {"default": "PNG"}),
                "jpeg_quality": ("INT", {"default": 95, "min": 1, "max": 100}),
            }
        }

    def compare_and_save(
        self,
        image_a,
        image_b,
        filename_prefix,
        split_mode,
        split_position,
        difference_gain,
        exposure,
        contrast,
        highlights,
        shadows,
        whites,
        blacks,
        vibrance,
        saturation,
        temperature,
        tint,
        save_corrected,
        save_compare,
        save_original,
        output_format,
        jpeg_quality,
    ):
        img_a = _ensure_bhwc(image_a).float()
        img_b = _ensure_bhwc(image_b).float()

        corrected = img_b
        corrected = _apply_exposure(corrected, exposure)
        corrected = _apply_whites_blacks(corrected, whites, blacks)
        corrected = _apply_highlights_shadows(corrected, highlights, shadows)
        corrected = _apply_contrast(corrected, contrast)
        corrected = _apply_saturation(corrected, saturation, vibrance)
        corrected = _apply_white_balance(corrected, temperature, tint)
        corrected = torch.clamp(corrected, 0.0, 1.0)

        corrected, a_resized = _match_size(corrected, img_a)
        a_resized = _broadcast_batch(corrected, a_resized)

        compare = _make_split_image(a_resized, corrected, split_mode, split_position, difference_gain=difference_gain)

        saved_paths = []
        out_dir = _COMFY_OUTPUT_DIR

        if save_corrected:
            p = _save_image_tensor(corrected, out_dir, f"{filename_prefix}_corrected", output_format, jpeg_quality)
            saved_paths.append(p)
        if save_compare:
            p = _save_image_tensor(compare, out_dir, f"{filename_prefix}_compare", output_format, jpeg_quality)
            saved_paths.append(p)
        if save_original:
            p = _save_image_tensor(a_resized, out_dir, f"{filename_prefix}_original", output_format, jpeg_quality)
            saved_paths.append(p)

        dbg = (
            f"CompareAndSave split={split_mode}@{split_position:.2f} diff_gain={difference_gain:.2f} | "
            f"EV={exposure:+.2f} C={contrast:+.2f} H={highlights:+.2f} S={shadows:+.2f} "
            f"W={whites:+.2f} B={blacks:+.2f} Vib={vibrance:+.2f} Sat={saturation:+.2f} "
            f"T={temperature:+.2f} Tint={tint:+.2f} | saved={len(saved_paths)} fmt={output_format}"
        )
        return (corrected, compare, dbg)


# ============================================================
# Registration
# ============================================================

NODE_CLASS_MAPPINGS = {
    "DB9ToneMatch": DB9ToneMatch,
    "DB9CompareAndSave": DB9CompareAndSave,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DB9ToneMatch": "DB9 Tone Match",
    "DB9CompareAndSave": "DB9 Compare And Save",
}

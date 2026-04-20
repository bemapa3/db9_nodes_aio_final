import io
import os
import time
import uuid
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image

try:
    import folder_paths

    OUTPUT_DIR = folder_paths.get_output_directory()
except Exception:
    OUTPUT_DIR = str(Path.cwd() / "output")

try:
    from server import PromptServer
    from aiohttp import web

    HAVE_SERVER = True
except Exception:
    PromptServer = None
    web = None
    HAVE_SERVER = False


LIVE_EDITOR_SESSIONS = {}
SESSION_TTL_SEC = 7200


def _now():
    return time.time()


def cleanup_sessions():
    now = _now()
    expired = [sid for sid, s in LIVE_EDITOR_SESSIONS.items() if now - s.get("updated_at", now) > SESSION_TTL_SEC]
    for sid in expired:
        LIVE_EDITOR_SESSIONS.pop(sid, None)


def _make_session_id():
    return uuid.uuid4().hex[:12]


def _default_params():
    return {
        "exposure": 0.0,
        "contrast": 0.0,
        "highlights": 0.0,
        "shadows": 0.0,
        "whites": 0.0,
        "blacks": 0.0,
        "vibrance": 0.0,
        "saturation": 0.0,
        "temperature": 0.0,
        "tint": 0.0,
        "red_balance": 0.0,
        "green_balance": 0.0,
        "blue_balance": 0.0,
        "curve_lift": 0.0,
        "curve_gamma": 1.0,
        "curve_gain": 1.0,
    }


def ensure_bhwc(img):
    if not isinstance(img, torch.Tensor) or img.ndim != 4:
        raise ValueError(f"Expected IMAGE [B,H,W,C], got {type(img)} {getattr(img, 'shape', None)}")
    return img.float()


def clamp01(x):
    return torch.clamp(x, 0.0, 1.0)


def resize_to(img_bhwc, target_h, target_w):
    x = img_bhwc.permute(0, 3, 1, 2)
    x = F.interpolate(x, size=(target_h, target_w), mode="bilinear", align_corners=False)
    return x.permute(0, 2, 3, 1)


def match_size(a_bhwc, b_bhwc):
    if a_bhwc.shape[1] == b_bhwc.shape[1] and a_bhwc.shape[2] == b_bhwc.shape[2]:
        return a_bhwc, b_bhwc
    return a_bhwc, resize_to(b_bhwc, a_bhwc.shape[1], a_bhwc.shape[2])


def broadcast_batch(ref_bhwc, other_bhwc):
    if ref_bhwc.shape[0] == other_bhwc.shape[0]:
        return other_bhwc
    if other_bhwc.shape[0] == 1 and ref_bhwc.shape[0] > 1:
        return other_bhwc.repeat(ref_bhwc.shape[0], 1, 1, 1)
    return other_bhwc[:1].repeat(ref_bhwc.shape[0], 1, 1, 1)


def rgb_to_luma(img):
    return 0.2126 * img[..., 0:1] + 0.7152 * img[..., 1:2] + 0.0722 * img[..., 2:3]


def rgb_to_hsv(img):
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
    return h % 1.0, s, v


def hsv_to_rgb(h, s, v):
    i = torch.floor(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i_mod = (i % 6).long()

    r = torch.zeros_like(v)
    g = torch.zeros_like(v)
    b = torch.zeros_like(v)

    vals = [
        (v, t, p),
        (q, v, p),
        (p, v, t),
        (p, q, v),
        (t, p, v),
        (v, p, q),
    ]

    for idx, (rr, gg, bb) in enumerate(vals):
        mask = i_mod == idx
        r = torch.where(mask, rr, r)
        g = torch.where(mask, gg, g)
        b = torch.where(mask, bb, b)

    return torch.stack([r, g, b], dim=-1)


def apply_exposure(img, ev):
    return clamp01(img * (2.0 ** ev)) if abs(ev) > 1e-8 else img


def apply_whites_blacks(img, whites, blacks):
    if abs(whites) < 1e-8 and abs(blacks) < 1e-8:
        return img
    w_point = 1.0 - whites * 0.3
    b_point = -blacks * 0.3
    return clamp01((img - b_point) / max(w_point - b_point, 1e-6))


def apply_highlights_shadows(img, highlights, shadows):
    if abs(highlights) < 1e-8 and abs(shadows) < 1e-8:
        return img
    luma = rgb_to_luma(img)
    hi_mask = torch.clamp((luma - 0.5) / 0.5, 0.0, 1.0) ** 2
    sh_mask = torch.clamp((0.5 - luma) / 0.5, 0.0, 1.0) ** 2
    return clamp01(img + highlights * 0.5 * hi_mask + shadows * 0.5 * sh_mask)


def apply_contrast(img, contrast):
    if abs(contrast) < 1e-8:
        return img
    return clamp01((img - 0.5) * (1.0 + contrast * 2.0) + 0.5)


def apply_curve(img, lift, gamma, gain):
    if abs(lift) < 1e-8 and abs(gamma - 1.0) < 1e-8 and abs(gain - 1.0) < 1e-8:
        return img
    x = clamp01(img + lift)
    x = torch.pow(torch.clamp(x, min=1e-6), 1.0 / max(gamma, 1e-6))
    return clamp01(x * gain)


def apply_temp_tint(img, temperature, tint):
    if abs(temperature) < 1e-8 and abs(tint) < 1e-8:
        return img
    out = img.clone()
    out[..., 0] += temperature * 0.1
    out[..., 2] -= temperature * 0.1
    out[..., 1] -= tint * 0.1
    return clamp01(out)


def apply_vibrance_saturation(img, vibrance, saturation):
    if abs(vibrance) < 1e-8 and abs(saturation) < 1e-8:
        return img
    h, s, v = rgb_to_hsv(img)
    s = s * (1.0 + saturation)
    s = s + (1.0 - s) * vibrance
    return hsv_to_rgb(h, torch.clamp(s, 0.0, 1.0), v)


def apply_rgb_balance(img, r, g, b):
    if abs(r) < 1e-8 and abs(g) < 1e-8 and abs(b) < 1e-8:
        return img
    out = img.clone()
    out[..., 0] += r * 0.1
    out[..., 1] += g * 0.1
    out[..., 2] += b * 0.1
    return clamp01(out)


def apply_all(image, params):
    x = image.clone()
    x = apply_exposure(x, float(params.get("exposure", 0.0)))
    x = apply_whites_blacks(x, float(params.get("whites", 0.0)), float(params.get("blacks", 0.0)))
    x = apply_highlights_shadows(x, float(params.get("highlights", 0.0)), float(params.get("shadows", 0.0)))
    x = apply_contrast(x, float(params.get("contrast", 0.0)))
    x = apply_curve(
        x,
        float(params.get("curve_lift", 0.0)),
        float(params.get("curve_gamma", 1.0)),
        float(params.get("curve_gain", 1.0)),
    )
    x = apply_temp_tint(x, float(params.get("temperature", 0.0)), float(params.get("tint", 0.0)))
    x = apply_vibrance_saturation(x, float(params.get("vibrance", 0.0)), float(params.get("saturation", 0.0)))
    x = apply_rgb_balance(
        x,
        float(params.get("red_balance", 0.0)),
        float(params.get("green_balance", 0.0)),
        float(params.get("blue_balance", 0.0)),
    )
    return clamp01(x)


def make_compare_image(img_a, img_b, mode="vertical", split_position=0.5, difference_gain=4.0):
    img_a, img_b = match_size(img_a, img_b)
    img_b = broadcast_batch(img_a, img_b)
    _, H, W, _ = img_a.shape

    if mode == "original":
        return img_a
    if mode == "edited":
        return img_b
    if mode == "difference":
        return clamp01(torch.abs(img_a - img_b) * difference_gain)
    if mode == "side_by_side":
        return torch.cat([img_a, img_b], dim=2)

    out = img_a.clone()

    if mode == "horizontal":
        cut = int(H * split_position)
        out[:, cut:, :, :] = img_b[:, cut:, :, :]
        if 0 <= cut < H:
            line_h = max(1, H // 500)
            out[:, max(0, cut - line_h):min(H, cut + line_h), :, :] = 1.0
    else:
        cut = int(W * split_position)
        out[:, :, cut:, :] = img_b[:, :, cut:, :]
        if 0 <= cut < W:
            line_w = max(1, W // 500)
            out[:, :, max(0, cut - line_w):min(W, cut + line_w), :] = 1.0

    return out


def tensor_to_png_bytes(img_bhwc):
    arr = (clamp01(img_bhwc[0]).detach().cpu().numpy() * 255).astype("uint8")
    bio = io.BytesIO()
    Image.fromarray(arr).save(bio, format="PNG")
    return bio.getvalue()


def save_tensor(img_bhwc, filename_prefix, save_mode, output_format, jpeg_quality):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ext = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[output_format]

    if save_mode == "overwrite":
        path = os.path.join(OUTPUT_DIR, f"{filename_prefix}.{ext}")
    else:
        i = 1
        while True:
            path = os.path.join(OUTPUT_DIR, f"{filename_prefix}_{i:04d}.{ext}")
            if not os.path.exists(path):
                break
            i += 1

    arr = (clamp01(img_bhwc[0]).detach().cpu().numpy() * 255).astype("uint8")
    pil = Image.fromarray(arr)

    if output_format == "JPEG":
        pil.save(path, quality=int(jpeg_quality), subsampling=0)
    elif output_format == "WEBP":
        pil.save(path, quality=int(jpeg_quality))
    else:
        pil.save(path, compress_level=4)

    return path


class DB9LiveToneEditor:
    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image_out", "session_id", "debug_info")
    FUNCTION = "open_live_editor"
    CATEGORY = "DB9/AIO"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "DB9_Live_Edit"}),
            },
            "optional": {
                "reference_image": ("IMAGE",),
                "enable_live_editor": ("BOOLEAN", {"default": True}),
                "autosave": ("BOOLEAN", {"default": False}),
                "autosave_delay_ms": ("INT", {"default": 700, "min": 100, "max": 5000}),
                "save_mode": (["versioned", "overwrite"], {"default": "versioned"}),
                "output_format": (["PNG", "JPEG", "WEBP"], {"default": "PNG"}),
                "jpeg_quality": ("INT", {"default": 95, "min": 1, "max": 100}),
            },
        }

    def open_live_editor(
        self,
        image,
        filename_prefix,
        reference_image=None,
        enable_live_editor=True,
        autosave=False,
        autosave_delay_ms=700,
        save_mode="versioned",
        output_format="PNG",
        jpeg_quality=95,
    ):
        cleanup_sessions()

        image = ensure_bhwc(image)
        ref = image if reference_image is None else ensure_bhwc(reference_image)

        image, ref = match_size(image, ref)
        ref = broadcast_batch(image, ref)

        session_id = _make_session_id()
        LIVE_EDITOR_SESSIONS[session_id] = {
            "original_image": image.clone(),
            "reference_image": ref.clone(),
            "current_image": image.clone(),
            "compare_image": image.clone(),
            "last_params": _default_params(),
            "filename_prefix": filename_prefix,
            "autosave": bool(autosave),
            "autosave_delay_ms": int(autosave_delay_ms),
            "save_mode": save_mode,
            "output_format": output_format,
            "jpeg_quality": int(jpeg_quality),
            "last_saved_path": None,
            "created_at": _now(),
            "updated_at": _now(),
        }

        return image, session_id, f"DB9 live editor session={session_id} enabled={bool(enable_live_editor)}"


if HAVE_SERVER and getattr(PromptServer, "instance", None) is not None:
    routes = PromptServer.instance.routes

    @routes.post("/db9/live_editor/session/init")
    async def db9_live_init(request):
        cleanup_sessions()
        data = await request.json()
        session_id = data.get("session_id")
        sess = LIVE_EDITOR_SESSIONS.get(session_id)
        if not sess:
            return web.json_response({"ok": False, "error": "session_not_found"}, status=404)

        img = sess["current_image"]
        return web.json_response(
            {
                "ok": True,
                "session_id": session_id,
                "width": int(img.shape[2]),
                "height": int(img.shape[1]),
                "has_reference": True,
            }
        )

    @routes.get("/db9/live_editor/session/{session_id}/image")
    async def db9_live_get_image(request):
        cleanup_sessions()
        session_id = request.match_info["session_id"]
        kind = request.query.get("kind", "current")
        sess = LIVE_EDITOR_SESSIONS.get(session_id)
        if not sess:
            return web.Response(status=404, text="session_not_found")

        if kind == "original":
            img = sess["original_image"]
        elif kind == "reference":
            img = sess["reference_image"]
        elif kind == "compare":
            img = sess.get("compare_image", sess["current_image"])
        else:
            img = sess["current_image"]

        return web.Response(body=tensor_to_png_bytes(img), content_type="image/png")

    @routes.post("/db9/live_editor/session/{session_id}/apply")
    async def db9_live_apply(request):
        cleanup_sessions()
        session_id = request.match_info["session_id"]
        sess = LIVE_EDITOR_SESSIONS.get(session_id)
        if not sess:
            return web.json_response({"ok": False, "error": "session_not_found"}, status=404)

        data = await request.json()
        params = data.get("params", {})
        merged = sess["last_params"].copy()
        merged.update(params)
        sess["last_params"] = merged
        sess["current_image"] = apply_all(sess["original_image"], merged)
        sess["updated_at"] = _now()

        return web.json_response(
            {
                "ok": True,
                "preview_url": f"/db9/live_editor/session/{session_id}/image?kind=current&ts={int(_now() * 1000)}",
                "debug_info": "applied",
            }
        )

    @routes.post("/db9/live_editor/session/{session_id}/compare")
    async def db9_live_compare(request):
        cleanup_sessions()
        session_id = request.match_info["session_id"]
        sess = LIVE_EDITOR_SESSIONS.get(session_id)
        if not sess:
            return web.json_response({"ok": False, "error": "session_not_found"}, status=404)

        data = await request.json()
        mode = data.get("mode", "vertical")
        split_position = float(data.get("split_position", 0.5))
        difference_gain = float(data.get("difference_gain", 4.0))

        sess["compare_image"] = make_compare_image(
            sess["reference_image"],
            sess["current_image"],
            mode=mode,
            split_position=split_position,
            difference_gain=difference_gain,
        )
        sess["updated_at"] = _now()

        return web.json_response(
            {
                "ok": True,
                "compare_url": f"/db9/live_editor/session/{session_id}/image?kind=compare&ts={int(_now() * 1000)}",
            }
        )

    @routes.post("/db9/live_editor/session/{session_id}/save")
    async def db9_live_save(request):
        cleanup_sessions()
        session_id = request.match_info["session_id"]
        sess = LIVE_EDITOR_SESSIONS.get(session_id)
        if not sess:
            return web.json_response({"ok": False, "error": "session_not_found"}, status=404)

        data = await request.json()
        prefix = data.get("filename_prefix", sess["filename_prefix"])
        save_mode = data.get("save_mode", sess["save_mode"])
        output_format = data.get("output_format", sess["output_format"])
        jpeg_quality = int(data.get("jpeg_quality", sess["jpeg_quality"]))

        path = save_tensor(sess["current_image"], prefix, save_mode, output_format, jpeg_quality)
        sess["last_saved_path"] = path
        sess["updated_at"] = _now()

        return web.json_response({"ok": True, "saved_path": path})

    @routes.post("/db9/live_editor/session/{session_id}/autosave")
    async def db9_live_autosave(request):
        cleanup_sessions()
        session_id = request.match_info["session_id"]
        sess = LIVE_EDITOR_SESSIONS.get(session_id)
        if not sess:
            return web.json_response({"ok": False, "error": "session_not_found"}, status=404)

        path = save_tensor(
            sess["current_image"],
            sess["filename_prefix"],
            sess["save_mode"],
            sess["output_format"],
            sess["jpeg_quality"],
        )
        sess["last_saved_path"] = path
        sess["updated_at"] = _now()

        return web.json_response({"ok": True, "saved_path": path})

    @routes.post("/db9/live_editor/session/{session_id}/reset")
    async def db9_live_reset(request):
        cleanup_sessions()
        session_id = request.match_info["session_id"]
        sess = LIVE_EDITOR_SESSIONS.get(session_id)
        if not sess:
            return web.json_response({"ok": False, "error": "session_not_found"}, status=404)

        sess["last_params"] = _default_params()
        sess["current_image"] = sess["original_image"].clone()
        sess["compare_image"] = sess["original_image"].clone()
        sess["updated_at"] = _now()

        return web.json_response(
            {
                "ok": True,
                "preview_url": f"/db9/live_editor/session/{session_id}/image?kind=current&ts={int(_now() * 1000)}",
            }
        )

    @routes.post("/db9/live_editor/session/{session_id}/close")
    async def db9_live_close(request):
        session_id = request.match_info["session_id"]
        LIVE_EDITOR_SESSIONS.pop(session_id, None)
        return web.json_response({"ok": True})


NODE_CLASS_MAPPINGS = {
    "DB9LiveToneEditor": DB9LiveToneEditor,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "DB9LiveToneEditor": "DB9 Live Tone Editor",
}

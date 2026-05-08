from .db9_tiling_aio import (
    DB9TilePlanV2, DB9TileBatchEmitterV2, DB9TileResultCollectorV2,
    DB9TileColorNormalize, DB9HighlightPreserveCompositeCanny, DB9TileQAPriority,
    DB9TilePriorityRerunPlanner, DB9TileBatchEmitterSubsetV2, DB9TileResultMergeV2,
)

class DB9TilePrep:
    RETURN_TYPES = ("IMAGE", "DB9_TILE_META_STACK", "DB9_TILE_PLAN", "INT", "INT", "INT", "INT", "STRING")
    RETURN_NAMES = ("tile_images", "tile_meta", "tile_plan", "total_tiles", "chosen_tile_size", "cols", "rows", "debug_info")
    FUNCTION = "prepare_tiles"
    CATEGORY = "DB9"
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "min_tile_size": ("INT", {"default": 1536, "min": 512, "max": 4096, "step": 64}),
            "max_tile_size": ("INT", {"default": 2048, "min": 512, "max": 4096, "step": 64}),
            "overlap_mode": (["auto", "manual"], {"default": "auto"}),
            "overlap": ("INT", {"default": 224, "min": 0, "max": 1024, "step": 8}),
            "prefer_larger_tiles": ("BOOLEAN", {"default": True}),
            "pad_mode": (["reflect", "replicate", "constant"], {"default": "replicate"}),
            "base_seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            "seed_mode": (["fixed", "fixed_with_grid_offset", "row", "col", "golden_jitter"], {"default": "fixed_with_grid_offset"}),
        }, "optional": {"tile_sizes_csv": ("STRING", {"default": "2048,1920,1792,1664,1536"})}}
    def prepare_tiles(self, image, min_tile_size, max_tile_size, overlap_mode, overlap, prefer_larger_tiles, pad_mode, base_seed, seed_mode, tile_sizes_csv="2048,1920,1792,1664,1536"):
        planner = DB9TilePlanV2()
        emitter = DB9TileBatchEmitterV2()
        plan, total_tiles, chosen_tile_size, cols, rows, dbg1 = planner.plan_tiles(
            image, min_tile_size, max_tile_size, overlap_mode, overlap, prefer_larger_tiles, pad_mode, base_seed, seed_mode, tile_sizes_csv
        )
        tile_images, tile_meta, dbg2 = emitter.emit_tiles(image, plan)
        return (tile_images, tile_meta, plan, total_tiles, chosen_tile_size, cols, rows, f"{dbg1} | {dbg2}")

class DB9SeamFinish:
    RETURN_TYPES = ("IMAGE", "DB9_TILE_IMAGE_STACK", "DB9_TILE_IMAGE_STACK", "DB9_QA_REPORT", "BOOLEAN", "IMAGE", "IMAGE", "DB9_TILE_DEBUG_STACK", "STRING")
    RETURN_NAMES = ("final_image", "base_tiles", "highlight_tiles", "qa_report", "recommend_rerun", "base_composite", "highlight_composite", "debug_stack", "debug_info")
    FUNCTION = "finish_seams"
    CATEGORY = "DB9"
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "processed_tiles": ("IMAGE",),
            "tile_meta": ("DB9_TILE_META_STACK",),
            "tile_plan": ("DB9_TILE_PLAN",),
            "extract_highlight": ("BOOLEAN", {"default": True}),
            "highlight_extract_blur": ("INT", {"default": 9, "min": 1, "max": 101, "step": 2}),
            "highlight_threshold": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}),
            "highlight_gain": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.01}),
            "soft_clamp_strength": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 1.0, "step": 0.01}),
            "micro_contrast_strength": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 1.0, "step": 0.01}),
            "normalize_strength": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 1.0, "step": 0.01}),
            "normalize_crop_ratio": ("FLOAT", {"default": 0.12, "min": 0.0, "max": 0.45, "step": 0.01}),
            "normalize_max_luma_shift": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 0.25, "step": 0.01}),
            "highlight_blend_mode": (["add", "screen"], {"default": "screen"}),
            "center_priority_strength": ("FLOAT", {"default": 0.90, "min": 0.0, "max": 2.0, "step": 0.01}),
            "canny_low_thresh": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 5.0, "step": 0.01}),
            "canny_high_thresh": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 5.0, "step": 0.01}),
            "border_edge_penalty": ("FLOAT", {"default": 0.90, "min": 0.0, "max": 1.0, "step": 0.01}),
            "border_start": ("FLOAT", {"default": 0.12, "min": 0.0, "max": 0.95, "step": 0.01}),
            "highlight_amount": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 2.0, "step": 0.01}),
            "seam_feather_px": ("INT", {"default": 64, "min": 0, "max": 256, "step": 8}),
            "ssim_threshold": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}),
            "l2_threshold": ("FLOAT", {"default": 0.12, "min": 0.0, "max": 10.0, "step": 0.01}),
            "ghost_threshold": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 10.0, "step": 0.01}),
            "severity_weight_ssim": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01}),
            "severity_weight_l2": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01}),
            "severity_weight_ghost": ("FLOAT", {"default": 1.25, "min": 0.0, "max": 10.0, "step": 0.01}),
        }}
    def finish_seams(self, processed_tiles, tile_meta, tile_plan, extract_highlight, highlight_extract_blur, highlight_threshold, highlight_gain, soft_clamp_strength, micro_contrast_strength, normalize_strength, normalize_crop_ratio, normalize_max_luma_shift, highlight_blend_mode, center_priority_strength, canny_low_thresh, canny_high_thresh, border_edge_penalty, border_start, highlight_amount, seam_feather_px, ssim_threshold, l2_threshold, ghost_threshold, severity_weight_ssim, severity_weight_l2, severity_weight_ghost):
        collector = DB9TileResultCollectorV2()
        normalizer = DB9TileColorNormalize()
        composite = DB9HighlightPreserveCompositeCanny()
        qa = DB9TileQAPriority()
        base_tiles, highlight_tiles, debug_stack, dbg_collect = collector.collect_results(processed_tiles, tile_meta, extract_highlight, highlight_extract_blur, highlight_threshold, highlight_gain, soft_clamp_strength, micro_contrast_strength)
        norm_base_tiles, dbg_norm = normalizer.normalize_tiles(base_tiles, normalize_strength, normalize_crop_ratio, normalize_max_luma_shift)
        base_composite, highlight_composite, final_image, dbg_comp = composite.composite(norm_base_tiles, highlight_tiles, tile_plan, highlight_blend_mode, center_priority_strength, canny_low_thresh, canny_high_thresh, border_edge_penalty, border_start, highlight_amount, seam_feather_px)
        qa_report, dbg_qa, recommend_rerun = qa.evaluate(final_image, tile_plan, norm_base_tiles, ssim_threshold, l2_threshold, ghost_threshold, severity_weight_ssim, severity_weight_l2, severity_weight_ghost)
        return (final_image, norm_base_tiles, highlight_tiles, qa_report, recommend_rerun, base_composite, highlight_composite, debug_stack, " | ".join([dbg_collect, dbg_norm, dbg_comp, dbg_qa]))

class DB9PriorityRerun:
    RETURN_TYPES = ("BOOLEAN", "DB9_TILE_PLAN", "STRING", "IMAGE", "DB9_TILE_META_STACK", "DB9_TILE_IMAGE_STACK", "DB9_TILE_IMAGE_STACK", "STRING")
    RETURN_NAMES = ("should_continue", "rerun_plan", "rerun_indices", "subset_tile_images", "subset_tile_meta", "merged_base_tiles", "merged_highlight_tiles", "debug_info")
    FUNCTION = "priority_rerun"
    CATEGORY = "DB9"
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "source_image": ("IMAGE",),
            "tile_plan": ("DB9_TILE_PLAN",),
            "qa_report": ("DB9_QA_REPORT",),
            "full_base_tiles": ("DB9_TILE_IMAGE_STACK",),
            "full_highlight_tiles": ("DB9_TILE_IMAGE_STACK",),
            "attempt": ("INT", {"default": 1, "min": 1, "max": 10}),
            "max_attempts": ("INT", {"default": 2, "min": 1, "max": 10}),
            "max_seam_pairs_to_rerun": ("INT", {"default": 3, "min": 1, "max": 100}),
            "expand_neighbors": ("BOOLEAN", {"default": True}),
            "rerun_seed_mode": (["same", "attempt_offset", "golden_jitter"], {"default": "attempt_offset"}),
        }, "optional": {
            "rerun_base_tiles": ("DB9_TILE_IMAGE_STACK",),
            "rerun_highlight_tiles": ("DB9_TILE_IMAGE_STACK",),
        }}
    def priority_rerun(self, source_image, tile_plan, qa_report, full_base_tiles, full_highlight_tiles, attempt, max_attempts, max_seam_pairs_to_rerun, expand_neighbors, rerun_seed_mode, rerun_base_tiles=None, rerun_highlight_tiles=None):
        planner = DB9TilePriorityRerunPlanner()
        emitter = DB9TileBatchEmitterSubsetV2()
        merger = DB9TileResultMergeV2()
        should_continue, rerun_plan, rerun_indices, dbg_plan = planner.plan_rerun(tile_plan, qa_report, attempt, max_attempts, max_seam_pairs_to_rerun, expand_neighbors, rerun_seed_mode)
        subset_tile_images, subset_tile_meta, dbg_emit = emitter.emit_subset(source_image, rerun_plan)
        if rerun_base_tiles is not None and rerun_highlight_tiles is not None:
            merged_base_tiles, merged_highlight_tiles, dbg_merge = merger.merge_results(full_base_tiles, full_highlight_tiles, rerun_base_tiles, rerun_highlight_tiles)
        else:
            merged_base_tiles, merged_highlight_tiles, dbg_merge = full_base_tiles, full_highlight_tiles, "Priority rerun: merge skipped, rerun stacks not provided."
        return (should_continue, rerun_plan, rerun_indices, subset_tile_images, subset_tile_meta, merged_base_tiles, merged_highlight_tiles, " | ".join([dbg_plan, dbg_emit, dbg_merge]))


# ─────────────────────────────────────────────────────────────────────────────
# V2 Context-Aware Nodes
# Simplifies wiring: TilingContext bundles tile_plan + tile_meta + settings
# into a single DB9_TILING_CONTEXT wire that flows alongside the KSampler chain.
#
# Workflow (V2):
#   Image → DB9TilingContext → tile_images → [VAE Encode → KSampler → VAE Decode]
#                            → tiling_context ──────────────────────────────────→ DB9SeamFinishV2
# ─────────────────────────────────────────────────────────────────────────────

class DB9TilingContext:
    """
    Single entry-point node. Combines tile planning + emission into one node.
    Outputs tile_images (batch) for the KSampler chain, and tiling_context
    (a bundled dict) that carries tile_plan, tile_meta, and seam settings in
    one wire — no extra wires needed downstream.
    Compatible with any KSampler or KSamplerAdvanced node.
    """
    RETURN_TYPES = ("IMAGE", "DB9_TILING_CONTEXT", "INT", "STRING")
    RETURN_NAMES = ("tile_images", "tiling_context", "total_tiles", "debug_info")
    FUNCTION = "create_context"
    CATEGORY = "DB9"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "min_tile_size": ("INT", {"default": 1536, "min": 512, "max": 4096, "step": 64}),
            "max_tile_size": ("INT", {"default": 2048, "min": 512, "max": 4096, "step": 64}),
            "overlap_mode": (["auto", "manual"], {"default": "auto"}),
            "overlap": ("INT", {"default": 224, "min": 0, "max": 1024, "step": 8}),
            "prefer_larger_tiles": ("BOOLEAN", {"default": True}),
            "pad_mode": (["reflect", "replicate", "constant"], {"default": "replicate"}),
            "base_seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            "seed_mode": (["fixed", "fixed_with_grid_offset", "row", "col", "golden_jitter"], {"default": "fixed_with_grid_offset"}),
            "lora_aspect_ratio": (["none", "1:1", "4:3", "3:2", "16:9", "2:1", "9:16", "2:3", "3:4"], {"default": "none"}),
            "seam_feather_px": ("INT", {"default": 64, "min": 0, "max": 256, "step": 8}),
        }, "optional": {"tile_sizes_csv": ("STRING", {"default": "2048,1920,1792,1664,1536"})}}

    def create_context(self, image, min_tile_size, max_tile_size, overlap_mode, overlap,
                       prefer_larger_tiles, pad_mode, base_seed, seed_mode,
                       lora_aspect_ratio, seam_feather_px,
                       tile_sizes_csv="2048,1920,1792,1664,1536"):
        planner = DB9TilePlanV2()
        emitter = DB9TileBatchEmitterV2()
        plan, total_tiles, chosen_tile_size, cols, rows, dbg1 = planner.plan_tiles(
            image, min_tile_size, max_tile_size, overlap_mode, overlap,
            prefer_larger_tiles, pad_mode, base_seed, seed_mode,
            tile_sizes_csv, lora_aspect_ratio,
        )
        tile_images, tile_meta, dbg2 = emitter.emit_tiles(image, plan)
        context = {
            "tile_plan": plan,
            "tile_meta": tile_meta,
            "seam_feather_px": int(seam_feather_px),
            "total_tiles": int(total_tiles),
            "cols": int(cols),
            "rows": int(rows),
        }
        return (tile_images, context, total_tiles, f"{dbg1} | {dbg2}")


class DB9SeamFinishV2:
    """
    Context-aware Seam Finish. Takes tiling_context (from DB9TilingContext) instead of
    separate tile_meta + tile_plan wires. seam_feather_px is read from context automatically.
    All quality/blend params remain fully adjustable by the user.
    """
    RETURN_TYPES = ("IMAGE", "DB9_QA_REPORT", "BOOLEAN", "IMAGE", "IMAGE",
                    "DB9_TILE_IMAGE_STACK", "DB9_TILE_IMAGE_STACK", "STRING")
    RETURN_NAMES = ("final_image", "qa_report", "recommend_rerun",
                    "base_composite", "highlight_composite",
                    "base_tiles", "highlight_tiles", "debug_info")
    FUNCTION = "finish_seams_v2"
    CATEGORY = "DB9"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "processed_tiles": ("IMAGE",),
            "tiling_context": ("DB9_TILING_CONTEXT",),
            "extract_highlight": ("BOOLEAN", {"default": True}),
            "highlight_extract_blur": ("INT", {"default": 9, "min": 1, "max": 101, "step": 2}),
            "highlight_threshold": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}),
            "highlight_gain": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.01}),
            "soft_clamp_strength": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 1.0, "step": 0.01}),
            "micro_contrast_strength": ("FLOAT", {"default": 0.10, "min": 0.0, "max": 1.0, "step": 0.01}),
            "normalize_strength": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 1.0, "step": 0.01}),
            "normalize_crop_ratio": ("FLOAT", {"default": 0.12, "min": 0.0, "max": 0.45, "step": 0.01}),
            "normalize_max_luma_shift": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 0.25, "step": 0.01}),
            "highlight_blend_mode": (["add", "screen"], {"default": "screen"}),
            "center_priority_strength": ("FLOAT", {"default": 0.90, "min": 0.0, "max": 2.0, "step": 0.01}),
            "canny_low_thresh": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 5.0, "step": 0.01}),
            "canny_high_thresh": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 5.0, "step": 0.01}),
            "border_edge_penalty": ("FLOAT", {"default": 0.90, "min": 0.0, "max": 1.0, "step": 0.01}),
            "border_start": ("FLOAT", {"default": 0.12, "min": 0.0, "max": 0.95, "step": 0.01}),
            "highlight_amount": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 2.0, "step": 0.01}),
            "ssim_threshold": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}),
            "l2_threshold": ("FLOAT", {"default": 0.12, "min": 0.0, "max": 10.0, "step": 0.01}),
            "ghost_threshold": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 10.0, "step": 0.01}),
            "severity_weight_ssim": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01}),
            "severity_weight_l2": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01}),
            "severity_weight_ghost": ("FLOAT", {"default": 1.25, "min": 0.0, "max": 10.0, "step": 0.01}),
        }}

    def finish_seams_v2(self, processed_tiles, tiling_context,
                        extract_highlight, highlight_extract_blur, highlight_threshold,
                        highlight_gain, soft_clamp_strength, micro_contrast_strength,
                        normalize_strength, normalize_crop_ratio, normalize_max_luma_shift,
                        highlight_blend_mode, center_priority_strength, canny_low_thresh,
                        canny_high_thresh, border_edge_penalty, border_start, highlight_amount,
                        ssim_threshold, l2_threshold, ghost_threshold,
                        severity_weight_ssim, severity_weight_l2, severity_weight_ghost):
        tile_plan = tiling_context["tile_plan"]
        tile_meta = tiling_context["tile_meta"]
        seam_feather_px = int(tiling_context.get("seam_feather_px", 64))

        collector = DB9TileResultCollectorV2()
        normalizer = DB9TileColorNormalize()
        composite = DB9HighlightPreserveCompositeCanny()
        qa = DB9TileQAPriority()

        base_tiles, highlight_tiles, _, dbg_collect = collector.collect_results(
            processed_tiles, tile_meta, extract_highlight, highlight_extract_blur,
            highlight_threshold, highlight_gain, soft_clamp_strength, micro_contrast_strength)
        norm_base_tiles, dbg_norm = normalizer.normalize_tiles(
            base_tiles, normalize_strength, normalize_crop_ratio, normalize_max_luma_shift)
        base_composite, highlight_composite, final_image, dbg_comp = composite.composite(
            norm_base_tiles, highlight_tiles, tile_plan, highlight_blend_mode,
            center_priority_strength, canny_low_thresh, canny_high_thresh,
            border_edge_penalty, border_start, highlight_amount, seam_feather_px)
        qa_report, dbg_qa, recommend_rerun = qa.evaluate(
            final_image, tile_plan, norm_base_tiles,
            ssim_threshold, l2_threshold, ghost_threshold,
            severity_weight_ssim, severity_weight_l2, severity_weight_ghost)
        return (final_image, qa_report, recommend_rerun,
                base_composite, highlight_composite,
                norm_base_tiles, highlight_tiles,
                " | ".join([dbg_collect, dbg_norm, dbg_comp, dbg_qa]))


class DB9PriorityRerunContext:
    """
    Context-aware Priority Rerun. Reads tile_plan from tiling_context.
    After KSampler processes the subset tiles, feed the rerun_processed_tiles
    back into DB9SeamFinishV2 using the returned rerun_context.
    """
    RETURN_TYPES = ("BOOLEAN", "DB9_TILING_CONTEXT", "STRING", "IMAGE",
                    "DB9_TILE_IMAGE_STACK", "DB9_TILE_IMAGE_STACK", "STRING")
    RETURN_NAMES = ("should_continue", "rerun_context", "rerun_indices",
                    "subset_tile_images", "merged_base_tiles", "merged_highlight_tiles",
                    "debug_info")
    FUNCTION = "priority_rerun_v2"
    CATEGORY = "DB9"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "source_image": ("IMAGE",),
            "tiling_context": ("DB9_TILING_CONTEXT",),
            "qa_report": ("DB9_QA_REPORT",),
            "base_tiles": ("DB9_TILE_IMAGE_STACK",),
            "highlight_tiles": ("DB9_TILE_IMAGE_STACK",),
            "attempt": ("INT", {"default": 1, "min": 1, "max": 10}),
            "max_attempts": ("INT", {"default": 2, "min": 1, "max": 10}),
            "max_seam_pairs_to_rerun": ("INT", {"default": 3, "min": 1, "max": 100}),
            "expand_neighbors": ("BOOLEAN", {"default": True}),
            "rerun_seed_mode": (["same", "attempt_offset", "golden_jitter"], {"default": "attempt_offset"}),
        }, "optional": {
            "rerun_base_tiles": ("DB9_TILE_IMAGE_STACK",),
            "rerun_highlight_tiles": ("DB9_TILE_IMAGE_STACK",),
        }}

    def priority_rerun_v2(self, source_image, tiling_context, qa_report,
                          base_tiles, highlight_tiles, attempt, max_attempts,
                          max_seam_pairs_to_rerun, expand_neighbors, rerun_seed_mode,
                          rerun_base_tiles=None, rerun_highlight_tiles=None):
        tile_plan = tiling_context["tile_plan"]
        seam_feather_px = tiling_context.get("seam_feather_px", 64)

        planner = DB9TilePriorityRerunPlanner()
        emitter  = DB9TileBatchEmitterSubsetV2()
        merger   = DB9TileResultMergeV2()

        should_continue, rerun_plan, rerun_indices, dbg_plan = planner.plan_rerun(
            tile_plan, qa_report, attempt, max_attempts,
            max_seam_pairs_to_rerun, expand_neighbors, rerun_seed_mode)
        subset_tile_images, subset_tile_meta, dbg_emit = emitter.emit_subset(source_image, rerun_plan)

        if rerun_base_tiles is not None and rerun_highlight_tiles is not None:
            merged_base, merged_hi, dbg_merge = merger.merge_results(
                base_tiles, highlight_tiles, rerun_base_tiles, rerun_highlight_tiles)
        else:
            merged_base, merged_hi, dbg_merge = base_tiles, highlight_tiles, "Merge skipped."

        # Build rerun_context: full plan (for final composite) + subset meta (for next SeamFinishV2)
        rerun_context = {
            "tile_plan": rerun_plan,
            "tile_meta": subset_tile_meta,
            "seam_feather_px": int(seam_feather_px),
            "total_tiles": len(subset_tile_meta),
            "cols": int(tiling_context.get("cols", 1)),
            "rows": int(tiling_context.get("rows", 1)),
        }
        return (should_continue, rerun_context, rerun_indices, subset_tile_images,
                merged_base, merged_hi, " | ".join([dbg_plan, dbg_emit, dbg_merge]))


# ─── Registration ─────────────────────────────────────────────────────────────
NODE_CLASS_MAPPINGS = {
    # V1 — kept for backward compatibility
    "DB9TilePrep": DB9TilePrep,
    "DB9SeamFinish": DB9SeamFinish,
    "DB9PriorityRerun": DB9PriorityRerun,
    # V2 — context-aware, simplified wiring
    "DB9TilingContext": DB9TilingContext,
    "DB9SeamFinishV2": DB9SeamFinishV2,
    "DB9PriorityRerunContext": DB9PriorityRerunContext,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "DB9TilePrep": "DB9 Tile Prep",
    "DB9SeamFinish": "DB9 Seam Finish",
    "DB9PriorityRerun": "DB9 Priority Rerun",
    "DB9TilingContext": "DB9 Tiling Context",
    "DB9SeamFinishV2": "DB9 Seam Finish V2",
    "DB9PriorityRerunContext": "DB9 Priority Rerun Context",
}


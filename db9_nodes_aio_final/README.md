# DB9 Nodes AIO Final

DB9 custom nodes for ComfyUI focused on tiling workflows, seam finishing,
priority reruns, tone matching, compare/export, and a live tone editor UI.

## Included Nodes

### Core nodes (9)
| Node | Function |
|---|---|
| DB9 Tile Plan V2 | Auto tile planning with tile size, overlap, grid, and seed logic |
| DB9 Tile Batch Emitter V2 | Extract tiles from the source image with padding |
| DB9 Tile Result Collector V2 | Collect processed tiles and extract highlight/detail stacks |
| DB9 Highlight Preserve Composite Canny | Composite tiles with edge-aware blending |
| DB9 Tile QA Priority | Score seams with SSIM, L2, and ghost metrics |
| DB9 Tile Priority Rerun Planner | Select tiles to rerun from QA severity |
| DB9 Tile Batch Emitter Subset V2 | Emit only rerun tiles |
| DB9 Tile Result Merge V2 | Merge rerun outputs back into the full stack |
| DB9 Tile Color Normalize | Normalize color consistency across tiles |

### Macro nodes (3)
| Node | Function |
|---|---|
| DB9 Tile Prep | Wrapper for planning and tile emission |
| DB9 Seam Finish | Wrapper for collection, normalize, composite, and QA |
| DB9 Priority Rerun | Wrapper for rerun planning, subset emission, and merge |

### Tone and compare nodes (2)
| Node | Function |
|---|---|
| DB9 Tone Match | Match tone, luminance, and color between upscaled and original images |
| DB9 Compare And Save | Compare images, apply final adjustments, and save to disk |

### Live editor node (1)
| Node | Function |
|---|---|
| DB9 Live Tone Editor | Live tone and color editor with frontend panel, compare modes, and autosave |

## Install

1. Copy this folder into `ComfyUI/custom_nodes/`
2. Restart ComfyUI

ComfyUI should auto-load the frontend extension from `web/extensions/db9_live_editor.js`.

## Dependencies

Minimal package list:

```txt
torch
numpy
Pillow
```

`opencv-python` is not required here. Edge detection in this package is implemented with PyTorch logic, and adding desktop OpenCV can conflict with `opencv-python-headless` in some ComfyUI setups.

## Suggested Flow

```txt
Pass 1: Load Image -> DB9 Tile Prep -> KSampler -> DB9 Seam Finish -> DB9 Tone Match
Pass 2: DB9 Priority Rerun -> KSampler -> DB9 Seam Finish
Final: DB9 Compare And Save or DB9 Live Tone Editor
```

## Tone Match Modes

- `lab_l_only`: Match luminance while preserving source color character
- `shm_match`: Separate shadow, midtone, and highlight matching
- `histogram`: Full histogram matching per RGB channel
- `mean_std`: Simpler per-channel mean and standard deviation matching
- `luma_only`: Lightweight luminance shift only

## Compare Modes

- `vertical`: Vertical wipe split
- `horizontal`: Horizontal wipe split
- `side_by_side`: Concatenate both images horizontally
- `grid_2x2`: Checkerboard-style compare
- `difference`: Amplified difference map

## Notes

- `pad_mode=reflect` includes a safe fallback at border tiles
- `pad_mode=replicate` is usually the safest manual option for Colab
- Use `DB9 Tile Color Normalize` before the final composite for more stable tile-to-tile color
- Use `DB9 Tone Match` after upscale to pull the final image closer to the original tone
- Use `DB9 Compare And Save` for final preview/export
- Use `DB9 Live Tone Editor` when you want interactive adjustments from the ComfyUI frontend

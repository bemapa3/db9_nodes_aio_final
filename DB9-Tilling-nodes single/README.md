# DB9 Tiling Nodes AIO (Clean)

This is the clean package version with:
- DB9 Tile Plan V2
- DB9 Tile Batch Emitter V2
- DB9 Tile Result Collector V2
- DB9 Highlight Preserve Composite Canny
- DB9 Tile QA Priority
- DB9 Tile Priority Rerun Planner
- DB9 Tile Batch Emitter Subset V2
- DB9 Tile Result Merge V2
- DB9 Tile Color Normalize

## Install
Copy these files into your custom node repo root:
- __init__.py
- db9_tiling_aio.py
- requirements.txt
- README.md

Then restart ComfyUI.

## Padding note
- `DB9 Tile Plan V2` can still use `pad_mode=reflect`.
- Border tiles now use a safe fallback automatically:
  - fallback to `replicate` when reflect padding would exceed tile bounds
  - fallback to `constant` when the tile edge is too small for reflect
- If you want the most conservative behavior for Colab or mixed-size edge tiles, `pad_mode=replicate` is still the safest manual choice.

## Recommended patch in workflow
DB9 Tile Result Collector V2 (base_tiles)
-> DB9 Tile Color Normalize
-> DB9 Highlight Preserve Composite Canny (base_tiles)

Collector highlight_tiles
-> Composite Canny highlight_tiles

Tile Plan V2 tile_plan
-> Composite Canny tile_plan

# db9_workflow_pack.md

## File trong bộ này

- workflow_db9_pass1_aio.json
- workflow_db9_priority_rerun_aio.json
- workflow_db9_guide.json

## 1) workflow_db9_pass1_aio.json
Workflow chạy pass đầu:
- tự plan tile
- batch tile
- render qua SDVN
- ghép bằng Composite Canny
- QA seam theo mức độ nặng

## 2) workflow_db9_priority_rerun_aio.json
Workflow rerun:
- chỉ rerun seam nặng nhất
- subset tile
- merge lại vào full stack
- composite lại
- QA lại

## 3) workflow_db9_guide.json
Chỉ là note canvas để bạn nhớ 3 kiểu dùng.

## Lưu ý
- Bạn cần đã cài đúng node AIO ở root repo:
  - __init__.py
  - db9_tiling_aio.py
  - requirements.txt
  - README.md
- Nếu tên node SDVN trong máy bạn khác nhẹ so với JSON này, đổi lại trong canvas là được.

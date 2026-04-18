import os
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
Bạn là một AI coding agent chạy trong VS Code.

Nhiệm vụ:
- Hỗ trợ đọc file trong workspace
- Trả lời ngắn gọn, đúng trọng tâm
- Khi cần, đề xuất sửa code an toàn
- Không tự ý chạy lệnh phá hoại
- Nếu thiếu thông tin, nói rõ bạn đang thiếu gì
"""

WORKSPACE = Path.cwd()


def read_file(relative_path: str) -> str:
    file_path = (WORKSPACE / relative_path).resolve()

    if not str(file_path).startswith(str(WORKSPACE.resolve())):
        return "Error: Đường dẫn nằm ngoài workspace."

    if not file_path.exists():
        return f"Error: Không tìm thấy file: {relative_path}"

    if file_path.is_dir():
        return f"Error: {relative_path} là thư mục, không phải file."

    try:
        content = file_path.read_text(encoding="utf-8")
        return content[:20000]
    except Exception as e:
        return f"Error khi đọc file: {e}"


def list_files(relative_path: str = ".") -> str:
    base_path = (WORKSPACE / relative_path).resolve()

    if not str(base_path).startswith(str(WORKSPACE.resolve())):
        return "Error: Đường dẫn nằm ngoài workspace."

    if not base_path.exists():
        return f"Error: Không tìm thấy thư mục: {relative_path}"

    if not base_path.is_dir():
        return f"Error: {relative_path} không phải thư mục."

    items = []
    for p in sorted(base_path.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        prefix = "[DIR]" if p.is_dir() else "[FILE]"
        items.append(f"{prefix} {p.relative_to(WORKSPACE)}")

    return "\n".join(items[:500])


TOOLS = [
    {
        "type": "function",
        "name": "read_file",
        "description": "Đọc nội dung một file trong workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "relative_path": {
                    "type": "string",
                    "description": "Đường dẫn tương đối từ workspace, ví dụ: src/main.py"
                }
            },
            "required": ["relative_path"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "list_files",
        "description": "Liệt kê file và thư mục trong workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "relative_path": {
                    "type": "string",
                    "description": "Thư mục tương đối từ workspace, mặc định là ."
                }
            },
            "required": [],
            "additionalProperties": False
        }
    }
]


def run_tool_call(tool_name: str, arguments: dict) -> str:
    if tool_name == "read_file":
        return read_file(arguments["relative_path"])
    if tool_name == "list_files":
        return list_files(arguments.get("relative_path", "."))
    return f"Unknown tool: {tool_name}"


def ask_agent(user_input: str):
    response = client.responses.create(
        model="gpt-5.4",
        instructions=SYSTEM_PROMPT,
        input=user_input,
        tools=TOOLS
    )

    while True:
        tool_calls = [item for item in response.output if item.type == "function_call"]

        if not tool_calls:
            print("\n=== Agent ===")
            print(response.output_text)
            break

        tool_outputs = []
        for call in tool_calls:
            try:
                args = json.loads(call.arguments)
            except json.JSONDecodeError:
                args = {}

            result = run_tool_call(call.name, args)

            tool_outputs.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": result
            })

        response = client.responses.create(
            model="gpt-5.4",
            instructions=SYSTEM_PROMPT,
            previous_response_id=response.id,
            input=tool_outputs
        )


def main():
    print("VS Code AI Agent (Python)")
    print("Workspace:", WORKSPACE)
    print("Gõ 'exit' để thoát.\n")

    while True:
        user_input = input("Bạn> ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue
        ask_agent(user_input)


if __name__ == "__main__":
    main()
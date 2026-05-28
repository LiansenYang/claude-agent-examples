import os
import platform
import re
import subprocess
import urllib.request
import yaml
import anthropic
from html.parser import HTMLParser
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    base_url=os.environ["ANTHROPIC_BASE_URL"],
    # 增加下面这一行，手动注入代理平台需要的鉴权头
    default_headers={"Authorization": f"Bearer {os.environ['ANTHROPIC_API_KEY']}"},
    timeout=3000.0 # 增加超时时间到5分钟，防止大上下文时挂起
)
MODEL = os.environ["ANTHROPIC_MODEL"]

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"

class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills = {}
        self._load_all()

    def _load_all(self):
        if not self.skills_dir.exists():
            return
        for f in sorted(self.skills_dir.rglob("SKILL.md")):
            text = f.read_text(encoding="utf-8")
            meta, body = self._parse_frontmatter(text)
            name = meta.get("name", f.parent.name)
            self.skills[name] = {"meta": meta, "body": body, "path": str(f)}

    def _parse_frontmatter(self, text: str) -> tuple:
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if not match:
            return {}, text
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        return meta, match.group(2).strip()

    def get_descriptions(self) -> str:
        if not self.skills:
            return "(no skills available)"
        lines = []
        for name, skill in self.skills.items():
            desc = skill["meta"].get("description", "No description")
            tags = skill["meta"].get("tags", "")
            line = f"  - {name}: {desc}"
            if tags:
                line += f" [{tags}]"
            lines.append(line)
        return "\n".join(lines)

    def get_content(self, name: str) -> str:
        skill = self.skills.get(name)
        if not skill:
            return f"Error: Unknown skill '{name}'. Available: {', '.join(self.skills.keys())}"
        return f'<skill name="{name}">\n{skill["body"]}\n</skill>'

SKILL_LOADER = SkillLoader(SKILLS_DIR)

class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4"):
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def get_text(self):
        return re.sub(r"\n{3,}", "\n\n", "".join(self._parts)).strip()

def web_fetch(url: str, extract_mode: str = "text", max_chars: int = 8000) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"Error fetching {url}: {e}"

    if extract_mode == "text":
        parser = _TextExtractor()
        parser.feed(raw)
        text = parser.get_text()
    else:
        text = raw

    return text[:max_chars]


# ============== TodoList 计划与执行 ==============
# 维护一份内存中的 todo 列表，模型通过 update_todos 工具读写
# 每项形如 {"id": 1, "content": "...", "status": "pending|in_progress|completed"}
TODOS: list[dict] = []
VALID_STATUS = {"pending", "in_progress", "completed"}
STATUS_ICON = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}

def render_todos(todos: list[dict]) -> str:
    if not todos:
        return "(当前无待办事项)"
    lines = []
    for t in todos:
        icon = STATUS_ICON.get(t.get("status", "pending"), "[?]")
        lines.append(f"  {icon} {t.get('id')}. {t.get('content', '')}")
    return "\n".join(lines)

def update_todos(todos: list[dict]) -> str:
    global TODOS
    cleaned = []
    for i, t in enumerate(todos, start=1):
        content = (t.get("content") or "").strip()
        if not content:
            continue
        status = t.get("status", "pending")
        if status not in VALID_STATUS:
            status = "pending"
        cleaned.append({"id": t.get("id", i), "content": content, "status": status})

    in_progress = [t for t in cleaned if t["status"] == "in_progress"]
    if len(in_progress) > 1:
        return "Error: 同一时间只能有一个 in_progress 任务，请重新规划。"

    TODOS = cleaned
    print("\n[计划已更新]")
    print(render_todos(TODOS))
    print()

    pending = [t for t in TODOS if t["status"] == "pending"]
    done = [t for t in TODOS if t["status"] == "completed"]
    summary = f"todos updated: total={len(TODOS)}, completed={len(done)}, in_progress={len(in_progress)}, pending={len(pending)}"
    return summary + "\n\n当前列表：\n" + render_todos(TODOS)

if platform.system() == "Windows":
    env_prompt = "当前操作系统为 Windows，run_command 执行环境为 cmd.exe。\n请注意：严禁使用 Linux 特有的 shell 语法（如 cat << EOF、grep、ls 等）。如果需要多行写入文件，请优先使用 write_file 工具，避免因命令行转义导致语法错误。"
else:
    env_prompt = f"当前操作系统为 {platform.system()}，run_command 执行环境通常为 bash/sh。\n你可以使用标准的 Unix/Linux shell 语法，但写入多行文件时也建议优先使用 write_file 工具。"

SYSTEM_PROMPT = f"""
你是一个 AI 助手，使用中文回复。

【运行环境】
{env_prompt}

【行事规矩】
1. 当需要多个步骤才能完成任务时，先调用 update_todos 工具，
    把任务拆成一份清晰的 todolist（每条一句话，按顺序执行）。
2. 拆完计划后，按列表顺序一步步执行：
   - 开始某一步前，把那一步的 status 改为 in_progress（同一时间只许一项 in_progress）。
   - 该步办完后，立即把它改为 completed，再开始下一项。
3. 简单的一句话问答（无需多步骤）不必生成 todolist，直接回答即可。
4. 遇到不熟悉的专题，请先调用 load_skill 工具加载对应知识，再继续。

当前可用技能：
{SKILL_LOADER.get_descriptions()}"""

TOOLS = [
    {
        "name": "write_file",
        "description": "安全地将多行文本写入指定文件，避免了在 shell 命令行中转义多行文本引发的各种语法错误。",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "要写入的绝对或相对文件路径"},
                "content": {"type": "string", "description": "要写入的完整文件内容"}
            },
            "required": ["filepath", "content"]
        }
    },
    {
        "name": "run_command",
        "description": "在终端执行一条 shell 命令并返回输出",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 shell 命令"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "web_fetch",
        "description": "获取指定 URL 的网页内容，支持文本提取模式",
        "input_schema": {
            "type": "object",
            "properties": {
                "url":          {"type": "string",  "description": "要访问的完整 URL"},
                "extract_mode": {"type": "string",  "description": "提取模式：text（纯文本，默认）或 raw（原始 HTML）"},
                "max_chars":    {"type": "integer", "description": "最大返回字符数，默认 8000"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "load_skill",
        "description": "加载指定技能的详细知识内容，在回答相关问题前调用",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "技能名称，必须是系统提示中列出的可用技能之一"
                }
            },
            "required": ["skill_name"]
        }
    },
    {
        "name": "update_todos",
        "description": (
            "创建或更新当前任务的 todolist。"
            "传入完整的 todos 数组（每次都是全量覆盖，而非增量）。"
            "用于：拆解多步骤任务、推进任务状态（pending → in_progress → completed）。"
            "约束：同一时间至多一个任务为 in_progress。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "完整的 todo 列表，按执行顺序排列",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":      {"type": "integer", "description": "序号，从 1 开始"},
                            "content": {"type": "string",  "description": "这一步要做什么"},
                            "status":  {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "状态"
                            }
                        },
                        "required": ["id", "content", "status"]
                    }
                }
            },
            "required": ["todos"]
        }
    }
]

history = []

while True:
    user_input = input("你: ")

    history.append({"role": "user", "content": user_input})

    while True:
        message = client.messages.create(
            model=MODEL,
            max_tokens=200000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=history
        )

        history.append({"role": "assistant", "content": message.content})

        if message.stop_reason != "tool_use":
            reply = next((b.text for b in message.content if b.type == "text"), "")
            print(f"[Agent回答]: {reply}\n")
            if TODOS:
                unfinished = [t for t in TODOS if t["status"] != "completed"]
                if unfinished:
                    print("[计划尚未办妥，继续执行...]")
                    print(render_todos(TODOS))
                    print()
                    history.append({
                        "role": "user",
                        "content": (
                            "任务尚未完成，以下任务仍未完成，请按计划继续执行，"
                            "并按规矩更新 todolist 状态：\n" + render_todos(TODOS)
                        )
                    })
                    continue
                print("[最终计划状态 - 全部办妥]")
                print(render_todos(TODOS))
                print()
                TODOS = []
            break


        tool_results = []
        for block in message.content:
            if block.type != "tool_use":
                continue

            if block.name == "web_fetch":
                url = block.input["url"]
                mode = block.input.get("extract_mode", "text")
                max_chars = block.input.get("max_chars", 8000)
                print(f"[网页获取]: {url}")
                content = web_fetch(url, mode, max_chars)

            elif block.name == "write_file":
                filepath = block.input["filepath"]
                file_content = block.input["content"]
                print(f"[写入文件]: {filepath}")
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(file_content)
                    content = f"文件 {filepath} 写入成功！"
                except Exception as e:
                    content = f"写入文件失败: {e}"

            elif block.name == "run_command":
                command = block.input["command"]
                print(f"[执行命令]: {command}")
                result = subprocess.run(command, shell=True, capture_output=True)
                try:
                    stdout = result.stdout.decode('utf-8')
                except UnicodeDecodeError:
                    stdout = result.stdout.decode('gbk', errors='replace')
                try:
                    stderr = result.stderr.decode('utf-8')
                except UnicodeDecodeError:
                    stderr = result.stderr.decode('gbk', errors='replace')
                output = stdout or stderr
                if len(output) > 8000:
                    output = output[:8000] + f"\n... [输出过长，已自动截断。原始长度: {len(output)}]"
                print(f"[命令输出]: {output}")
                content = output

            elif block.name == "load_skill":
                skill_name = block.input["skill_name"]
                print(f"[加载技能]: {skill_name}")
                content = SKILL_LOADER.get_content(skill_name)

            elif block.name == "update_todos":
                content = update_todos(block.input.get("todos", []))

            else:
                content = f"Error: Unknown tool '{block.name}'"

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content
            })

        history.append({"role": "user", "content": tool_results})

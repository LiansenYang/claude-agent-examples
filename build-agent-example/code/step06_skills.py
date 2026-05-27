import os
import re
import subprocess
import urllib.parse
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
    default_headers={"Authorization": f"Bearer {os.environ['ANTHROPIC_API_KEY']}"}
)
MODEL = os.environ["ANTHROPIC_MODEL"]

SKILLS_DIR = Path(__file__).parent / "skills"

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

    def get_all_content(self) -> str:
        parts = []
        for name, skill in self.skills.items():
            parts.append(self.get_content(name))
        return "\n\n".join(parts) if parts else "(no skills available)"

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
    # 对 URL 中的特殊字符（如 +）进行规范化编码
    parsed = urllib.parse.urlparse(url)
    safe_path = urllib.parse.quote(parsed.path, safe="/,@")
    normalized_url = urllib.parse.urlunparse(parsed._replace(path=safe_path))

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/125.0.0.0 Safari/537.36"
    }
    req = urllib.request.Request(normalized_url, headers=headers)
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

SKILL_CONTENT = SKILL_LOADER.get_all_content()

SYSTEM_PROMPT = f"""
你是一个 AI 助手，使用中文回复。

遇到不熟悉的专题时，请先调用 load_skill 工具加载对应的知识，再给出回答。

以下是你可调用的技能知识（已加载当前会话中，可直接参考使用）：
{SKILL_CONTENT}

当前可用技能列表：
{SKILL_LOADER.get_descriptions()}"""

TOOLS = [
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
    }
]

history = []

while True:
    user_input = input("你: ")

    history.append({"role": "user", "content": user_input})

    while True:
        message = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=history
        )

        history.append({"role": "assistant", "content": message.content})

        if message.stop_reason != "tool_use":
            # 将生成器表达式用括号括起来，并加上默认值 "" (空字符串)
            reply = next((b.text for b in message.content if b.type == "text"), "")
            
            # 为了方便调试，如果连空字符串都没有，可以打印一下原始的 message 看看到底发生了什么
            if not reply:
                print(f"[Debug] 模型未返回文本，完整返回对象: {message}")
                reply = "（臣万死，未能给出有效答复）"
                
            print(f"[Agent回答]: {reply}\n")
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
                print(f"[网页获取结果]: {content[:200]}...")

            elif block.name == "run_command":
                command = block.input["command"]
                print(f"[执行命令]: {command}")
                result = subprocess.run(command, shell=True, capture_output=True, text=True)
                output = result.stdout or result.stderr
                print(f"[命令输出]: {output}")
                content = output

            elif block.name == "load_skill":
                skill_name = block.input["skill_name"]
                print(f"[加载技能]: {skill_name}")
                content = SKILL_LOADER.get_content(skill_name)

            else:
                content = f"Error: Unknown tool '{block.name}'"

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content
            })

        history.append({"role": "user", "content": tool_results})

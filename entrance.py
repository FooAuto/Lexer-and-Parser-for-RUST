from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from lexer.lexer import Lexer
from lexparser.lexparser import Parser
import uvicorn
from contextlib import asynccontextmanager
from lexer.token import tokenType
import sys
from utils.utils import *
from codegen.codegen import CodeGenerator


def format_action_table(action):
    formatted = {}
    for state_id, entries in enumerate(action):
        formatted[state_id] = {}
        for token_id, (act_type, target) in entries.items():
            if act_type == 0:
                formatted[state_id][token_id] = "accept"
            elif act_type == 1:
                formatted[state_id][token_id] = f"shift {target}"
            elif act_type == 2:
                formatted[state_id][token_id] = f"reduce {target}"
            else:
                formatted[state_id][token_id] = "error"
    return formatted


def format_goto_table(goto):
    formatted = {}
    for state_id, entries in enumerate(goto):
        formatted[state_id] = {}
        for nonterminal_id, target in entries.items():
            formatted[state_id][nonterminal_id] = str(target)
    return formatted


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initialization Start!")
    app.state.lexer = Lexer()
    print("Lexer Startup Done!")
    app.state.parser = Parser()
    print("Parser Startup Done!")
    app.state.codegen = CodeGenerator()
    print("CodeGen Startup Done!")
    app.state.map = {member.value: member.name for member in tokenType}
    print("Map Startup Done!")
    print("Initialization Done!")
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def serve_frontend():
    path = "static/index.html"
    path = resource_path(path)
    return FileResponse(path)


app.mount("/static", StaticFiles(directory=resource_path("static")), name="static")


@app.post("/api/parse")
async def api_parse(request: Request):
    lexer = app.state.lexer
    parser = app.state.parser
    codegen = app.state.codegen
    body = await request.json()
    code = body.get("code", "")

    lexer.load_code(code)
    tokens_for_highlight = lexer.get_all_tokens()

    mark_tokens = [
        {**t, "prop": tokenType(t["prop"]).name if isinstance(t["prop"], int) else t["prop"].name}
        for t in tokens_for_highlight
    ]

    unknown_token = next((t for t in mark_tokens if t["prop"] == "UNKNOWN"), None)
    if unknown_token:
        return {
            "error": {
                "content": f"词法错误: 未知Token '{unknown_token['content']}'",
                "loc": unknown_token["loc"],
                "tok": unknown_token,
            },
            "tokens": mark_tokens,
        }

    lexer.load_code(code)
    result = parser.parse(lexer)

    if isinstance(result, dict) and result.get("error"):
        error_info = result["error"]
        return {
            "error": {
                "content": error_info["content"],
                "loc": error_info["loc"],
                "tok": error_info.get("tok"),
            },
            "tokens": mark_tokens,
        }

    quadruples = result.get("quadruples", [])
    global_scope = parser.semantic_analyzer.symbol_tables[0]
    mips_code = codegen.generate(quadruples, global_scope)

    return {
        "tree": result["syntax_tree"],
        "quadruples": result.get("quadruples", []),
        "mips_code": mips_code,
        "tokens": mark_tokens,
        "success": True,
        "action": format_action_table(parser.action_table),
        "goto": format_goto_table(parser.goto_table),
    }


if __name__ == "__main__":
    is_frozen = getattr(sys, "frozen", False)
    if not is_frozen:
        # 开发时
        uvicorn.run("entrance:app", host="127.0.0.1", port=8000, reload=True)
    else:
        # 打包时
        uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initialization Start!")
    app.state.lexer = Lexer()
    print("Lexer Startup Done!")
    app.state.parser = Parser()
    print("Parser Startup Done!")
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
    body = await request.json()
    code = body.get("code", "")
    lines = code.splitlines(keepends=True)

    # 重置 lexer 状态
    # print(lines)
    # return {"tree": None}
    lexer.token_id = 1
    tokens, success = lexer.getLex(lines)
    mark_tokens = [
        {**t, "prop": tokenType(t["prop"]).name}
        for t in tokens
    ]
    # input(tokens)
    if not success:
        unk = next(t for t in mark_tokens if t["prop"] == "UNKNOWN")
        return {
            "error": {
                "content": unk["content"],
                "loc": unk["loc"]
            },
            "tokens": mark_tokens
        }

    # parser 进行语法分析
    result = parser.parse(tokens)
    if isinstance(result, dict) and result.get("error"):
        return {
            "error": {
                "content": result["error"],
                "loc": result["loc"],
                "tok": result["token"]
            },
            "tokens": mark_tokens
        }

    return {
        "tree": result,
        "tokens": mark_tokens,
        "success": success
    }


if __name__ == "__main__":
    is_frozen = getattr(sys, "frozen", False)
    if not is_frozen:
        # 开发时
        uvicorn.run(
            "entrance:app",
            host="0.0.0.0",
            port=8000,
            reload=True
        )
    else:
        # 打包时
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            reload=False
        )

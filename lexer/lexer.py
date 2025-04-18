import re
from dataclasses import dataclass
from lexer.token import tokenType, tokenKeywords, tokenSymbols


@dataclass
class Token:
    id: int
    content: str
    prop: tokenType
    loc: dict


class Lexer:
    def __init__(self):
        # 词法规则
        self.token_exprs = [
            (r"\s+", None),
            (r"//.*", tokenType.S_COMMENT),
            (r"/\*", None),
            (r"'(\\.|[^\\'])'", tokenType.CHAR_CONSTANT),
            (r'"(\\.|[^\\"])*"', tokenType.STRING_CONSTANT),
            (
                r"\b(?:"
                + "|".join(re.escape(k) for k in tokenKeywords.keys())
                + r")\b",
                None,
            ),
            (r"[A-Za-z_][A-Za-z0-9_]*!", tokenType.MACRO_IDENTIFIER),
            (r"[A-Za-z_][A-Za-z0-9_]*", tokenType.IDENTIFIER),
            (r"\d+\.\d+([eE][+-]?\d+)?", tokenType.FLOATING_POINT_CONSTANT),
            (r"\d+", tokenType.INTEGER_CONSTANT),
            (r"==|!=|>=|<=|->|\.\.|[+\-*/=><!]", None),
            (r"[(){}\[\];:,.]", None),
            (r"#", tokenType.EOF),
        ]
        self.token_id = 1
        self.lines = []  # Added to store lines
        self.line_idx = 0  # Added to track line index

    def handle_block_comment(self, lines, start_row, start_col, line_idx, start_pos):
        depth = 1
        comment_text = ""
        row = start_row
        col = start_col
        while line_idx < len(lines):
            line = lines[line_idx]
            pos = start_pos if row == start_row else 0
            while pos < len(line):
                if line[pos : pos + 2] == "/*":
                    depth += 1
                    comment_text += "/*"
                    pos += 2
                elif line[pos : pos + 2] == "*/":
                    depth -= 1
                    comment_text += "*/"
                    pos += 2
                    if depth == 0:
                        return comment_text, line_idx, pos
                else:
                    comment_text += line[pos]
                    pos += 1
            comment_text += "\n"
            row += 1
            line_idx += 1
        return comment_text, line_idx, pos  # Unclosed comment fallback

    def tokenize_line(self, line, row):
        tokens = []
        pos = 0
        while pos < len(line):
            match_found = False
            for pattern, initial_tag in self.token_exprs:
                if pattern == r"/\*":
                    if line[pos : pos + 2] == "/*":
                        comment_text, end_row_idx, end_pos = self.handle_block_comment(
                            self.lines, row, pos + 1, self.line_idx, pos + 2
                        )
                        tokens.append(
                            Token(
                                id=self.token_id,
                                content="/*" + comment_text,
                                prop=tokenType.LM_COMMENT,
                                loc={"row": row, "col": pos + 1},
                            )
                        )
                        self.token_id += 1
                        self.line_idx = end_row_idx
                        return tokens
                    continue
                regex = re.compile(pattern)
                match = regex.match(line, pos)
                if match:
                    text = match.group(0)
                    match_found = True
                    tag = initial_tag
                    if tag is None and text in tokenKeywords:
                        tag = tokenKeywords[text]
                    elif tag is None and text in tokenSymbols:
                        tag = tokenSymbols[text]
                    elif tag is None:
                        tag = tokenType.UNKNOWN
                    if tag not in [None, tokenType.UNKNOWN]:
                        tokens.append(
                            Token(
                                id=self.token_id,
                                content=text,
                                prop=tag,
                                loc={"row": row, "col": pos + 1},
                            )
                        )
                        self.token_id += 1
                    elif tag == tokenType.UNKNOWN and not text.isspace():
                        tokens.append(
                            Token(
                                id=self.token_id,
                                content=text,
                                prop=tag,
                                loc={"row": row, "col": pos + 1},
                            )
                        )
                        self.token_id += 1
                    pos = match.end(0)
                    break
            if not match_found:
                tokens.append(
                    Token(
                        id=self.token_id,
                        content=line[pos],
                        prop=tokenType.UNKNOWN,
                        loc={"row": row, "col": pos + 1},
                    )
                )
                self.token_id += 1
                pos += 1
        return tokens

    def getLex(self, lines):
        self.lines = lines
        self.line_idx = 0
        all_tokens = []
        row = 1
        success = True
        for idx, line in enumerate(lines):
            self.line_idx = idx
            tokens = self.tokenize_line(line, row)
            for token in tokens:
                if token.prop == tokenType.UNKNOWN:
                    success = False
                all_tokens.append(token)
            row += 1
        all_tokens.append(
            Token(
                id=self.token_id,
                content="#",
                prop=tokenType.EOF,
                loc={"row": row, "col": 1},
            )
        )
        return [t.__dict__ for t in all_tokens], success

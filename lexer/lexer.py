import re
from dataclasses import dataclass
from .token import tokenType, tokenKeywords, tokenSymbols


@dataclass
class Token:
    id: int
    content: str
    prop: tokenType
    loc: dict


class Lexer:
    def __init__(self):
        self.token_exprs = [
            (r"\s+", None),
            (r"//.*", tokenType.S_COMMENT),
            (r"/\*", tokenType.LM_COMMENT),
            (r"'(\\.|[^\\'])'", tokenType.CHAR_CONSTANT),
            (r'"(\\.|[^\\"])*"', tokenType.STRING_CONSTANT),
            (r"\b(?:" + "|".join(re.escape(k) for k in tokenKeywords.keys()) + r")\b", "KEYWORD"),
            (r"[A-Za-z_][A-Za-z0-9_]*!", tokenType.MACRO_IDENTIFIER),
            (r"[A-Za-z_][A-Za-z0-9_]*", tokenType.IDENTIFIER),
            (r"\d+\.\d+([eE][+-]?\d+)?", tokenType.FLOATING_POINT_CONSTANT),
            (r"\d+", tokenType.INTEGER_CONSTANT),
            (r"->|==|!=|>=|<=|\.\.", "SYMBOL"),
            (r"[+\-*/=><!&(){}\[\];:,.]", "SYMBOL"),
        ]
        self.compiled_rules = [(re.compile(p), t) for p, t in self.token_exprs]
        self.source_code = ""
        self.pos = 0
        self.line_num = 1
        self.col_num = 1
        self.token_id_counter = 1

    def load_code(self, code: str):
        self.source_code = code
        self.pos = 0
        self.line_num = 1
        self.col_num = 1
        self.token_id_counter = 1

    def _update_pos_and_loc(self, text: str):
        last_newline_pos = text.rfind("\n")
        if last_newline_pos != -1:
            self.line_num += text.count("\n")
            self.col_num = len(text) - last_newline_pos
        else:
            self.col_num += len(text)
        self.pos += len(text)

    def _handle_block_comment(self):
        start_loc = {"row": self.line_num, "col": self.col_num}
        scan_pos = self.pos + 2
        depth = 1
        while depth > 0 and scan_pos < len(self.source_code):
            if self.source_code[scan_pos : scan_pos + 2] == "*/":
                depth -= 1
                scan_pos += 2
            elif self.source_code[scan_pos : scan_pos + 2] == "/*":
                depth += 1
                scan_pos += 2
            else:
                scan_pos += 1

        comment_text = self.source_code[self.pos : scan_pos]
        self._update_pos_and_loc(comment_text)

        if depth > 0:
            return Token(self.token_id_counter, comment_text, tokenType.UNKNOWN, start_loc)

        token = Token(self.token_id_counter, comment_text, tokenType.LM_COMMENT, start_loc)
        self.token_id_counter += 1
        return token

    def get_next_token(self) -> Token:
        while self.pos < len(self.source_code):
            for compiled_regex, tag in self.compiled_rules:
                match = compiled_regex.match(self.source_code, self.pos)
                if match:
                    text = match.group(0)
                    loc = {"row": self.line_num, "col": self.col_num}

                    if tag is None:
                        self._update_pos_and_loc(text)
                        break

                    if tag == tokenType.LM_COMMENT:
                        return self._handle_block_comment()

                    self._update_pos_and_loc(text)
                    final_tag = tag
                    if tag == "KEYWORD":
                        final_tag = tokenKeywords.get(text, tokenType.IDENTIFIER)
                    elif tag == "SYMBOL":
                        final_tag = tokenSymbols[text]

                    token = Token(self.token_id_counter, text, final_tag, loc)
                    self.token_id_counter += 1
                    return token
            else:
                loc = {"row": self.line_num, "col": self.col_num}
                unknown_char = self.source_code[self.pos]
                self._update_pos_and_loc(unknown_char)
                token = Token(self.token_id_counter, unknown_char, tokenType.UNKNOWN, loc)
                self.token_id_counter += 1
                return token

        return Token(self.token_id_counter, "#", tokenType.EOF, {"row": self.line_num, "col": self.col_num})

    def get_all_tokens(self):
        self.load_code(self.source_code)
        tokens = []
        while True:
            token = self.get_next_token()
            tokens.append(token)
            if token.prop == tokenType.EOF:
                break
        return [t.__dict__ for t in tokens]

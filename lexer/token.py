from enum import Enum

class tokenType(Enum):
    IDENTIFIER = 1
    INTEGER_CONSTANT = 2
    FLOATING_POINT_CONSTANT = 3
    S_COMMENT = 4
    LM_COMMENT = 5
    RM_COMMENT = 6
    EOF = 7
    UNKNOWN = 8

    # 关键字
    LET = 100
    FN = 101
    RETURN = 102
    MUT = 103
    IF = 104
    ELSE = 105
    WHILE = 106
    FOR = 107
    IN = 108
    LOOP = 109
    BREAK = 110
    CONTINUE = 111
    I32 = 112

    # 各类符号
    ASSIGN = 201      # =
    PLUS = 202        # +
    MINUS = 203       # -
    MULT = 204        # *
    DIV = 205         # /
    EQ = 206          # ==
    NEQ = 207         # !=
    GT = 208          # >
    LT = 209          # <
    GE = 210          # >=
    LE = 211          # <=
    LPAREN = 212      # (
    RPAREN = 213      # )
    LBRACE = 214      # {
    RBRACE = 215      # }
    LBRACK = 216      # [
    RBRACK = 217      # ]
    COLON = 218       # :
    SEMICOLON = 219   # ;
    COMMA = 220       # ,
    ARROW = 221       # ->
    DOT = 222         # .
    DOTDOT = 223      # ..

    # 宏调用
    EXCLAMATION = 99
    MACRO_IDENTIFIER = 100

    # 字符与字符串
    CHAR_CONSTANT = 101
    STRING_LITERAL = 102

tokenKeywords = {
    "let": tokenType.LET,
    "fn": tokenType.FN,
    "return": tokenType.RETURN,
    "mut": tokenType.MUT,
    "if": tokenType.IF,
    "else": tokenType.ELSE,
    "while": tokenType.WHILE,
    "for": tokenType.FOR,
    "in": tokenType.IN,
    "loop": tokenType.LOOP,
    "break": tokenType.BREAK,
    "continue": tokenType.CONTINUE,
    "i32": tokenType.I32,
}

tokenSymbols = {
    "=": tokenType.ASSIGN,
    "+": tokenType.PLUS,
    "-": tokenType.MINUS,
    "*": tokenType.MULT,
    "/": tokenType.DIV,
    "==": tokenType.EQ,
    "!=": tokenType.NEQ,
    ">": tokenType.GT,
    "<": tokenType.LT,
    ">=": tokenType.GE,
    "<=": tokenType.LE,
    "(": tokenType.LPAREN,
    ")": tokenType.RPAREN,
    "{": tokenType.LBRACE,
    "}": tokenType.RBRACE,
    "[": tokenType.LBRACK,
    "]": tokenType.RBRACK,
    ":": tokenType.COLON,
    ";": tokenType.SEMICOLON,
    ",": tokenType.COMMA,
    "->": tokenType.ARROW,
    "..": tokenType.DOTDOT,
    ".": tokenType.DOT,
    '!': tokenType.EXCLAMATION,
}
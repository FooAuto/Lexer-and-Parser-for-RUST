from enum import Enum


class tokenType(Enum):
    IDENTIFIER = 1  # 标识符
    MACRO_IDENTIFIER = 2  # 宏标识符（以!结尾的标识符）
    INTEGER_CONSTANT = 3  # 整型常量
    FLOATING_POINT_CONSTANT = 4  # 浮点型常量
    CHAR_CONSTANT = 5  # 字符常量
    STRING_CONSTANT = 6  # 字符串常量
    S_COMMENT = 7  # 单行注释
    LM_COMMENT = 8  # 多行注释开始
    RM_COMMENT = 9  # 多行注释结束
    EOF = 10  # 文件结束标记
    UNKNOWN = 11  # 未知标记

    # 关键字
    I32 = 100  # i32
    LET = 101  # let
    IF = 102  # if
    ELSE = 103  # else
    WHILE = 104  # while
    RETURN = 105  # return
    MUT = 106  # mut
    FN = 107  # fn
    FOR = 108  # for
    IN = 109  # in
    LOOP = 110  # loop
    BREAK = 111  # break
    CONTINUE = 112  # continue

    # 各类符号
    ASSIGN = 201  # =
    PLUS = 202  # +
    MINUS = 203  # -
    MULT = 204  # *
    DIV = 205  # /
    EQ = 206  # ==
    GT = 207  # >
    GE = 208  # >=
    LT = 209  # <
    LE = 210  # <=
    NEQ = 211  # !=
    LPAREN = 212  # (
    RPAREN = 213  # )
    LBRACE = 214  # {
    RBRACE = 215  # }
    LBRACK = 216  # [
    RBRACK = 217  # ]
    SEMICOLON = 218  # ;
    COLON = 219  # :
    COMMA = 220  # ,
    ARROW = 221  # ->
    DOT = 222  # .
    DOTDOT = 223  # ..


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
    "!": tokenType.EXCLAMATION,
}

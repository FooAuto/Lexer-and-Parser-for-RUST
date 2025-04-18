from enum import Enum


class tokenType(Enum):
    IDENTIFIER = 1  # 标识符
    EXCLAMATION = 2  # 感叹号（!），用于宏标识符
    MACRO_IDENTIFIER = 3  # 宏标识符（以!结尾的标识符）
    INTEGER_CONSTANT = 4  # 整型常量
    FLOATING_POINT_CONSTANT = 5  # 浮点型常量
    CHAR_CONSTANT = 6  # 字符常量
    STRING_CONSTANT = 7  # 字符串常量
    S_COMMENT = 8  # 单行注释
    LM_COMMENT = 9  # 多行注释开始
    RM_COMMENT = 10  # 多行注释结束
    EOF = 11  # 文件结束标记
    UNKNOWN = 12  # 未知标记

    # 关键字
    I32 = 101  # i32
    LET = 102  # let
    IF = 103  # if
    ELSE = 104  # else
    WHILE = 105  # while
    RETURN = 106  # return
    MUT = 107  # mut
    FN = 108  # fn
    FOR = 109  # for
    IN = 110  # in
    LOOP = 111  # loop
    BREAK = 112  # break
    CONTINUE = 113  # continue

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
    "i32": tokenType.I32,
    "let": tokenType.LET,
    "if": tokenType.IF,
    "else": tokenType.ELSE,
    "while": tokenType.WHILE,
    "return": tokenType.RETURN,
    "mut": tokenType.MUT,
    "fn": tokenType.FN,
    "for": tokenType.FOR,
    "in": tokenType.IN,
    "loop": tokenType.LOOP,
    "break": tokenType.BREAK,
    "continue": tokenType.CONTINUE,
}

tokenSymbols = {
    "=": tokenType.ASSIGN,
    "+": tokenType.PLUS,
    "-": tokenType.MINUS,
    "*": tokenType.MULT,
    "/": tokenType.DIV,
    "==": tokenType.EQ,
    ">": tokenType.GT,
    ">=": tokenType.GE,
    "<": tokenType.LT,
    "<=": tokenType.LE,
    "!=": tokenType.NEQ,
    "(": tokenType.LPAREN,
    ")": tokenType.RPAREN,
    "{": tokenType.LBRACE,
    "}": tokenType.RBRACE,
    "[": tokenType.LBRACK,
    "]": tokenType.RBRACK,
    ";": tokenType.SEMICOLON,
    ":": tokenType.COLON,
    ",": tokenType.COMMA,
    "->": tokenType.ARROW,
    ".": tokenType.DOT,
    "..": tokenType.DOTDOT,
    "!": tokenType.EXCLAMATION,
}

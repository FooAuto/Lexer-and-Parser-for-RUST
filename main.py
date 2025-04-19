from lexer.lexer import Lexer
from parser.parser import Parser
from utils.utils import *
import json
from pprint import pprint

if __name__ == "__main__":
    with open("data/test6_2_2.rs", "r", encoding="utf-8") as f:
        lines = f.readlines()

    lexer = Lexer()
    parser = Parser()
    tokens, success = lexer.getLex(lines)

    with open("outputs/result.json", "w", encoding="utf-8") as out_file:
        json.dump(
            [serialize_token(token) for token in tokens],
            out_file,
            indent=2,
            ensure_ascii=False,
        )
    print("Tokens written to output/tokens.json")

    if success:
        print("\nLexing completed successfully.")
        print("\nNow Parser starts...")
        result = parser.parse(tokens)
        if isinstance(result, dict) and result.get("error"):
            print(f"语法错误：{result['error']}，位置：{result.get('loc')}")
        else:
            print("\n===== 语法树 (ASCII) =====")
            print_tree(result)
            # visualize_tree_matplotlib(result)
            visualize_tree_pyqt(result)
    else:
        print("\nLexing failed: unknown tokens found.")

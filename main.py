from lexer.lexer import Lexer
from utils.utils import serialize_token
import json

if __name__ == "__main__":
    with open("data/basic.rs", "r", encoding="utf-8") as f:
        lines = f.readlines()

    lexer = Lexer()
    tokens, success = lexer.getLex(lines)

    with open("outputs/result.json", "w", encoding="utf-8") as out_file:
        json.dump([serialize_token(token) for token in tokens], out_file, indent=2, ensure_ascii=False)
    print('Tokens written to output/tokens.json')

    if success:
        print("\nLexing completed successfully.")
    else:
        print("\nLexing failed: unknown tokens found.")
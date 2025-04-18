import re
from lexer.token import tokenType
from lexer.token import tokenType_to_terminal

# Action types
ACTION_ACC = 0
ACTION_S = 1
ACTION_R = 2
ActionType = ["acc", "s", "r"]


class Production:
    def __init__(self):
        self.cnt = 0
        self.from_id = 0
        self.to_ids = []

    def __lt__(self, other):
        return self.cnt < other.cnt


class Item:
    def __init__(self, production_id, dot_pos, terminal_id):
        self.production_id = production_id
        self.dot_pos = dot_pos
        self.terminal_id = terminal_id

    def __eq__(self, other):
        return (self.production_id, self.dot_pos, self.terminal_id) == (
            other.production_id,
            other.dot_pos,
            other.terminal_id,
        )

    def __lt__(self, other):
        return (self.production_id, self.dot_pos, self.terminal_id) < (
            other.production_id,
            other.dot_pos,
            other.terminal_id,
        )


class Closure:
    def __init__(self):
        self.cnt = 0
        self.items = []

    def __eq__(self, other):
        return sorted(self.items) == sorted(other.items)


class Parser:
    def __init__(self, prod_file="configs/production.cfg"):
        self.terminal_symbols = [
            t.name for t in sorted(tokenType, key=lambda x: x.value)
        ]

        self.non_terminal_symbols = ["epsilon"]

        self.productions = []
        self.firsts = []
        self.closures = []
        self.gos = []
        self.goto_table = []
        self.action_table = []

        self.read_productions(prod_file)
        self.find_firsts()
        self.find_gos()
        self.find_gotos()

    def get_id(self, symbol: str) -> int:
        if symbol in self.terminal_symbols:
            return self.terminal_symbols.index(symbol)
        if symbol in self.non_terminal_symbols:
            return self.non_terminal_symbols.index(symbol) + len(self.terminal_symbols)
        raise ValueError(f"Unknown symbol: {symbol}")

    def read_productions(self, filename="configs/production.cfg"):
        try:
            with open(filename, "r", encoding="utf-8") as fin:
                for line in fin:
                    m = re.match(r"\s*([^->]+)\s*->\s*(.*)", line)
                    if not m:
                        continue  # ingore comments
                    left = m.group(1).strip()
                    rights = [r.strip() for r in m.group(2).split("|")]
                    if left not in self.non_terminal_symbols:
                        self.non_terminal_symbols.append(left)
                    from_id = len(
                        self.terminal_symbols
                    ) + self.non_terminal_symbols.index(left)
                    for alt in rights:
                        p = Production()
                        p.cnt = len(self.productions)
                        p.from_id = from_id
                        # handle epsilon
                        # if right side is epsilon, no adding to non terminal
                        if alt != "epsilon":
                            for tok in alt.split():
                                if tok in self.terminal_symbols:
                                    tid = self.terminal_symbols.index(tok)
                                else:
                                    if tok not in self.non_terminal_symbols:
                                        self.non_terminal_symbols.append(tok)
                                    tid = len(
                                        self.terminal_symbols
                                    ) + self.non_terminal_symbols.index(tok)
                                p.to_ids.append(tid)
                        self.productions.append(p)
        except FileNotFoundError:
            raise FileNotFoundError(f"Cannot open production file: {filename}")

    def find_firsts(self):
        T = len(self.terminal_symbols)
        self.firsts = []
        for i in range(T):
            self.firsts.append({i})
        for _ in range(len(self.non_terminal_symbols)):
            self.firsts.append(set())

        changed = True
        while changed:
            changed = False
            for p in self.productions:
                A = p.from_id
                nullable = True
                for X in p.to_ids:
                    # 加入 FIRST(X)\{ε}
                    for t in self.firsts[X]:
                        if t != T and t not in self.firsts[A]:
                            self.firsts[A].add(t)
                            changed = True
                    # 若 X 不可空，结束
                    if T not in self.firsts[X]:
                        nullable = False
                        break
                # 全可空则加入 ε
                if nullable and T not in self.firsts[A]:
                    self.firsts[A].add(T)
                    changed = True

    def find_firsts_alpha(self, alpha, firsts: set):
        T = len(self.terminal_symbols)
        firsts.clear()
        for i, X in enumerate(alpha):
            for t in self.firsts[X]:
                if t != T:
                    firsts.add(t)
            if T not in self.firsts[X]:
                return
        # 若所有都可空，加入 ε
        firsts.add(T)

    def find_closures(self, closure: Closure):
        T = len(self.terminal_symbols)
        i = 0
        while i < len(closure.items):
            it = closure.items[i]
            prod = self.productions[it.production_id]
            if it.dot_pos < len(prod.to_ids):
                B = prod.to_ids[it.dot_pos]
                if B >= T:
                    beta = prod.to_ids[it.dot_pos + 1 :]
                    la_set = set()
                    self.find_firsts_alpha(beta + [it.terminal_id], la_set)
                    for j, p in enumerate(self.productions):
                        if p.from_id == B:
                            for la in la_set:
                                new_it = Item(j, 0, la)
                                if new_it not in closure.items:
                                    closure.items.append(new_it)
            i += 1

    def find_gos(self):
        # augmentation
        self.non_terminal_symbols.append("S'")
        aug = Production()
        aug.cnt = len(self.productions)  # new production
        aug.from_id = len(self.terminal_symbols) + self.non_terminal_symbols.index(
            "S'"
        )  # S' index
        start_sym = self.productions[0].from_id  # original start symbol
        aug.to_ids = [start_sym]
        self.productions.append(aug)

        self.aug_prod_id = aug.cnt

        eof_id = self.terminal_symbols.index("EOF")
        start = Closure()
        start.items.append(Item(self.aug_prod_id, 0, eof_id))
        self.find_closures(start)
        self.closures = [start]
        self.gos = [{}]

        idx = 0
        while idx < len(self.closures):
            C = self.closures[idx]
            trans = {}
            for it in C.items:
                prod = self.productions[it.production_id]
                if it.dot_pos < len(prod.to_ids):
                    X = prod.to_ids[it.dot_pos]
                    trans.setdefault(X, Closure()).items.append(
                        Item(it.production_id, it.dot_pos + 1, it.terminal_id)
                    )
            for X, Cx in trans.items():
                self.find_closures(Cx)
                if Cx in self.closures:
                    j = self.closures.index(Cx)
                else:
                    j = len(self.closures)
                    Cx.cnt = j
                    self.closures.append(Cx)
                    self.gos.append({})
                self.gos[idx][X] = j
            idx += 1

        # eof_id = self.terminal_symbols.index("EOF")
        # for st, row in enumerate(self.action_table):
        #     if eof_id in row and row[eof_id][0] == ACTION_ACC:
        #         print(f"State {st} is accepting on EOF")
        # else:
        #     print("No accept entries for EOF found in action_table")
        # input()

    def find_gotos(self):
        T = len(self.terminal_symbols)
        for i, C in enumerate(self.closures):
            self.action_table.append({})
            self.goto_table.append({})

            for sym, tgt in self.gos[i].items():
                if sym >= len(self.terminal_symbols):
                    self.goto_table[i][sym] = tgt

            for it in C.items:
                prod = self.productions[it.production_id]

                if it.dot_pos == len(prod.to_ids):
                    # reduce or accept
                    if it.production_id == self.aug_prod_id:
                        # accept on EOF
                        if it.terminal_id == self.terminal_symbols.index("EOF"):
                            self.action_table[i][it.terminal_id] = (ACTION_ACC, 0)
                    else:
                        # normal reduce
                        self.action_table[i][it.terminal_id] = (
                            ACTION_R,
                            it.production_id,
                        )
                else:
                    a = prod.to_ids[it.dot_pos]
                    # shift
                    if a < T and a in self.gos[i]:
                        self.action_table[i][a] = (ACTION_S, self.gos[i][a])

    def parse(self, lex):
        comments = {tokenType.S_COMMENT, tokenType.LM_COMMENT, tokenType.RM_COMMENT}
        toks = [
            t for t in lex if t["prop"] not in comments and t["prop"] != tokenType.EOF
        ]
        syms = [tokenType_to_terminal(t["prop"]) for t in toks] + ["EOF"]
        # input(syms)
        ids = [self.get_id(s) for s in syms]
        # input(ids)

        stack = [{"state": 0, "tree": {"root": "EOF"}}]
        idx = 0
        while True:
            st = stack[-1]["state"]
            a = ids[idx]
            # input(a)
            if a not in self.action_table[st]:
                cur = toks[idx]
                return {
                    "error": f"unexpected token {cur['prop']} ('{cur['content']}')",
                    "loc": cur["loc"],
                }
            act, val = self.action_table[st][a]
            if act == ACTION_S:  # shift
                stack.append({"state": val, "tree": {"root": syms[idx]}})
                idx += 1
            elif act == ACTION_R:  # reduce
                p = self.productions[val]
                children = []
                for _ in p.to_ids:
                    children.insert(0, stack.pop()["tree"])
                st2 = stack[-1]["state"]
                nt = p.from_id
                ns = self.goto_table[st2][nt]
                stack.append(
                    {
                        "state": ns,
                        "tree": {
                            "root": self.non_terminal_symbols[
                                nt - len(self.terminal_symbols)
                            ],
                            "children": children,
                        },
                    }
                )
            else:  # accept
                return stack[-1]["tree"]

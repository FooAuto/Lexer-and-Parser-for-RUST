import pickle
import os
import sys
import re
from lexer.token import tokenType
from lexer.token import tokenType_to_terminal
from semantic.semantic import SemanticAnalyzer, SemanticError
from utils.utils import * 


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
    def __init__(self, prod_file="configs/production.cfg", cache_file=".cache/parser_cache.pkl"):
        prod_file = resource_path(prod_file)
        try:
            prod_mtime = os.path.getmtime(prod_file)
        except OSError:
            prod_mtime = 0
        cache_mtime = os.path.getmtime(
            cache_file) if os.path.exists(cache_file) else 0
        cache_dir = os.path.dirname(cache_file)
        if cache_dir and not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        
        self.semantic_analyzer = SemanticAnalyzer()

        if cache_mtime >= prod_mtime:
            try:
                with open(cache_file, "rb") as f:
                    (
                        self.terminal_symbols,
                        self.non_terminal_symbols,
                        self.productions,
                        self.firsts,
                        self.closures,
                        self.gos,
                        self.action_table,
                        self.goto_table
                    ) = pickle.load(f)
                return
            except Exception:
                # 若反序列化失败，则继续下面的重建流程
                pass

        # 2. 否则按原逻辑计算
        self.terminal_symbols = [t.name for t in sorted(
            tokenType, key=lambda x: x.value)]

        self.non_terminal_symbols = [] # 将在 read_productions 中填充
        self.productions = []
        self.firsts = []
        self.closures = []
        self.gos = []
        self.action_table = []
        self.goto_table = []

        self.read_productions(prod_file)
        self.find_firsts()
        self.find_gos() # S' 会在这里被添加到 self.non_terminal_symbols
        self.find_gotos()

        with open(cache_file, "wb") as f:
            pickle.dump((
                self.terminal_symbols,
                self.non_terminal_symbols,
                self.productions,
                self.firsts,
                self.closures,
                self.gos,
                self.action_table,
                self.goto_table
            ), f)

    def get_id(self, symbol: str) -> int:
        if symbol in self.terminal_symbols:
            return self.terminal_symbols.index(symbol)
        if symbol in self.non_terminal_symbols:
            # 非终结符的ID = 列表中的索引 + 终结符总数
            return self.non_terminal_symbols.index(symbol) + len(self.terminal_symbols)
        raise ValueError(f"Unknown symbol: {symbol}")

    def read_productions(self, filename="configs/production.cfg"):
        temp_productions = [] 

        try:
            with open(filename, "r", encoding="utf-8") as fin:
                raw_lines = fin.readlines()

            processed_lines = []
            for i, line_content in enumerate(raw_lines):
                line_content = line_content.strip()
                if not line_content: # 跳过空行
                    continue
                if line_content.startswith("#"): # 一般注释
                    if i == 0 and "" in line_content: # 保留第一行的特殊注释
                         pass # 这个注释不代表产生式，所以不需要加入 processed_lines
                    continue # 跳过其他注释
                
                # 假设非注释行都是产生式
                processed_lines.append(line_content)
                m = re.match(r"\s*([^->]+)\s*->.*", line_content)
                if m:
                    left_symbol = m.group(1).strip()
                    if left_symbol not in self.non_terminal_symbols:
                        self.non_terminal_symbols.append(left_symbol)
            
            # 第二遍：正式创建 Production 对象
            for line_content in processed_lines:
                m = re.match(r"\s*([^->]+)\s*->\s*(.*)", line_content)
                if not m: # 理论上不应该发生，因为上面已经过滤了
                    continue
                
                left_symbol = m.group(1).strip()
                right_part_str = m.group(2).strip()

                # from_id 使用调整后的 get_id 或者直接用 index
                from_id = self.non_terminal_symbols.index(left_symbol) + len(self.terminal_symbols)
                
                p = Production()
                p.cnt = len(self.productions)
                p.from_id = from_id

                if right_part_str.lower() == "epsilon": # 处理 epsilon 产生式
                    # p.to_ids 保持为空列表
                    pass
                else:
                    rhs_symbols = right_part_str.split() # 按空格分割右部符号
                    for sym_name in rhs_symbols:
                        if sym_name in self.terminal_symbols:
                            tid = self.terminal_symbols.index(sym_name)
                        else:
                            # 右部的非终结符也必须在 self.non_terminal_symbols 中
                            if sym_name not in self.non_terminal_symbols:

                                self.non_terminal_symbols.append(sym_name)
                            tid = self.non_terminal_symbols.index(sym_name) + len(self.terminal_symbols)
                        p.to_ids.append(tid)
                self.productions.append(p)

        except FileNotFoundError:
            raise FileNotFoundError(f"Cannot open production file: {filename}")


    def find_firsts(self):
        T = len(self.terminal_symbols)
        NT_COUNT = len(self.non_terminal_symbols) # 非终结符的数量
        
        self.firsts = []
        for i in range(T): # 0 到 T-1 是终结符
            self.firsts.append({i}) 
        
        for _ in range(NT_COUNT):
            self.firsts.append(set())

        changed = True
        while changed:
            changed = False
            for p in self.productions:
                A = p.from_id # A 是一个非终结符的ID

                nullable_rhs = True
                for X_id in p.to_ids: # X_id 是右部符号的ID

                    for t_id in self.firsts[X_id]:
                        if t_id != T: # t_id 不是 epsilon
                            if t_id not in self.firsts[A]:
                                self.firsts[A].add(t_id)
                                changed = True
                    
                    if T not in self.firsts[X_id]: # 如果 X 不可导出 epsilon
                        nullable_rhs = False
                        break # 该产生式的后续符号不再影响 FIRST(A)
                
                if nullable_rhs: # 如果整个右部都可以导出 epsilon (或者右部为空)
                    if T not in self.firsts[A]:
                        self.firsts[A].add(T) # 将 epsilon 加入 FIRST(A)
                        changed = True


    def find_firsts_alpha(self, alpha_ids, result_first_set: set):
        T = len(self.terminal_symbols) # epsilon 的代表ID
        result_first_set.clear()
        
        all_nullable = True
        for X_id in alpha_ids:
            # 将 FIRST(X) \ {epsilon} 加入结果集
            has_epsilon_in_X = False
            for t_id in self.firsts[X_id]:
                if t_id != T: # 不是 epsilon
                    result_first_set.add(t_id)
                else:
                    has_epsilon_in_X = True
            
            if not has_epsilon_in_X: # 如果 X 不可导出 epsilon
                all_nullable = False
                break # 后续符号不再影响此alpha串的FIRST集
        
        if all_nullable: # 如果alpha串中的所有符号都可以导出epsilon
            result_first_set.add(T) # 将epsilon加入结果集


    def find_closures(self, closure: Closure):
        T = len(self.terminal_symbols) # epsilon 的代表ID
        i = 0
        while i < len(closure.items):
            it = closure.items[i] # Item(production_id, dot_pos, terminal_id_lookahead)
            prod = self.productions[it.production_id] # 当前处理的产生式 A -> alpha . B beta

            if it.dot_pos < len(prod.to_ids): # 如果点号不在末尾
                B_id = prod.to_ids[it.dot_pos] # 点号后的第一个符号 B

                if B_id >= T: # 如果 B 是一个非终结符
                    # beta 是 B 后面的符号串
                    beta_ids = prod.to_ids[it.dot_pos + 1:] 
                    # lookahead_for_B_rules 是 FIRST(beta terminal_id_lookahead)
                    lookahead_for_B_rules = set()
                    # 构造 beta + terminal_id_lookahead 序列
                    # terminal_id_lookahead 是终结符ID (it.terminal_id)
                    alpha_for_first_calc = beta_ids + [it.terminal_id]
                    self.find_firsts_alpha(alpha_for_first_calc, lookahead_for_B_rules)
                    
                    # 对于每个产生式 B -> gamma
                    for j, p_B_gamma in enumerate(self.productions):
                        if p_B_gamma.from_id == B_id: # 找到了 B -> gamma
                            for la_id in lookahead_for_B_rules:

                                if la_id == T : # 如果 FIRST(beta la) 包含 epsilon，则展望符是原展望符 it.terminal_id

                                     pass


                                new_it = Item(j, 0, la_id) # j是 B->gamma 的产生式ID, la_id是展望符
                                if new_it not in closure.items:
                                    closure.items.append(new_it)
            i += 1


    def find_gos(self):
        # 增广文法 S' -> S (这里S是原始开始符号)
        if "S'" not in self.non_terminal_symbols: # 避免重复添加
            self.non_terminal_symbols.append("S'")

        aug_prod = Production()
        aug_prod.cnt = len(self.productions) # 新产生式的编号
        # S' 的 ID
        s_prime_id = self.non_terminal_symbols.index("S'") + len(self.terminal_symbols)
        aug_prod.from_id = s_prime_id

        original_start_symbol_name = self.productions[0].from_id # 这是 Program 的ID
        aug_prod.to_ids = [original_start_symbol_name]
        self.productions.append(aug_prod)
        self.aug_prod_id = aug_prod.cnt # 存储增广产生式的ID

        # 初始闭包 I0
        eof_terminal_id = self.terminal_symbols.index("EOF") # EOF的终结符ID
        start_closure = Closure()
        start_closure.items.append(Item(self.aug_prod_id, 0, eof_terminal_id)) # [S' -> .Program, EOF]
        self.find_closures(start_closure) # 计算完整 I0
        
        self.closures = [start_closure] # 项目集族
        self.gos = [{}] # 状态转移 GOTO[i, X] = j

        idx = 0 # 处理队列索引
        while idx < len(self.closures):
            current_closure = self.closures[idx]
            # 收集当前闭包中所有可能的转移符号 X
            possible_transitions = {} # X_id -> Closure_of_items_after_shifting_X
            
            for item_in_closure in current_closure.items:
                prod = self.productions[item_in_closure.production_id]
                if item_in_closure.dot_pos < len(prod.to_ids): # 如果点号不在末尾
                    symbol_after_dot_id = prod.to_ids[item_in_closure.dot_pos]
                    # 为该符号创建一个新的项，点号后移一位
                    new_item_after_shift = Item(item_in_closure.production_id, 
                                                item_in_closure.dot_pos + 1, 
                                                item_in_closure.terminal_id)
                    
                    if symbol_after_dot_id not in possible_transitions:
                        possible_transitions[symbol_after_dot_id] = Closure()
                    # 添加到对应符号的核心项集
                    if new_item_after_shift not in possible_transitions[symbol_after_dot_id].items:
                         possible_transitions[symbol_after_dot_id].items.append(new_item_after_shift)

            # 对每个转移符号 X，计算 GOTO(current_closure, X)
            for symbol_id, core_items_closure in possible_transitions.items():
                self.find_closures(core_items_closure) # 计算这些核心项的完整闭包
                
                target_closure_index = -1
                try:
                    target_closure_index = self.closures.index(core_items_closure) # 检查是否已存在
                except ValueError:
                    target_closure_index = len(self.closures)
                    core_items_closure.cnt = target_closure_index
                    self.closures.append(core_items_closure)
                    self.gos.append({}) # 为新状态添加空的转移字典
                
                self.gos[idx][symbol_id] = target_closure_index # 记录 GOTO(idx, symbol_id) = target_closure_index
            idx += 1


    def find_gotos(self):
        # 此函数在你的代码中实际上是填充 ACTION 和 GOTO 表
        # find_gos 已经计算了状态和转移，这里是根据它们填充表
        T = len(self.terminal_symbols) # 终结符数量
        # 初始化 ACTION 和 GOTO 表
        self.action_table = [{} for _ in range(len(self.closures))]
        self.goto_table = [{} for _ in range(len(self.closures))]

        for i, closure_i in enumerate(self.closures): # i 是状态编号
            # 处理 GOTO 表 (非终结符的转移)
            # self.gos[i] 是一个字典 {symbol_id: target_state_j}
            for symbol_id, target_state_j in self.gos[i].items():
                if symbol_id >= T: # 如果是symbol_id是非终结符
                    self.goto_table[i][symbol_id] = target_state_j
            
            # 处理 ACTION 表 (移进和规约)
            for item in closure_i.items:
                prod = self.productions[item.production_id]
                
                # 情况1: 规约 A -> alpha . , la
                if item.dot_pos == len(prod.to_ids):
                    # 接受动作 S' -> S . , EOF
                    if item.production_id == self.aug_prod_id: # 如果是增广产生式
                        # 展望符必须是 EOF
                        if item.terminal_id == self.terminal_symbols.index("EOF"):
                            self.action_table[i][item.terminal_id] = (ACTION_ACC, 0) # (acc, 0)
                    else: # 普通规约
                        # ACTION[i, item.terminal_id] = (reduce, item.production_id)
                        # 检查冲突
                        if item.terminal_id in self.action_table[i] and \
                           self.action_table[i][item.terminal_id] != (ACTION_R, item.production_id):
                            existing_action, existing_val = self.action_table[i][item.terminal_id]

                            pass # 你是直接覆盖
                        self.action_table[i][item.terminal_id] = (ACTION_R, item.production_id)
                
                # 情况2: 移进 A -> alpha . a beta , la  (a 是终结符)
                else:
                    symbol_after_dot_id = prod.to_ids[item.dot_pos]
                    if symbol_after_dot_id < T: # 如果点后是终结符 a
                        # 且 GOTO(i, a) = j 存在
                        if symbol_after_dot_id in self.gos[i]:
                            target_state_j = self.gos[i][symbol_after_dot_id]
                            # ACTION[i, symbol_after_dot_id] = (shift, target_state_j)
                            # 检查冲突
                            if symbol_after_dot_id in self.action_table[i] and \
                               self.action_table[i][symbol_after_dot_id] != (ACTION_S, target_state_j):
                                existing_action, existing_val = self.action_table[i][symbol_after_dot_id]
                                # print(f"冲突在状态 {i}, 符号 {self.terminal_symbols[symbol_after_dot_id]}: 已有 {ActionType[existing_action]}{existing_val}, 新的 s{target_state_j}")
                                # LALR(1) 冲突解决：优先移进
                                if existing_action == ACTION_R: # 如果是S/R冲突，优先S
                                     self.action_table[i][symbol_after_dot_id] = (ACTION_S, target_state_j)
                                # else S/S冲突不应该发生，R/R冲突此逻辑不处理
                            elif symbol_after_dot_id not in self.action_table[i]: # 如果没有冲突，直接设置
                                self.action_table[i][symbol_after_dot_id] = (ACTION_S, target_state_j)


    def parse(self, lex_tokens_input): # 重命名参数以示区分
        comments = {tokenType.S_COMMENT,
                    tokenType.LM_COMMENT, tokenType.RM_COMMENT}
        
        toks_for_parsing = [
            t for t in lex_tokens_input if t["prop"] not in comments # 移除注释
        ]
        
        terminal_symbol_names_for_parsing = [tokenType_to_terminal(t["prop"]) for t in toks_for_parsing if t["prop"] != tokenType.EOF] + ["EOF"]

        try:
            terminal_ids_for_parsing = [self.get_id(s_name) for s_name in terminal_symbol_names_for_parsing]
        except ValueError as e:
            return {"error": f"符号ID查找失败: {str(e)}。请检查终结符定义。", "loc": None}

        # 分析栈，每个元素是 {'state': state_id, 'tree': syntax_tree_node, 'attrs': semantic_attributes}
        # 初始时，栈底是状态0，EOF的tree和attrs是象征性的
        stack = [{"state": 0, "tree": {"root": "InitialStackMarker"}, "attrs": {'token_obj': None, 'code':[]}}] 
        
        current_token_idx = 0 # 指向 toks_for_parsing (原始token列表，包含EOF前所有有效token)
                              # 和 terminal_ids_for_parsing (符号ID列表，包含EOF的ID)
        
        while True:
            current_state = stack[-1]["state"]
            # lookahead_symbol_id 是下一个输入符号的ID
            lookahead_symbol_id = terminal_ids_for_parsing[current_token_idx] 
            
            if lookahead_symbol_id not in self.action_table[current_state]:
                # 语法错误
                error_token_obj = toks_for_parsing[current_token_idx] if current_token_idx < len(toks_for_parsing) else {"prop": "EOF", "content": "#", "loc": {"row": -1, "col": -1}} # 防止索引越界
                
                expected_symbols = []
                for term_id in self.action_table[current_state].keys():
                    expected_symbols.append(self.terminal_symbols[term_id])
                
                return {
                    "error": f"意外的token {error_token_obj['prop']} ('{error_token_obj['content']}'). 可能的期望是: {', '.join(expected_symbols) if expected_symbols else '无 (语法结构不完整?)'}",
                    "loc": error_token_obj["loc"],
                    "token": error_token_obj
                }
            
            action, value = self.action_table[current_state][lookahead_symbol_id]
            
            if action == ACTION_S:  # 移进 (Shift)
                current_actual_token_obj = toks_for_parsing[current_token_idx]
                
                initial_terminal_attrs = {
                    'token_obj': current_actual_token_obj, # 存储原始token对象，包含content, prop, loc
                    'code': [] # 终结符本身不产生新的四元式序列
                }
                # 设置初始的 type 和 place
                if current_actual_token_obj['prop'] == tokenType.INTEGER_CONSTANT:
                    initial_terminal_attrs['type'] = 'i32'
                    try:
                        initial_terminal_attrs['place'] = int(current_actual_token_obj['content'])
                    except ValueError:
                        # 理论上词法分析阶段应该保证这是个有效整数
                        initial_terminal_attrs['place'] = 0 # 或其他错误标记
                        # TODO：可以考虑在此处报告一个内部错误
                elif current_actual_token_obj['prop'] == tokenType.IDENTIFIER:
                    initial_terminal_attrs['name'] = current_actual_token_obj['content']

                stack.append({
                    "state": value, # value 是移进后的新状态
                    "tree": {"root": terminal_symbol_names_for_parsing[current_token_idx]}, # 语法树节点
                    "attrs": initial_terminal_attrs # 附带语义属性
                })
                current_token_idx += 1

            elif action == ACTION_R:  # 规约 (Reduce)
                production_to_reduce = self.productions[value] # value 是产生式编号
                # print(production_to_reduce.from_id)
                # input(production_to_reduce.to_ids)
                
                children_syntax_nodes = [] # 用于构造语法树
                children_semantic_attrs = [] # 用于传递给语义分析

                for _ in production_to_reduce.to_ids: # p.to_ids 是产生式右部符号的ID列表
                    popped_item = stack.pop()
                    children_syntax_nodes.insert(0, popped_item["tree"])
                    # 确保即使没有 'attrs' 也能安全获取，提供默认值
                    children_semantic_attrs.insert(0, popped_item.get("attrs", {'code': [], 'token_obj': popped_item.get('token_obj')}))
                
                lhs_symbol_id = production_to_reduce.from_id
                # from_id 是全局ID, 需要转换为 non_terminal_symbols 的索引
                lhs_symbol_name = self.non_terminal_symbols[lhs_symbol_id - len(self.terminal_symbols)]
                
                rhs_symbol_names = []
                if not production_to_reduce.to_ids: # Epsilon 产生式
                    rhs_symbol_names.append("epsilon")
                else:
                    for symbol_id_in_rhs in production_to_reduce.to_ids:
                        if symbol_id_in_rhs < len(self.terminal_symbols): # 终结符
                            rhs_symbol_names.append(self.terminal_symbols[symbol_id_in_rhs])
                        else: # 非终结符
                            rhs_symbol_names.append(self.non_terminal_symbols[symbol_id_in_rhs - len(self.terminal_symbols)])
                
                production_rule_str = f"{lhs_symbol_name} -> {' '.join(rhs_symbol_names)}"
                # print(f"DEBUG: Reducing by rule: {production_rule_str}") # 添加这行来进行调试


                # approx_line_num = 1 # 默认
                approx_loc = {'row': '?', 'col': '?'}
                # 尝试从规约的第一个子节点的token获取行号
                if children_semantic_attrs and children_semantic_attrs[0] and children_semantic_attrs[0].get('token_obj'):
                    first_child_token = children_semantic_attrs[0]['token_obj']
                    if first_child_token and 'loc' in first_child_token and first_child_token['loc']:
                        approx_loc = first_child_token['loc']
                # 或者从当前的lookahead token获取
                elif current_token_idx < len(toks_for_parsing):
                     lookahead_token_for_line = toks_for_parsing[current_token_idx]
                     if lookahead_token_for_line and 'loc' in lookahead_token_for_line and lookahead_token_for_line['loc']:
                         approx_loc = lookahead_token_for_line['loc']
                
                new_lhs_attributes = {} # 初始化
                try:
                    # print(production_rule_str)
                    # print(children_semantic_attrs)
                    # input(approx_loc)
                    new_lhs_attributes = self.semantic_analyzer.dispatch_semantic_action(
                        production_rule_str,
                        children_semantic_attrs,
                        approx_loc
                    )
                    # self.semantic_analyzer.print_quadruples() # 打印四元式 (调试用)
                    # self.semantic_analyzer.print_symbol_table() # 打印符号表 (调试用)
                    # input()
                except SemanticError as se:
                    # 报告语义错误并停止分析
                    final_loc = se.loc if se.loc and 'row' in se.loc and se.loc['row'] != '?' else approx_loc
                    return {
                        "error": f"语义错误: {se.message}",
                        "loc": final_loc, # 尝试获取列信息
                        "rule": production_rule_str,
                        "semantic_error": True # 标记为语义错误
                    }

                previous_top_state = stack[-1]["state"]
                goto_non_terminal_id = production_to_reduce.from_id # 左部非终结符的ID
                
                if goto_non_terminal_id not in self.goto_table[previous_top_state]:
                    return {
                        "error": f"内部错误: GOTO 表中状态 {previous_top_state} 对非终结符 {lhs_symbol_name} (ID: {goto_non_terminal_id}) 无转移。",
                        "loc": approx_loc 
                    }

                next_state_after_reduce = self.goto_table[previous_top_state][goto_non_terminal_id]
                
                stack.append({
                    "state": next_state_after_reduce,
                    "tree": {
                        "root": lhs_symbol_name,
                        "children": children_syntax_nodes,
                    },
                    "attrs": new_lhs_attributes # 左部非终glie符的语义属性
                })

            elif action == ACTION_ACC:  # 接受 (Accept)
                final_tree = stack[-1]["tree"] 
                final_attrs = stack[-1]["attrs"] # 这是 Program 符号的属性

                # 使用 final_attrs 中聚合的 'code' 作为最终的四元式列表
                quads_to_return = final_attrs.get('code', [])
                
                # 调试：打印将要返回的四元式
                # print("\n--- Final Quads from Parser (final_attrs['code']) ---")
                # if quads_to_return:
                # for i, q_obj in enumerate(quads_to_return):
                # print(f"{i:03d}: {q_obj}") # 假设 Quadruple 有 __str__
                # else:
                # print(" <empty>")
                # print("----------------------------------------------------")

                return {
                    "syntax_tree": final_tree,
                    "quadruples": quads_to_return,
                    "symbol_table_debug_print": self.semantic_analyzer.get_symbol_table_string_for_debug()
                }
            
            else: # 不应该发生的未知动作
                 return {
                    "error": f"内部错误: 未知的 ACTION 表动作 {action}",
                    "loc": None
                }
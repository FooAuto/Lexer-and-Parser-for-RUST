from enum import Enum
from lexer.token import tokenType


class SymbolType(Enum):
    VARIABLE = 1
    FUNCTION = 2
    PARAMETER = 3
    ARRAY = 4
    TUPLE = 5
    REFERENCE = 6  # 用于 &T 和 &mut T


class Quadruple:
    def __init__(self, op, arg1, arg2, result):
        self.op = op
        self.arg1 = arg1
        self.arg2 = arg2
        self.result = result

    def __str__(self):
        return (
            f"({self.op}, {self.arg1 or '_'}, {self.arg2 or '_'}, {self.result or '_'})"
        )


class SymbolTableEntry:
    def __init__(
        self,
        name,
        sym_type,
        data_type,
        scope_level,
        is_mutable=False,
        initialized=True,
        extra_info=None,
    ):
        self.name = name  # 名字
        self.sym_type = sym_type  # id类型 SymbolTypes
        self.data_type = data_type  # 实际数据类型，比如i32
        self.scope_level = scope_level  # 作用域
        self.is_mutable = is_mutable  # 是否可修改
        self.initialized = initialized  # 是否初始化
        self.extra_info = (
            extra_info if extra_info is not None else {}
        )  # For func params, array/tuple details, reference details
        # extra_info for FUNCTION: {'params': [{'name': 'p1', 'type': 'i32', 'is_mutable': False}, ...], 'return_type': 'i32'}
        # extra_info for ARRAY: {'element_type': 'i32', 'length': 3}
        # extra_info for TUPLE: {'element_types': ['i32', 'bool']}
        # extra_info for REFERENCE: {'target_type': 'i32', 'is_mutable_ref': True/False}
        self.line_declared = -1  # Placeholder, set this during declaration
        self.active_borrows = {"mutable": 0, "immutable": 0}  # For borrow checking


class SemanticError(Exception):
    def __init__(self, message, loc=None):
        self.message = message
        self.loc = loc if loc else {'row': '?', 'col': '?'}
        super().__init__(
            f"Semantic Error: {message}" + (f" at line {self.loc.get('row', '?')}" if loc else "")
        )


# 实际语义分析执行类
class SemanticAnalyzer:
    def __init__(self):
        self.symbol_tables = [{}]
        self.current_scope_level = 0
        self.quadruples = []
        self.temp_var_count = 0
        self.label_count = 0
        self.current_function = None  # 当前函数的返回值
        self.loop_stack = []  # For break/continue

    def _new_temp(self):
        self.temp_var_count += 1
        return f"t{self.temp_var_count}"

    def _new_label(self):
        self.label_count += 1
        return f"L{self.label_count}"

    def add_quad(self, op, arg1=None, arg2=None, result=None):
        self.quadruples.append(Quadruple(op, arg1, arg2, result))
        return result

    def enter_scope(self):
        self.current_scope_level += 1
        self.symbol_tables.append({})

    def exit_scope(self):
        if self.current_scope_level > 0:
            self.symbol_tables.pop()
            self.current_scope_level -= 1
        else:
            raise SemanticError("Attempted to exit global scope.")

    def add_symbol(
        self,
        name,
        sym_type,
        data_type,
        line_num,
        is_mutable=False,
        initialized=True,
        extra_info=None,
    ):
        if name in self.symbol_tables[self.current_scope_level]:
            # Handle shadowing: if a symbol with the same name exists in the current scope, it's an error
            # Rust allows shadowing, so we actually overwrite.
            # However, the PDF implies some re-declaration might be errors.
            # For now, we allow shadowing by overwriting.
            # If strict "no re-declaration in same scope" is needed, add a check here.
            # TODO：目前这里对于二次申明是覆盖第一次，认为放行。可能需要进一步考虑
            pass  # Shadowing is allowed by overwriting.

        entry = SymbolTableEntry(
            name,
            sym_type,
            data_type,
            self.current_scope_level,
            is_mutable,
            initialized,
            extra_info,
        )
        entry.line_declared = line_num
        self.symbol_tables[self.current_scope_level][name] = entry
        return entry

    def lookup_symbol(self, name, line_num=None):
        for i in range(self.current_scope_level, -1, -1):
            if name in self.symbol_tables[i]:
                return self.symbol_tables[i][name]
        raise SemanticError(f"Variable '{name}' not declared.", line_num)

    def lookup_function(self, name, line_num=None):
        entry = self.lookup_symbol(name, line_num)
        if entry.sym_type != SymbolType.FUNCTION:
            raise SemanticError(f"'{name}' is not a function.", line_num)
        return entry

    def get_type_name(self, data_type):
        """Helper to get a string representation of a complex type."""
        if isinstance(data_type, str):
            return data_type
        elif isinstance(data_type, list):  # Array or Reference
            if data_type[0] == "[":  # Array: ['[', type, size]
                return f"[{self.get_type_name(data_type[1])}; {data_type[2]}]"
            elif data_type[0] == "&":  # Reference: ['&', type] or ['&mut', type]
                if len(data_type) == 2:  # Immutable reference
                    return f"&{self.get_type_name(data_type[1])}"
                else:  # Mutable reference ['&mut', type]
                    return f"&mut {self.get_type_name(data_type[1])}"
        elif isinstance(data_type, tuple):  # Tuple: (type1, type2, ...)
            return f"({', '.join(self.get_type_name(t) for t in data_type)})"
        return "unknown_type"

    def check_type_compatibility(self, type1, type2, line_num, allow_ref_deref=True, error_message_override=None):
        """
        Checks if type2 can be assigned to or used where type1 is expected.
        Includes basic reference compatibility (e.g., &T can be used for &T, T for *&T).
        """
        s_type1 = self.get_type_name(type1)
        s_type2 = self.get_type_name(type2)

        if s_type1 == s_type2:
            return True

        if type1 == "unknown_inferred":
            # 如果左侧是待推断类型，且右侧是 void，这是不允许的
            if type2 == "void":
                err_msg = error_message_override or f"Cannot assign a 'void' value to a variable whose type is to be inferred."
                raise SemanticError(err_msg, line_num)
            return True # 允许推断为任何非 void 类型

        if type2 == "void" and type1 != "void":
            err_msg = error_message_override or f"Cannot assign a 'void' value to a variable of type {s_type1}."
            raise SemanticError(err_msg, line_num)


        # Dereferencing: if type1 is T and type2 is &T or &mut T
        if allow_ref_deref:
            if isinstance(type2, list) and type2[0] in [
                "&",
                "&mut",
            ]:
                deref_type2 = (
                    type2[1] if type2[0] == "&" else type2[1]
                )
                if self.get_type_name(type1) == self.get_type_name(deref_type2):
                    pass

        default_err_msg = f"Type mismatch: expected {s_type1}, found {s_type2}."
        raise SemanticError(error_message_override or default_err_msg, line_num)

    # 罗列具体的语义规则与语义分析
    # Rule 0.1: <变量声明内部> -> mut <ID>
    # Rule 6.1: <变量声明内部> -> <ID>
    def process_variable_decl_internal(self, p_id, is_mutable_token, line_num):
        id_name = p_id["content"]
        is_mut = True if is_mutable_token else False
        return {"name": id_name, "is_mutable": is_mut, "line": p_id["loc"]["row"]}

    # Rule 0.2: <类型> -> i32 | & <类型> | & mut <类型> | '[' <类型> ';' <NUM> ']' | '(' <元组类型内部> ')'
    def process_type(self, type_token_or_structure, line_num):
        # type_token_or_structure can be:
        #   - 'i32' (string from token)
        #   - {'op': '&', 'type': processed_type}
        #   - {'op': '&mut', 'type': processed_type}
        #   - {'op': 'array', 'element_type': processed_type, 'size': num_val}
        #   - {'op': 'tuple', 'element_types': [processed_type1, ...]}
        # Returns the internal representation of the type.
        if (
            isinstance(type_token_or_structure, str)
            and type_token_or_structure == "i32"
        ):
            return "i32"
        elif isinstance(type_token_or_structure, dict):
            op = type_token_or_structure["op"]
            if op == "&":
                return [
                    "&",
                    self.process_type(type_token_or_structure["type"], line_num),
                ]
            elif op == "&mut":
                return [
                    "&mut",
                    self.process_type(type_token_or_structure["type"], line_num),
                ]
            elif op == "array":
                size = int(type_token_or_structure["size"])
                if size <= 0:
                    raise SemanticError("Array size must be positive.", line_num)
                return [
                    "[",
                    self.process_type(
                        type_token_or_structure["element_type"], line_num
                    ),
                    size,
                ]
            elif op == "tuple":
                return tuple(
                    self.process_type(t, line_num)
                    for t in type_token_or_structure["element_types"]
                )
        raise SemanticError(
            f"Unknown type structure: {type_token_or_structure}", line_num
        )

    # Rule 1.1, 1.5, 7.2: Function Declaration
    def process_function_declaration_header(
        self, fn_name_token, params_list, return_type_processed, line_num
    ):
        fn_name = fn_name_token["content"]

        # 检查函数是否已在全局作用域（通常是 scope 0）被声明
        # 我们直接检查 self.symbol_tables[0]，而不是用 lookup_symbol，因为它找不到时会抛错
        if (
            fn_name in self.symbol_tables[0]
            and self.symbol_tables[0][fn_name].sym_type == SymbolType.FUNCTION
        ):
            # 如果确实找到了一个同名且类型为FUNCTION的符号，在 process_function_body_end 之后再检查是否重复定义
            # 或者，如果你希望严格禁止在任何内部作用域“覆盖”全局函数，可以在这里报错
            # 但通常函数声明主要关注全局作用域的冲突
            # 为了允许不同作用域的 shadowing (虽然函数通常在全局)，或者更精细的控制，
            # 这里的检查可以调整。
            # 但对于顶层函数，如果已存在，则不应重复添加。
            raise SemanticError(
                f"Function '{fn_name}' already declared at line {self.symbol_tables[0][fn_name].line_declared}.",
                line_num,
            )

        param_info_for_symtable = []
        for p_attr in params_list:  # params_list 应该是直接可用的列表
            param_info_for_symtable.append(
                {
                    "name": p_attr["name"],
                    "type": p_attr["type"],
                    "is_mutable": p_attr["is_mutable"],
                }
            )

        extra_info = {
            "params": param_info_for_symtable,
            "return_type": return_type_processed,
        }
        self.add_symbol(
            fn_name,
            SymbolType.FUNCTION,
            return_type_processed,
            line_num,
            extra_info=extra_info,
        )

        entry_label = self._new_label()
        self.add_quad(
            "FUNC_BEGIN", arg1=fn_name, result=entry_label
        )  # 添加到 self.quadruples
        quad_func_begin = self.quadruples.pop()  # 从 self.quadruples 中取出

        self.current_function = {
            "name": fn_name,
            "return_type": return_type_processed,
            "entry_label": entry_label,
            "params_attrs": params_list,
        }
        self.enter_scope()
        for p_attr in params_list:
            self.add_symbol(
                p_attr["name"],
                SymbolType.PARAMETER,
                p_attr["type"],
                p_attr["line"],
                is_mutable=p_attr["is_mutable"],
                initialized=True,
            )

        return {
            "name": fn_name,
            "label": entry_label,
            "return_type": return_type_processed,
            "token_obj": fn_name_token,
            "code": [quad_func_begin],
        }  # 将取出的四元式放入返回的 'code' 列表

    def process_function_body_end(
        self, func_name, line_num, last_expr_attrs_for_implicit_return=None
    ):
        if self.current_function and self.current_function["name"] == func_name:
            # 创建 FUNC_END 四元式
            quad_func_end = Quadruple("FUNC_END", func_name, None, None)

            self.exit_scope()
            self.current_function = None
            return {"code": [quad_func_end]}  # 返回包含 FUNC_END 的 'code' 列表
        else:
            # 此处可以抛出错误或返回空的 code，取决于你的错误处理策略
            # 为了安全，如果 mismatched, 返回空 code 或抛异常
            # raise SemanticError(f"Mismatched function end for '{func_name}'. Expected '{self.current_function['name'] if self.current_function else 'None'}'.", line_num)
            # 或者如果current_function为None但尝试结束一个函数
            if not self.current_function:
                raise SemanticError(
                    f"Attempting to end function '{func_name}' but no function is current.",
                    line_num,
                )
            # 如果名字不匹配
            raise SemanticError(
                f"Mismatched function end. Expected '{self.current_function['name']}', got '{func_name}'.",
                line_num,
            )
        # return {'code': []} # 理论上不应在正常流程到达这里

    # Rule 1.3: return ;
    # Rule 1.5: return <expr> ;
    # Rule 7.4: break <expr> ; (for loop expressions, context-dependent)
    def process_return_statement(self, expr_attrs, line_num, is_break_expr=False):
        # expr_attrs: {'type': type, 'place': temp_var_or_const, 'code': [quads]} or None for 'return;'
        op = "BREAK_VAL" if is_break_expr else "RETURN_VAL"
        target_type_container = None

        if is_break_expr:
            if not self.loop_stack or not self.loop_stack[-1].get("is_expr_loop"):
                raise SemanticError(
                    "'break <expression>;' can only be used inside a loop expression.",
                    line_num,
                )
            loop_ctx = self.loop_stack[-1]
            if loop_ctx.get("expr_type") == "unknown_inferred":
                if not expr_attrs:  # break; in loop expr
                    raise SemanticError(
                        "Loop expression 'break' must provide a value.", line_num
                    )
                loop_ctx["expr_type"] = expr_attrs[
                    "type"
                ]  # Infer loop type from first break
            target_type_container = loop_ctx["expr_type"]
        else:  # Regular return
            if not self.current_function:
                raise SemanticError("Return statement outside of function.", line_num)
            target_type_container = self.current_function["return_type"]

        quads = []
        if expr_attrs:
            quads.extend(expr_attrs.get("code", []))
            self.check_type_compatibility(
                target_type_container, expr_attrs["type"], line_num
            )
            self.add_quad(op, arg1=expr_attrs["place"])
            quads.append(self.quadruples[-1])
            return {
                "type": expr_attrs["type"],
                "place": expr_attrs["place"],
                "code": quads,
            }  # For expression blocks
        else:  # return; or break; (break; is not allowed in loop expr)
            if is_break_expr:
                raise SemanticError(
                    "Loop expression 'break' must provide a value.", line_num
                )

            if target_type_container != "void":
                raise SemanticError(
                    f"Function '{self.current_function['name']}' expects a return value of type {self.get_type_name(target_type_container)}.",
                    line_num,
                )
            self.add_quad("RETURN")  # For void return
            return {"type": "void", "place": None, "code": quads}

    # Rule 2.1: let <var_decl_internal> : <type> ;
    # Rule 2.1: let <var_decl_internal> ; (Type inference needed)
    def process_variable_declaration(
        self, var_decl_internal_attrs, type_attrs, line_num
    ):
        # var_decl_internal_attrs: {'name': str, 'is_mutable': bool, 'line': int}
        # type_attrs: {'type': processed_type, 'code': []} or None
        var_name = var_decl_internal_attrs["name"]
        is_mutable = var_decl_internal_attrs["is_mutable"]
        decl_line = var_decl_internal_attrs["line"]

        var_type = "unknown_inferred"
        quads = []

        if type_attrs:
            var_type = type_attrs["type"]
            if "code" in type_attrs:
                quads.extend(type_attrs["code"])  # e.g. for array type def

        self.add_symbol(
            var_name,
            SymbolType.VARIABLE,
            var_type,
            decl_line,
            is_mutable,
            initialized=False,
        )
        # No direct quadruple for 'let x: i32;' until assignment, unless for memory allocation planning
        # For now, symbol table entry is enough.
        return {
            "name": var_name,
            "type": var_type,
            "is_mutable": is_mutable,
            "code": quads,
            "place": var_name,
        }

    # Rule 2.2: <assignable> = <expr> ;
    def process_assignment(self, assignable_attrs, expr_attrs, line_num):
        quads = []
        quads.extend(assignable_attrs.get("code", []))
        quads.extend(expr_attrs.get("code", []))

        if not assignable_attrs.get("is_lvalue", False):
            raise SemanticError(
                f"Cannot assign to non-lvalue '{assignable_attrs.get('name', 'expression')}'.",
                line_num,
            )

        lvalue_handled = False
        target_type_for_check = None # 用于存储左值的类型

        # 情况1: 简单变量赋值 (例如: x = 10)
        if assignable_attrs.get("sym_type") in [SymbolType.VARIABLE, SymbolType.PARAMETER]:
            lvalue_entry = self.lookup_symbol(assignable_attrs["name"], line_num)

            if not lvalue_entry.is_mutable and lvalue_entry.initialized:
                raise SemanticError(
                    f"Cannot assign to immutable variable '{lvalue_entry.name}'.",
                    line_num,
                )

            target_type_for_check = lvalue_entry.data_type
            if lvalue_entry.data_type == "unknown_inferred":
                # 如果左值类型之前是未推断的，现在用右值的类型来确定它
                self.check_type_compatibility(lvalue_entry.data_type, expr_attrs["type"], line_num,
                    error_message_override=f"Cannot infer type of variable '{lvalue_entry.name}' from a void expression."
                )
                lvalue_entry.data_type = expr_attrs["type"]
                target_type_for_check = lvalue_entry.data_type # 更新用于后续检查的类型
            
            lvalue_entry.initialized = True
            
            # self.check_type_compatibility(lvalue_entry.data_type, expr_attrs["type"], line_num)
            
            self.add_quad("ASSIGN", expr_attrs["place"], result=assignable_attrs["place"])
            quads.append(self.quadruples.pop())
            lvalue_handled = True

        # 情况2: 向内存地址赋值 (例如: *ptr = 10, array[idx] = 10, tuple.field = 10)
        elif assignable_attrs.get("is_lvalue_address"):
            is_array_or_tuple_element = assignable_attrs.get("sym_type") in [SymbolType.ARRAY, SymbolType.TUPLE]

            if is_array_or_tuple_element:
                if not assignable_attrs.get("base_is_mutable"):
                    raise SemanticError(
                        f"Cannot assign to element of immutable base '{assignable_attrs.get('name', 'container')}'.",
                        line_num,
                    )
            else: 
                if not assignable_attrs.get("is_mutable"):
                    raise SemanticError(
                        f"Cannot assign to content of dereferenced immutable reference/pointer.",
                        line_num,
                    )
            
            target_type_for_check = assignable_attrs["type"] # 左值（如 *ptr 或 arr[i]）的类型
            
            self.add_quad("STORE", expr_attrs["place"], assignable_attrs["place"])
            quads.append(self.quadruples.pop())
            lvalue_handled = True
        
        if not lvalue_handled:
            raise SemanticError(
                f"Internal Error: Unhandled LValue structure in assignment. Attributes: {assignable_attrs}", line_num
            )

        if target_type_for_check is None: # 理论上不应发生
            raise SemanticError("Internal error: Target type for assignment not determined.", line_num)

        self.check_type_compatibility(target_type_for_check, expr_attrs["type"], line_num,
            error_message_override=f"Cannot assign expression of type {self.get_type_name(expr_attrs['type'])} to lvalue of type {self.get_type_name(target_type_for_check)}."
        )
        
        return {"code": quads}

    # Rule 2.3: let <var_decl_internal> : <type> = <expr> ;
    # Rule 2.3: let <var_decl_internal> = <expr> ;
    def process_variable_declaration_assignment(
        self, var_decl_internal_attrs, type_attrs, expr_attrs, line_num
    ):
        var_name = var_decl_internal_attrs["name"]
        is_mutable = var_decl_internal_attrs["is_mutable"]
        decl_line = var_decl_internal_attrs["line"]
        quads = []
        quads.extend(expr_attrs.get("code", []))

        var_type = expr_attrs["type"] # 先用表达式的类型作为推断类型

        # 如果表达式类型是
        if expr_attrs["type"] == "void":
            pass # 让 check_type_compatibility 决定

        if type_attrs:  # 如果给定了显式类型
            explicit_type = type_attrs["type"]
            if "code" in type_attrs:
                quads.extend(type_attrs["code"])
            
            self.check_type_compatibility(explicit_type, expr_attrs["type"], line_num,
                error_message_override=f"Cannot initialize variable '{var_name}' of type {self.get_type_name(explicit_type)} with an expression of type {self.get_type_name(expr_attrs['type'])}."
            )
            var_type = explicit_type  # 使用声明的类型
        elif var_type == "void": # 如果没有显式类型，且推断出是 void
             raise SemanticError(
                f"Cannot declare variable '{var_name}' with inferred type 'void' from a void expression.", line_num
            )


        self.add_symbol(
            var_name,
            SymbolType.VARIABLE,
            var_type,
            decl_line,
            is_mutable,
            initialized=True,
        )
        self.add_quad("ASSIGN", expr_attrs["place"], result=var_name)
        quads.append(self.quadruples.pop())

        return {
            "name": var_name,
            "type": var_type,
            "is_mutable": is_mutable,
            "code": quads,
            "place": var_name,
        }

    # Rule 3.1 <元素> -> <NUM> | <可赋值元素> | ( <表达式> )
    def process_element(self, element_token_or_attrs, line_num):
        # element_token_or_attrs:
        #  - if NUM: {'type': tokenType.INTEGER_CONSTANT, 'content': '123', 'loc': ...}
        #  - if <可赋值元素> (ID, array_access, tuple_access): result of process_assignable_element
        #  - if (<表达式>): result of process_expression (expr_attrs)

        if (
            isinstance(element_token_or_attrs, dict)
            and "prop" in element_token_or_attrs
        ):  # Terminal token like NUM
            token_prop = element_token_or_attrs["prop"]
            token_content = element_token_or_attrs["content"]
            if token_prop == tokenType.INTEGER_CONSTANT:
                # For constants, 'place' is the constant value itself
                return {"type": "i32", "place": int(token_content), "code": []}
            # Add other constants like CHAR_CONSTANT, STRING_CONSTANT if they are expressions
            else:
                raise SemanticError(
                    f"Unsupported terminal in expression: {token_content}", line_num
                )

        # If it's from <可赋值元素> or (<表达式>), it's already processed attrs
        # For <可赋值元素>, it needs to be treated as an R-value.
        # 'place' could be a variable name or a temporary holding an array/tuple element's value.
        # A 'LOAD' quad might be needed if 'place' is a direct variable name and we need its value in a temp.
        # For simplicity, if 'place' is a variable, downstream ops will use it directly.
        # If it's a complex l-value (like a[i]), its 'place' is already a temp from address calculation.
        elif (
            isinstance(element_token_or_attrs, dict)
            and "type" in element_token_or_attrs
        ):
            # If it's an LValue used as RValue, ensure it's initialized
            if "name" in element_token_or_attrs and not element_token_or_attrs.get(
                "is_temp_lvalue"
            ):
                entry = self.lookup_symbol(element_token_or_attrs["name"], line_num)
                if not entry.initialized:
                    raise SemanticError(
                        f"Variable '{entry.name}' used before initialization.", line_num
                    )

                # If the LValue was an array/tuple itself, its 'place' is the name.
                # If it was an element access, its 'place' is a temp holding the value/address.
                # We might need to generate a load instruction if the 'place' is an address.
                # For now, assume 'place' from process_assignable_element holds the value or is directly usable.
                if element_token_or_attrs.get(
                    "is_lvalue_address"
                ):  # from array/tuple element access not yet dereferenced
                    temp_val = self._new_temp()
                    current_quads = element_token_or_attrs.get("code", [])
                    current_quads.append(
                        Quadruple(
                            "LOAD_FROM_ADDR",
                            element_token_or_attrs["place"],
                            None,
                            temp_val,
                        )
                    )
                    return {
                        "type": element_token_or_attrs["type"],
                        "place": temp_val,
                        "code": current_quads,
                    }

            return (
                element_token_or_attrs  # Pass through attrs from (expr) or assignable
            )
        else:
            raise SemanticError("Invalid element structure in expression.", line_num)

    # Rule 0.3: <可赋值元素> -> <ID>
    # Rule 8.2: <可赋值元素> -> <元素> '[' <表达式> ']'
    # Rule 9.2: <可赋值元素> -> <元素> '.' <NUM>
    def process_assignable_element(self, structure, line_num):
        # structure:
        #   - {'type': 'id', 'token': id_token}
        #   - {'type': 'array_access', 'base': element_attrs, 'index': expr_attrs}
        #   - {'type': 'tuple_access', 'base': element_attrs, 'index_token': num_token}
        # Returns: {'name': str, 'type': type, 'is_lvalue': True, 'is_mutable': bool, 'place': ..., 'code': [], 'sym_type': ..., 'base_is_mutable': ...}
        stype = structure["type"]
        quads = []

        if stype == "id":
            id_token = structure["token"]
            id_name = id_token["content"]
            entry = self.lookup_symbol(id_name, line_num)
            # For LValue use, place is the name. For RValue, its value might be loaded.
            return {
                "name": id_name,
                "type": entry.data_type,
                "is_lvalue": True,
                "is_mutable": entry.is_mutable,
                "place": id_name,
                "code": [],
                "sym_type": entry.sym_type,
                "initialized": entry.initialized,
            }
        elif stype == "array_access":
            base_attrs = structure["base"]  # Comes from process_element
            index_attrs = structure["index"]  # Comes from process_expression

            quads.extend(base_attrs.get("code", []))
            quads.extend(index_attrs.get("code", []))

            base_entry = None
            # Base can be a variable or a result of another operation (e.g. function call returning array, or *ref_to_array)
            if "name" in base_attrs and not base_attrs.get(
                "is_temp_lvalue"
            ):  # if base_attrs['place'] is a direct variable name
                base_entry = self.lookup_symbol(base_attrs["name"], line_num)
                base_type = base_entry.data_type
                base_is_mut = base_entry.is_mutable
                base_place = base_entry.name
            else:  # Base is temporary, e.g. from *(&mut arr)[i] or func_call()[i]
                base_type = base_attrs["type"]
                base_is_mut = base_attrs.get(
                    "is_mutable", True
                )  # Temp results are often mutable in effect
                base_place = base_attrs["place"]

            if not (isinstance(base_type, list) and base_type[0] == "["):
                raise SemanticError(
                    f"Cannot apply index operator to non-array type '{self.get_type_name(base_type)}'.",
                    line_num,
                )
            if index_attrs["type"] != "i32":
                raise SemanticError(
                    f"Array index must be i32, found {self.get_type_name(index_attrs['type'])}.",
                    line_num,
                )

            element_type = base_type[1]
            array_len = base_type[2]

            # Runtime bounds check (conceptual quad, can be expanded)
            # self.add_quad("BOUNDS_CHECK", index_attrs['place'], array_len, None)
            # quads.append(self.quadruples.pop())

            # Address calculation: result_addr = base_addr + index * element_size
            # element_size needs to be known. For i32, assume 1 unit for simplicity here.
            # More realistically, this would be platform dependent.
            addr_temp = self._new_temp()
            self.add_quad(
                "ARRAY_ACCESS_ADDR", base_place, index_attrs["place"], addr_temp
            )
            quads.append(self.quadruples.pop())

            return {
                "name": base_attrs.get(
                    "name", "array_element"
                ),  # Name for error reporting
                "type": element_type,
                "is_lvalue": True,
                "is_mutable": base_is_mut,  # Element mutability depends on base array
                "place": addr_temp,
                "code": quads,
                "sym_type": SymbolType.ARRAY,
                "base_is_mutable": base_is_mut,
                "is_lvalue_address": True,
            }

        elif stype == "tuple_access":
            base_attrs = structure["base"]
            index_val = int(structure["index_token"]["content"])
            quads.extend(base_attrs.get("code", []))

            base_entry = None
            if "name" in base_attrs and not base_attrs.get("is_temp_lvalue"):
                base_entry = self.lookup_symbol(base_attrs["name"], line_num)
                base_type = base_entry.data_type
                base_is_mut = base_entry.is_mutable
                base_place = base_entry.name
            else:
                base_type = base_attrs["type"]
                base_is_mut = base_attrs.get("is_mutable", True)
                base_place = base_attrs["place"]

            if not isinstance(base_type, tuple):
                raise SemanticError(
                    f"Cannot apply '.' operator to non-tuple type '{self.get_type_name(base_type)}'.",
                    line_num,
                )

            if not (0 <= index_val < len(base_type)):
                raise SemanticError(
                    f"Tuple index {index_val} out of bounds for tuple of length {len(base_type)}.",
                    line_num,
                )

            element_type = base_type[index_val]
            addr_temp = self._new_temp()  # Placeholder for tuple element access
            self.add_quad("TUPLE_ACCESS_ADDR", base_place, index_val, addr_temp)
            quads.append(self.quadruples.pop())

            return {
                "name": base_attrs.get("name", "tuple_element"),
                "type": element_type,
                "is_lvalue": True,
                "is_mutable": base_is_mut,
                "place": addr_temp,
                "code": quads,
                "sym_type": SymbolType.TUPLE,
                "base_is_mutable": base_is_mut,
                "is_lvalue_address": True,
            }
        raise SemanticError(f"Unknown assignable element structure: {stype}", line_num)

    # Rule 3.2: Arithmetic and Comparison ops
    def process_binary_op(self, op_token, left_attrs, right_attrs, line_num):
        # op_token: {'content': '+', 'prop': tokenType.PLUS, ...}
        # left_attrs, right_attrs: {'type': type, 'place': temp_or_const, 'code': []}
        op_str = op_token["content"]
        quads = []
        quads.extend(left_attrs.get("code", []))
        quads.extend(right_attrs.get("code", []))

        # Type checking (assuming i32 for arithmetic, bool for comparison result)
        if op_str in ["+", "-", "*", "/"]:
            self.check_type_compatibility("i32", left_attrs["type"], line_num)
            self.check_type_compatibility("i32", right_attrs["type"], line_num)
            result_type = "i32"
            quad_op_map = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV"}
            quad_op = quad_op_map[op_str]
            if (
                op_str == "/"
                and isinstance(right_attrs["place"], int)
                and right_attrs["place"] == 0
            ):
                raise SemanticError("Division by zero.", line_num)

        elif op_str in ["<", "<=", ">", ">=", "==", "!="]:
            # For simplicity, assume i32 comparison. Could be extended.
            self.check_type_compatibility(
                left_attrs["type"], right_attrs["type"], line_num
            )  # Must be same type
            if left_attrs["type"] != "i32":  # Or allow other comparable types
                raise SemanticError(
                    f"Comparison not supported for type {self.get_type_name(left_attrs['type'])}.",
                    line_num,
                )

            result_type = "bool"  # Rust doesn't have a direct bool type like this, but result is a truth value
            quad_op_map = {
                "<": "LT",
                "<=": "LE",
                ">": "GT",
                ">=": "GE",
                "==": "EQ",
                "!=": "NE",
            }
            quad_op = quad_op_map[op_str]
        else:
            raise SemanticError(f"Unknown binary operator: {op_str}", line_num)

        result_place = self._new_temp()
        self.add_quad(quad_op, left_attrs["place"], right_attrs["place"], result_place)
        quads.append(self.quadruples.pop())

        return {"type": result_type, "place": result_place, "code": quads}

    # Rule 3.3: Function Call <ID> ( <实参列表> )
    def process_function_call(self, func_id_token, actual_args_attrs_list, line_num):
        # func_id_token: Token for the function ID
        # actual_args_attrs_list: list of {'type': type, 'place': temp_or_const, 'code': []} for each arg
        func_name = func_id_token["content"]
        func_entry = self.lookup_function(func_name, line_num)
        expected_params = func_entry.extra_info["params"]
        expected_return_type = func_entry.extra_info["return_type"]

        quads = []

        if len(actual_args_attrs_list) != len(expected_params):
            raise SemanticError(
                f"Function '{func_name}' expected {len(expected_params)} arguments, but got {len(actual_args_attrs_list)}.",
                line_num,
            )

        for i, arg_attrs in enumerate(actual_args_attrs_list):
            quads.extend(arg_attrs.get("code", []))
            self.check_type_compatibility(
                expected_params[i]["type"], arg_attrs["type"], line_num
            )
            self.add_quad("PARAM", arg_attrs["place"])  # Push param for call
            quads.append(self.quadruples.pop())

        call_result_place = None
        if expected_return_type != "void":
            call_result_place = self._new_temp()

        self.add_quad("CALL", func_name, len(actual_args_attrs_list), call_result_place)
        quads.append(self.quadruples.pop())

        return {"type": expected_return_type, "place": call_result_place, "code": quads}

    # Rule 4.1, 4.2: If-Else If-Else statement/expression
    def process_if_construct_begin(self, condition_attrs, line_num):
        # condition_attrs: {'type': type, 'place': temp_or_const, 'code': []}
        quads = []
        quads.extend(condition_attrs.get("code", []))
        # Rust's if condition doesn't strictly need 'bool', any type that can be compared to zero (for i32)
        if condition_attrs["type"] not in ["bool", "i32"]:  # i32 can be 0 or non-0
            raise SemanticError(
                f"If condition must be a boolean or integer, found {self.get_type_name(condition_attrs['type'])}.",
                line_num,
            )

        # Placeholder for jump instruction, address will be backpatched.
        # JUMP_IF_FALSE <condition_place> <label_for_else_or_endif>
        # Store index of this quad for backpatching
        after_if_label = (
            self._new_label()
        )  # Label for code after true block (used by JUMP_IF_FALSE)
        if_quad_idx = len(self.quadruples)
        self.add_quad(
            "IF_FALSE", condition_attrs["place"], result=after_if_label
        )  # Target label to be filled
        quads.append(self.quadruples.pop())

        # Return the label for the 'else' or 'endif' part and the list of quads generated for condition
        return {
            "quads": quads,
            "after_if_label": after_if_label,
            "if_quad_idx": if_quad_idx,
        }

    def process_if_true_block_end(self, if_data, is_if_expression, line_num):
        # if_data: from process_if_construct_begin
        # is_if_expression: boolean, true if it's 'if expr {block} else {block}'
        # Returns data needed for else/endif, like jump quad index and end_label for statement
        end_if_label = self._new_label()  # Label for end of entire if-else structure
        else_quad_idx = -1

        if not is_if_expression:  # If it's an if STMT, not if EXPR
            else_quad_idx = len(self.quadruples)
            self.add_quad("JUMP", result=end_if_label)  # Jump over else block

        # Backpatch the JUMP_IF_FALSE from the if_construct_begin
        # self.quadruples[if_data['if_quad_idx']].result = if_data['after_if_label'] # this was already set

        return {
            "end_if_label": end_if_label,
            "after_if_label": if_data[
                "after_if_label"
            ],  # This is where JUMP_IF_FALSE goes
            "else_jump_quad_idx": else_quad_idx if not is_if_expression else -1,
        }

    def process_else_block_begin(self, if_else_data, line_num):
        # if_else_data: from process_if_true_block_end
        # Set the target for the original IF_FALSE jump to here (start of else)
        self.add_quad("LABEL", result=if_else_data["after_if_label"])

    def process_if_else_construct_end(
        self,
        if_else_data,
        is_if_expression,
        true_branch_attrs,
        else_branch_attrs,
        line_num,
    ):
        # if_else_data: from process_if_true_block_end (or process_else_if)
        # true_branch_attrs, else_branch_attrs: for if expressions, {'type': type, 'place': result_place, 'code': block_quads}
        quads = []

        if is_if_expression:
            if not else_branch_attrs:
                raise SemanticError("If expression must have an else block.", line_num)
            self.check_type_compatibility(
                true_branch_attrs["type"], else_branch_attrs["type"], line_num
            )
            # The result of the if expression needs to be stored
            result_place = self._new_temp()
            # After true branch, assign its result and jump to end
            # After else branch, assign its result (no jump needed as it's the end)
            # This logic is tricky. Quads for branches are already generated.
            # Need to unify the result.
            # A common pattern:
            #   ... cond_code ...
            #   IF_FALSE cond, ElseLabel
            #   ... true_block_code ...
            #   ASSIGN true_block_result, expr_result_temp
            #   JUMP EndIfLabel
            # ElseLabel:
            #   ... else_block_code ...
            #   ASSIGN else_block_result, expr_result_temp
            # EndIfLabel:
            # This requires true_branch_attrs and else_branch_attrs to include their result places.
            # The semantic actions for blocks ending in expressions should populate this.
            # For simplicity now, assume the type is checked and the structure handles flow.
            # The 'place' of an if-expression is more complex.
            # It often involves Phi functions in SSA form, or stack manipulation.
            # A simpler way:
            # L_true_action: result = true_expr_val; JUMP L_endif
            # L_else_action: result = else_expr_val;
            # L_endif:
            # This means process_if_true_block_end and process_else_block_end need to handle result assignment
            # if it's an expression.

            # Let's assume the final expression of each block becomes its 'place' attribute.
            # We need to emit ASSIGN quads after each block to a common temp.
            # This requires modification of block processing.

            # Simplified: The type is the main check here. Quad generation assumes block results are handled.
            return {
                "type": true_branch_attrs["type"],
                "place": "if_expr_needs_phi_or_stack_val",
                "code": quads,
            }

        else:  # If statement
            # Backpatch the JUMP from end of true block (if there was an else)
            if if_else_data.get("else_jump_quad_idx", -1) != -1:
                self.quadruples[if_else_data["else_jump_quad_idx"]].result = (
                    if_else_data["end_if_label"]
                )
            elif (
                if_else_data.get("if_quad_idx", -1) != -1
            ):  # No else block, backpatch the original IF_FALSE
                self.quadruples[if_else_data["if_quad_idx"]].result = if_else_data[
                    "end_if_label"
                ]

            self.add_quad(
                "LABEL", result=if_else_data["end_if_label"]
            )  # Label for end of if-else structure
            quads.append(self.quadruples.pop())
            return {"code": quads}

    # Rule 5.1: while <expr> <block>
    def process_while_loop_begin(self, line_num):
        loop_start_label = self._new_label()  # For 'continue' and jumping back
        loop_end_label = self._new_label()  # For 'break' and exiting loop

        self.add_quad("LABEL", result=loop_start_label)
        self.loop_stack.append(
            {
                "type": "while",
                "start_label": loop_start_label,
                "end_label": loop_end_label,
            }
        )
        return {
            "start_label": loop_start_label,
            "end_label": loop_end_label,
            "quads": [self.quadruples[-1]],
        }

    def process_while_condition(self, condition_attrs, loop_data, line_num):
        quads = []
        quads.extend(condition_attrs.get("code", []))
        if condition_attrs["type"] not in ["bool", "i32"]:
            raise SemanticError(
                f"While condition must be bool or i32, found {self.get_type_name(condition_attrs['type'])}.",
                line_num,
            )

        # JUMP_IF_FALSE <condition_place> <loop_end_label>
        self.add_quad(
            "IF_FALSE", condition_attrs["place"], result=loop_data["end_label"]
        )
        quads.append(self.quadruples.pop())
        return {"quads": quads}

    def process_while_loop_end(self, loop_data, line_num):
        self.add_quad("JUMP", result=loop_data["start_label"])  # Jump back to condition
        self.add_quad("LABEL", result=loop_data["end_label"])  # Label for loop exit
        if self.loop_stack and self.loop_stack[-1]["type"] == "while":
            self.loop_stack.pop()
        else:
            raise SemanticError("Mismatched loop structure (while).", line_num)
        return {"quads": [self.quadruples[-2], self.quadruples[-1]]}

    # 5.2 for <pattern> in <expression1> .. <expression2> { <block> }
    def process_for_loop_begin(
        self, loop_var_name, range_start_expr, range_end_expr, line_num
    ):
        loop_start_label = self._new_label()  # loop body start
        loop_end_label = self._new_label()  # loop exit
        iter_temp = self._new_temp()  # holds current iterator value
        start_temp = self._new_temp()
        end_temp = self._new_temp()

        quads = []

        # Evaluate range start expression
        quads.extend(range_start_expr.get("code", []))
        self.add_quad("ASSIGN", range_start_expr["place"], result=start_temp)
        quads.append(self.quadruples[-1])

        # Evaluate range end expression
        quads.extend(range_end_expr.get("code", []))
        self.add_quad("ASSIGN", range_end_expr["place"], result=end_temp)
        quads.append(self.quadruples[-1])

        # Initialize iterator variable
        self.add_quad("ASSIGN", start_temp, result=iter_temp)
        quads.append(self.quadruples[-1])

        # Define loop metadata (continue, break)
        self.loop_stack.append(
            {
                "type": "for",
                "start_label": loop_start_label,
                "end_label": loop_end_label,
                "iter_temp": iter_temp,
                "end_temp": end_temp,
                "loop_var": loop_var_name,
            }
        )

        self.add_quad("LABEL", result=loop_start_label)
        quads.append(self.quadruples[-1])

        # if iter_temp >= end_temp goto loop_end
        cond_temp = self._new_temp()
        self.add_quad("GE", iter_temp, end_temp, cond_temp)
        quads.append(self.quadruples[-1])
        self.add_quad("IF_TRUE", cond_temp, result=loop_end_label)
        quads.append(self.quadruples[-1])

        # Assign iter_temp to loop variable
        self.add_quad("ASSIGN", iter_temp, result=loop_var_name)
        quads.append(self.quadruples[-1])

        return {"quads": quads, "loop_data": self.loop_stack[-1]}

    def process_for_loop_end(self, loop_data, line_num):
        quads = []

        # iter_temp = iter_temp + 1
        inc_temp = self._new_temp()
        self.add_quad("ADD", loop_data["iter_temp"], "1", inc_temp)
        quads.append(self.quadruples[-1])
        self.add_quad("ASSIGN", inc_temp, result=loop_data["iter_temp"])
        quads.append(self.quadruples[-1])

        # jump back to start of loop
        self.add_quad("JUMP", result=loop_data["start_label"])
        quads.append(self.quadruples[-1])

        # loop exit label
        self.add_quad("LABEL", result=loop_data["end_label"])
        quads.append(self.quadruples[-1])

        # pop loop metadata
        if self.loop_stack and self.loop_stack[-1]["type"] == "for":
            self.loop_stack.pop()
        else:
            raise SemanticError("Mismatched loop structure (for).", line_num)

        return {"quads": quads}

    # Rule 5.3: loop <block> (and loop expression)
    def process_loop_begin(self, is_expression, line_num):

        loop_start_label = self._new_label()
        loop_end_label = self._new_label()
        
        self.add_quad("LABEL", result=loop_start_label)
        label_quad = self.quadruples.pop()

        loop_ctx = {
            "type": "loop",
            "start_label": loop_start_label,
            "end_label": loop_end_label,
            "line_num": line_num
        }

        if is_expression:
            loop_ctx["is_expr_loop"] = True
            loop_ctx["expr_type"] = "unknown_inferred" 
            loop_ctx["result_place"] = self._new_temp()
        
        self.loop_stack.append(loop_ctx)
        
        return {
            "quads": [label_quad], 
            "loop_ctx": loop_ctx 
        }

    def process_loop_end(self, loop_data, line_num):
        if not loop_data or "loop_ctx" not in loop_data:
            raise SemanticError("Internal error: loop_data missing or malformed in process_loop_end.", line_num)

        loop_ctx = loop_data["loop_ctx"]

        quads_added_by_this_func = []

        # 1. 从 loop_stack 中弹出当前循环上下文，并进行校验
        if not (self.loop_stack and \
                self.loop_stack[-1]["type"] == loop_ctx["type"] and \
                self.loop_stack[-1]["start_label"] == loop_ctx["start_label"]): # 确保栈顶与传入的ctx匹配
            err_msg = "Mismatched loop structure (end). "
            if not self.loop_stack:
                err_msg += "Loop stack is empty."
            else:
                err_msg += f"Expected loop starting at L{loop_ctx['start_label']}, but stack top is L{self.loop_stack[-1]['start_label']} of type {self.loop_stack[-1]['type']}."
            raise SemanticError(err_msg, line_num)

        self.loop_stack.pop() # 弹出上下文

        # 2. 根据循环类型生成特定结尾四元式
        if loop_ctx["type"] == "loop" and not loop_ctx.get("is_expr_loop"): 
            self.add_quad("JUMP", result=loop_ctx["start_label"])
            quads_added_by_this_func.append(self.quadruples.pop())

        self.add_quad("LABEL", result=loop_ctx["end_label"])
        quads_added_by_this_func.append(self.quadruples.pop())

        # 3. 准备返回属性
        result_attrs = {"quads": quads_added_by_this_func}

        if loop_ctx.get("is_expr_loop"): # 特指 LoopExpression
            if loop_ctx["expr_type"] == "unknown_inferred":
                result_attrs["type"] = "void" 
                result_attrs["place"] = None 
            else: # 类型已由 'break <value>;' 推断
                result_attrs["type"] = loop_ctx["expr_type"]
                result_attrs["place"] = loop_ctx["result_place"]
        else: # 对于普通 loop 语句 (以及 while, for 语句)
            result_attrs["type"] = "void" 

        return result_attrs

    # Rule 5.4: break; continue; (and break <expr>; for loop expressions)
    def process_break_continue(self, keyword_token, expr_attrs, line_num):
        """
        处理 break 和 continue 语句，包括 loop 表达式中的 break <expr>;

        参数:
            keyword_token: 词法单元，包含 'content' 字段（'break' 或 'continue'）
            expr_attrs: 表达式的属性（None 表示无表达式）
            line_num: 当前源代码行号

        返回:
            dict: 包含生成的中间代码 {'code': [...]}
        """
        keyword = keyword_token["content"]
        quads = []

        if not self.loop_stack:
            raise SemanticError(f"'{keyword}' statement outside of a loop.", line_num)

        loop_ctx = self.loop_stack[-1]

        if keyword == "continue":
            if expr_attrs:
                raise SemanticError("'continue' cannot have an expression.", line_num)
            self.add_quad("JUMP", result=loop_ctx["start_label"])
            quads.append(self.quadruples.pop())

        elif keyword == "break":
            if loop_ctx.get("is_expr_loop"):  # loop 表达式中的 break <expr>
                if not expr_attrs:
                    raise SemanticError(
                        "Loop expression 'break' must provide a value.", line_num
                    )

                # 生成 break 表达式的计算代码
                quads.extend(expr_attrs.get("code", []))

                # 推导或检查 loop 表达式的类型
                if loop_ctx["expr_type"] == "unknown_inferred":
                    loop_ctx["expr_type"] = expr_attrs["type"]
                else:
                    self.check_type_compatibility(
                        loop_ctx["expr_type"], expr_attrs["type"], line_num
                    )

                # 赋值到 loop 表达式的 result_place
                self.add_quad(
                    "ASSIGN", expr_attrs["place"], result=loop_ctx["result_place"]
                )
                assign_quad = self.quadruples.pop()
                quads.append(assign_quad)

                # 记录用于 loop 表达式收集的 break 赋值
                if "break_assign_quads" not in loop_ctx:
                    loop_ctx["break_assign_quads"] = []
                loop_ctx["break_assign_quads"].append(assign_quad)

            elif expr_attrs:
                # 非表达式 loop 不允许 break <expr>
                raise SemanticError(
                    "'break <expression>;' is only allowed in 'loop' expressions.",
                    line_num,
                )

            # 跳转到 loop 末尾
            self.add_quad("JUMP", result=loop_ctx["end_label"])
            quads.append(self.quadruples.pop())

        return {"code": quads}

    # Rule 6.2: References and Dereferences
    # <因子> -> '*' <因子> | '&' mut <因子> | '&' <因子>
    def process_reference_op(self, op_type, target_attrs, line_num):
        # op_type: '*', '&', '&mut'
        # target_attrs: attributes of the factor being operated on
        quads = []
        quads.extend(target_attrs.get("code", []))
        target_type = target_attrs["type"]
        target_place = target_attrs["place"]
        result_place = self._new_temp()

        if op_type == "*":  # Dereference
            if not (isinstance(target_type, list) and target_type[0] in ["&", "&mut"]):
                raise SemanticError(
                    f"Cannot dereference non-reference type '{self.get_type_name(target_type)}'.",
                    line_num,
                )

            # Borrow checking: Dereferencing a shared ref is fine. Dereferencing a mut ref requires exclusive access.
            # This simplistic check doesn't fully model Rust's borrow checker.
            # If it's a named variable, check its borrow state.
            if "name" in target_attrs:
                target_entry = self.lookup_symbol(target_attrs["name"], line_num)
                # Actual borrow checking logic is more complex, involving lifetimes etc.
                # For now, assume valid if type is correct.

            result_type = target_type[1]  # The inner type
            self.add_quad("DEREF", target_place, result=result_place)
            # The result_place now holds the value. If used as LValue, it needs to be an address.
            # This means DEREF might produce an address or a value based on context.
            # For simplicity: DEREF here gives value. If *p = ..., then DEREF gives address.
            # Let's refine: DEREF gives address. LOAD_FROM_ADDR gets value.
            # So, if *p is used as RValue, it's (DEREF p, t1), (LOAD_FROM_ADDR t1, t2)
            # If *p is LValue, (DEREF p, t1) and t1 is the address.
            quads.append(self.quadruples.pop())
            return {
                "type": result_type,
                "place": result_place,
                "code": quads,
                "is_lvalue": True,
                "is_mutable": (target_type[0] == "&mut"),
                "is_lvalue_address": True,
                "is_temp_lvalue": True,
            }  # Temp lvalue from deref

        elif op_type == "&" or op_type == "&mut":
            # Target must be an LValue
            if not target_attrs.get("is_lvalue"):
                raise SemanticError(f"Cannot take reference of non-lvalue.", line_num)

            # For &mut, target must be mutable
            target_name = target_attrs.get("name")
            target_is_actually_mutable = target_attrs.get("is_mutable", False)

            if (
                "is_temp_lvalue" in target_attrs and target_attrs["is_temp_lvalue"]
            ):  # e.g. &(*foo) or &arr[i]
                pass  # Mutability comes from target_attrs['is_mutable']
            elif target_name:
                target_entry = self.lookup_symbol(target_name, line_num)
                target_is_actually_mutable = target_entry.is_mutable
                # Borrow checking (simplified):
                if op_type == "&mut":
                    if (
                        target_entry.active_borrows["immutable"] > 0
                        or target_entry.active_borrows["mutable"] > 0
                    ):
                        raise SemanticError(
                            f"Cannot take mutable reference to '{target_name}' as it's already borrowed.",
                            line_num,
                        )
                    target_entry.active_borrows["mutable"] += 1
                else:  # op_type == '&'
                    if target_entry.active_borrows["mutable"] > 0:
                        raise SemanticError(
                            f"Cannot take immutable reference to '{target_name}' as it's already mutably borrowed.",
                            line_num,
                        )
                    target_entry.active_borrows["immutable"] += 1
            else:  # Referencing something without a direct symbol table entry (e.g. complex expr result)
                if op_type == "&mut" and not target_is_actually_mutable:
                    raise SemanticError(
                        f"Cannot take mutable reference to an immutable temporary value.",
                        line_num,
                    )

            if op_type == "&mut" and not target_is_actually_mutable:
                raise SemanticError(
                    f"Cannot take mutable reference of immutable '{target_attrs.get('name', 'value')}'.",
                    line_num,
                )

            result_type = [op_type, target_type]  # e.g. ['&mut', 'i32']
            self.add_quad("REF", target_place, result=result_place)
            quads.append(self.quadruples.pop())
            # TODO: decrement borrow counts when references go out of scope (complex)

            return {"type": result_type, "place": result_place, "code": quads}

        raise SemanticError(f"Unknown reference operation '{op_type}'.", line_num)

    # Rule 7.1, 7.2, 7.3: Expression Blocks
    def process_expression_block_begin(self, line_num):
        self.enter_scope()
        # For if/loop expressions, the block's "result" (type and place) is important.

    def process_expression_block_end(
        self, stmts_attrs_list, final_expr_attrs, line_num
    ):
        # stmts_attrs_list: list of codes from statements
        # final_expr_attrs: {'type': type, 'place': temp, 'code': []} or None if block ends with ';'
        quads = []
        for stmt_attrs in stmts_attrs_list:
            if stmt_attrs and "code" in stmt_attrs:
                quads.extend(stmt_attrs["code"])

        self.exit_scope()
        block_result_type = "void"
        block_result_place = None

        if final_expr_attrs:  # Block ends with an expression
            quads.extend(final_expr_attrs.get("code", []))
            block_result_type = final_expr_attrs["type"]
            block_result_place = final_expr_attrs["place"]
        # If block ends with a statement (e.g. let x=1;}), type is void.

        return {"type": block_result_type, "place": block_result_place, "code": quads}

    # Rule 8.1: Array literal ['elem1', 'elem2', ...]
    # Rule 8.1: Array type declaration [type; size] (handled in process_type)
    def process_array_literal(self, elements_attrs_list, declared_type_attrs, line_num):
        # elements_attrs_list: list of {'type': type, 'place': place, 'code': []}
        # declared_type_attrs: (optional) from a 'let a: [i32; 3] = ...;' context.
        #                    {'type': ['[', 'i32', 3], ...}
        quads = []
        element_places = []
        literal_element_type = None

        if not elements_attrs_list:  # Empty array literal []
            # Type must be known from context if it's empty
            if not declared_type_attrs:
                raise SemanticError(
                    "Cannot infer type of empty array literal without context.",
                    line_num,
                )
            array_type_info = declared_type_attrs["type"]  # ['[', el_type, size]
            if array_type_info[2] != 0:
                raise SemanticError(
                    f"Empty array literal used for non-empty array type {self.get_type_name(array_type_info)}.",
                    line_num,
                )
            literal_element_type = array_type_info[1]
            num_elements = 0
        else:
            num_elements = len(elements_attrs_list)
            first_element_type = elements_attrs_list[0]["type"]
            for i, elem_attrs in enumerate(elements_attrs_list):
                quads.extend(elem_attrs.get("code", []))
                self.check_type_compatibility(
                    first_element_type,
                    elem_attrs["type"],
                    line_num,
                    f"Array elements must have the same type. Expected {self.get_type_name(first_element_type)}, found {self.get_type_name(elem_attrs['type'])} at index {i}.",
                )
                element_places.append(elem_attrs["place"])
            literal_element_type = first_element_type

        final_array_type = ["[", literal_element_type, num_elements]

        if declared_type_attrs:
            self.check_type_compatibility(
                declared_type_attrs["type"], final_array_type, line_num
            )
            # Use the declared type as the definitive one if compatible
            final_array_type = declared_type_attrs["type"]

        array_place = self._new_temp()
        # Quad for array creation. Arguments might be size and then elements, or a special op.
        # For now: (ARRAY_INIT, result_array_place, size, type_info_or_nullptr)
        # Then sequence of (ARRAY_SET_ELEMENT, array_place, index, element_place)
        self.add_quad(
            "ARRAY_INIT",
            array_place,
            num_elements,
            self.get_type_name(final_array_type[1]),
        )
        quads.append(self.quadruples.pop())
        for i, el_place in enumerate(element_places):
            self.add_quad("ARRAY_SET", array_place, i, el_place)
            quads.append(self.quadruples.pop())

        return {"type": final_array_type, "place": array_place, "code": quads}

    # Rule 9.1: Tuple literal (elem1, elem2, ...)
    # Rule 9.1: Tuple type declaration (type1, type2, ...) (handled in process_type)
    def process_tuple_literal(self, elements_attrs_list, declared_type_attrs, line_num):
        # elements_attrs_list: list of {'type': type, 'place': place, 'code': []}
        # declared_type_attrs: (optional) from 'let a: (i32, bool) = ...;' context.
        #                    {'type': ('i32', 'bool'), ...}
        quads = []
        element_places = []
        element_types = []

        if not elements_attrs_list:  # Empty tuple literal ()
            final_tuple_type = tuple()
        else:
            for elem_attrs in elements_attrs_list:
                quads.extend(elem_attrs.get("code", []))
                element_places.append(elem_attrs["place"])
                element_types.append(elem_attrs["type"])
            final_tuple_type = tuple(element_types)

        if declared_type_attrs:
            self.check_type_compatibility(
                declared_type_attrs["type"], final_tuple_type, line_num
            )
            final_tuple_type = declared_type_attrs[
                "type"
            ]  # Use declared type if compatible

        tuple_place = self._new_temp()
        # Similar to array, (TUPLE_INIT, result_tuple_place, num_elements)
        # Then (TUPLE_SET_ELEMENT, tuple_place, index, element_place)
        self.add_quad("TUPLE_INIT", tuple_place, len(final_tuple_type))
        quads.append(self.quadruples.pop())
        for i, el_place in enumerate(element_places):
            self.add_quad("TUPLE_SET", tuple_place, i, el_place)
            quads.append(self.quadruples.pop())

        return {"type": final_tuple_type, "place": tuple_place, "code": quads}

    # depreciated
    # def process_loop_statement(self, body_block_attrs, line_num):
    #     loop_data_from_begin = self.process_loop_begin(is_expression=False, line_num=line_num)

    #     all_quads = []
    #     all_quads.extend(loop_data_from_begin.get("quads", []))
    #     all_quads.extend(body_block_attrs.get("code", []))

    #     attrs_from_end = self.process_loop_end(loop_data_from_begin, line_num)
    #     all_quads.extend(attrs_from_end.get("quads", []))

    #     return {"code": all_quads, "type": "void"}



    def get_quadruples(self):
        return self.quadruples

    def print_quadruples(self):
        print("\n--- Quadruples ---")
        for i, q in enumerate(self.quadruples):
            print(f"{i:03d}: {q}")
        print("------------------")

    def print_symbol_table(self):  # For debugging
        print("\n--- Symbol Table ---")
        level = 0
        for scope_table in self.symbol_tables:
            print(f"Scope Level: {level}")
            if not scope_table:
                print("  <empty>")
            for name, entry in scope_table.items():
                extra = f", extra: {entry.extra_info}" if entry.extra_info else ""
                mut = "mut" if entry.is_mutable else "immut"
                init = "init" if entry.initialized else "uninit"
                print(
                    f"  {name}: type={self.get_type_name(entry.data_type)}, kind={entry.sym_type.name}, scope={entry.scope_level}, {mut}, {init}{extra}"
                )
            level += 1
        print("--------------------")

    def dispatch_semantic_action(self, production_rule_str, children_attrs, approx_loc):
        """
        根据产生式字符串，调度到相应的语义处理函数。
        """

        # 辅助函数，确保即使子节点属性不存在或为None，也能安全获取并提供默认值
        def get_child_attrs(idx):
            if idx < len(children_attrs) and children_attrs[idx] is not None:
                attrs = children_attrs[idx]
                # 确保每个子属性字典都有 'code' 键，即使是空列表
                if "code" not in attrs:
                    attrs["code"] = []
                return attrs
            # 对于epsilon或不存在的子节点，返回一个包含空code列表的默认字典
            return {
                "code": [],
                "token_obj": None,
                "place": None,
                "type": "unknown_epsilon",
                "is_empty": True,
            }

        def get_token_obj_from_child(child_idx):
            child = get_child_attrs(child_idx)
            return child.get("token_obj")

        # --- Program & Declarations ---
        if production_rule_str == "Program -> DeclarationList":
            decl_list_attrs = get_child_attrs(0)
            return {"code": decl_list_attrs.get("code", [])}

        elif production_rule_str == "DeclarationList -> epsilon":
            return {"code": []}
        elif production_rule_str == "DeclarationList -> Declaration DeclarationList":
            decl_attrs = get_child_attrs(0)
            decl_list_tail_attrs = get_child_attrs(1)
            combined_code = decl_attrs.get("code", []) + decl_list_tail_attrs.get(
                "code", []
            )
            return {"code": combined_code}

        elif production_rule_str == "Declaration -> FunctionDeclaration":
            return get_child_attrs(0)  # FunctionDeclaration 应返回其 'code'

        # --- VariableDeclarationInner ---
        elif production_rule_str == "VariableDeclarationInner -> MUT IDENTIFIER":
            mut_token = get_token_obj_from_child(0)
            identifier_token = get_token_obj_from_child(1)
            attrs = self.process_variable_decl_internal(
                identifier_token, mut_token, approx_loc
            )
            attrs["code"] = []  # 此规则本身不产生代码，但返回的属性应有code字段
            return attrs
        elif production_rule_str == "VariableDeclarationInner -> IDENTIFIER":
            identifier_token = get_token_obj_from_child(0)
            attrs = self.process_variable_decl_internal(
                identifier_token, None, approx_loc
            )
            attrs["code"] = []
            return attrs

        # --- Assignable ---
        elif production_rule_str == "Assignable -> IDENTIFIER":
            identifier_token = get_token_obj_from_child(0)
            # process_assignable_element 返回的字典应包含 'code' (通常为空)
            return self.process_assignable_element(
                {"type": "id", "token": identifier_token}, approx_loc
            )
        elif (
            production_rule_str == "Assignable -> MULT IDENTIFIER"
        ):  # 假设 MULT 是解引用 '*'
            # id_attrs 应包含 'code' (来自可能的复杂IDENTIFIER的解析)
            id_attrs = self.process_assignable_element(
                {"type": "id", "token": get_token_obj_from_child(1)}, approx_loc
            )
            # process_reference_op 应返回包含解引用代码的 'code'
            ref_op_attrs = self.process_reference_op("*", id_attrs, approx_loc)
            # 合并代码
            combined_code = id_attrs.get("code", []) + ref_op_attrs.get("code", [])
            ref_op_attrs["code"] = combined_code
            return ref_op_attrs
        elif (
            production_rule_str == "Assignable -> Primary LBRACK Expression RBRACK"
        ):  # 数组元素访问作为左值
            primary_attrs = get_child_attrs(
                0
            )  # Primary (可能是数组名或更复杂的表达式结果)
            expr_attrs = get_child_attrs(2)  # Expression (索引)
            # process_assignable_element 处理数组访问时，会合并 base 和 index 的 code
            return self.process_assignable_element(
                {"type": "array_access", "base": primary_attrs, "index": expr_attrs},
                approx_loc,
            )
        elif (
            production_rule_str == "Assignable -> Primary DOT INTEGER_CONSTANT"
        ):  # 元组元素访问作为左值
            primary_attrs = get_child_attrs(0)  # Primary (元组)
            index_token = get_token_obj_from_child(2)  # INTEGER_CONSTANT (索引)
            return self.process_assignable_element(
                {
                    "type": "tuple_access",
                    "base": primary_attrs,
                    "index_token": index_token,
                },
                approx_loc,
            )

        # --- Type Productions ---
        elif production_rule_str == "Type -> I32":
            return {"type": "i32", "code": [], "token_obj": get_token_obj_from_child(0)}
        elif production_rule_str == "Type -> AMP MUT Type":
            inner_type_attrs = get_child_attrs(2)
            return {
                "type": ["&mut", inner_type_attrs.get("type")],
                "code": inner_type_attrs.get("code", []),
                "token_obj": get_token_obj_from_child(0),
            }
        elif production_rule_str == "Type -> AMP Type":
            inner_type_attrs = get_child_attrs(1)
            return {
                "type": ["&", inner_type_attrs.get("type")],
                "code": inner_type_attrs.get("code", []),
                "token_obj": get_token_obj_from_child(0),
            }
        elif (
            production_rule_str
            == "Type -> LBRACK Type SEMICOLON INTEGER_CONSTANT RBRACK"
        ):
            element_type_attrs = get_child_attrs(1)
            size_token = get_token_obj_from_child(3)
            size = -1
            try:
                size = int(size_token["content"])
                if size <= 0:
                    raise SemanticError("数组大小必须为正整数。", approx_loc)
            except:
                raise SemanticError(
                    f"无效的数组大小: {size_token['content'] if size_token else '未知'}",
                    approx_loc,
                )
            return {
                "type": ["[", element_type_attrs.get("type"), size],
                "code": element_type_attrs.get("code", []),
                "token_obj": get_token_obj_from_child(0),
            }
        elif production_rule_str == "Type -> LPAREN TupleTypeInternal RPAREN":
            tuple_type_internal_attrs = get_child_attrs(1)
            element_types = tuple_type_internal_attrs.get("element_types", [])
            return {
                "type": tuple(element_types),
                "code": tuple_type_internal_attrs.get("code", []),
                "token_obj": get_token_obj_from_child(0),
            }

        # --- TupleTypeInternal / TypeList ---
        elif production_rule_str == "TupleTypeInternal -> epsilon":
            return {"element_types": [], "code": []}
        elif (
            production_rule_str == "TupleTypeInternal -> Type"
        ):  # 按照文法，这可能用于 (T) 形式，通常不认为是元组
            type_attrs = get_child_attrs(0)
            return {
                "element_types": [type_attrs.get("type")],
                "code": type_attrs.get("code", []),
            }
        elif production_rule_str == "TupleTypeInternal -> Type COMMA TypeList":
            first_type_attrs = get_child_attrs(0)
            type_list_attrs = get_child_attrs(2)
            element_types = [first_type_attrs.get("type")] + type_list_attrs.get(
                "element_types", []
            )
            code = first_type_attrs.get("code", []) + type_list_attrs.get("code", [])
            return {"element_types": element_types, "code": code}
        elif production_rule_str == "TypeList -> epsilon":
            return {"element_types": [], "code": []}
        elif production_rule_str == "TypeList -> Type":
            type_attrs = get_child_attrs(0)
            return {
                "element_types": [type_attrs.get("type")],
                "code": type_attrs.get("code", []),
            }
        elif production_rule_str == "TypeList -> Type COMMA TypeList":
            first_type_attrs = get_child_attrs(0)
            tail_type_list_attrs = get_child_attrs(2)
            element_types = [first_type_attrs.get("type")] + tail_type_list_attrs.get(
                "element_types", []
            )
            code = first_type_attrs.get("code", []) + tail_type_list_attrs.get(
                "code", []
            )
            return {"element_types": element_types, "code": code}

        # --- Function Structure ---
        elif (
            production_rule_str
            == "FunctionDeclaration -> FunctionHeader StatementBlock"
        ):
            func_header_attrs = get_child_attrs(0)
            stmt_block_attrs = get_child_attrs(1)

            combined_code = func_header_attrs.get("code", []) + stmt_block_attrs.get(
                "code", []
            )

            # 从 process_function_body_end 获取 FUNC_END 四元式并合并
            # 假设 func_header_attrs['name'] 总是存在且正确
            end_attrs = self.process_function_body_end(
                func_header_attrs.get("name"), approx_loc
            )
            combined_code.extend(end_attrs.get("code", []))

            return {
                "name": func_header_attrs.get("name"),
                "type": "function_declaration",
                "code": combined_code,
            }

        elif (
            production_rule_str
            == "FunctionDeclaration -> FunctionHeader BlockExpression"
        ):
            func_header_attrs = get_child_attrs(0)
            block_expr_attrs = get_child_attrs(1)

            combined_code = func_header_attrs.get("code", []) + block_expr_attrs.get(
                "code", []
            )

            func_return_type = func_header_attrs.get("return_type", "void")
            block_expr_type = block_expr_attrs.get("type", "void")
            block_expr_place = block_expr_attrs.get("place")

            # 处理函数返回类型和块表达式的兼容性及隐式返回
            if func_return_type != "void":
                if block_expr_type == "void":
                    # 检查行号获取是否准确
                    err_line = (
                        block_expr_attrs.get("token_obj", {})
                        .get("loc", {})
                        .get("row", approx_loc)
                    )
                    raise SemanticError(
                        f"Function '{func_header_attrs.get('name')}' expects a return value of type {self.get_type_name(func_return_type)}, but block expression returns void.",
                        err_line,
                    )
                self.check_type_compatibility(
                    func_return_type, block_expr_type, approx_loc
                )
                # 创建 RETURN_VAL 四元式 (之前是 add_quad 后 pop，现在直接创建)
                temp_return_quad = Quadruple("RETURN_VAL", block_expr_place, None, None)
                combined_code.append(temp_return_quad)
            elif (
                block_expr_type != "void" and block_expr_place is not None
            ):  # 如果函数返回void，但块表达式有值
                # Rust 中这种情况是允许的，值会被丢弃。可以考虑添加一个 "DROP" 指令或无操作。
                # 对于简单的四元式生成，可以不生成额外指令。
                pass

            # 从 process_function_body_end 获取 FUNC_END 四元式并合并
            end_attrs = self.process_function_body_end(
                func_header_attrs.get("name"),
                approx_loc,
                last_expr_attrs_for_implicit_return=block_expr_attrs,
            )
            combined_code.extend(end_attrs.get("code", []))

            return {
                "name": func_header_attrs.get("name"),
                "type": "function_declaration",
                "code": combined_code,
            }

        elif (
            production_rule_str
            == "FunctionHeader -> FN IDENTIFIER LPAREN ParameterList RPAREN"
        ):
            id_token = get_token_obj_from_child(1)
            param_list_cont_attrs = get_child_attrs(3)
            # process_function_declaration_header 返回的字典应包含 'code' (内含 FUNC_BEGIN)
            return self.process_function_declaration_header(
                id_token,
                param_list_cont_attrs.get("params", []),
                "void",
                approx_loc,
            )
        elif (
            production_rule_str
            == "FunctionHeader -> FN IDENTIFIER LPAREN ParameterList RPAREN ARROW Type"
        ):
            id_token = get_token_obj_from_child(1)
            param_list_cont_attrs = get_child_attrs(3)
            return_type_attrs = get_child_attrs(6)
            return self.process_function_declaration_header(
                id_token,
                param_list_cont_attrs.get("params", []),
                return_type_attrs.get("type"),
                approx_loc,
            )

        elif production_rule_str == "ParameterList -> epsilon":
            return {"params": [], "code": []}
        elif production_rule_str == "ParameterList -> Parameter":
            param_attrs = get_child_attrs(0)
            return {
                "params": [param_attrs] if param_attrs else [],
                "code": param_attrs.get("code", []) if param_attrs else [],
            }
        elif production_rule_str == "ParameterList -> Parameter COMMA ParameterList":
            param_attrs = get_child_attrs(0)
            tail_list_attrs = get_child_attrs(2)
            params = ([param_attrs] if param_attrs else []) + tail_list_attrs.get(
                "params", []
            )
            code = (
                param_attrs.get("code", []) if param_attrs else []
            ) + tail_list_attrs.get("code", [])
            return {"params": params, "code": code}

        elif production_rule_str == "Parameter -> VariableDeclarationInner COLON Type":
            var_decl_inner_attrs = get_child_attrs(0)
            type_attrs = get_child_attrs(2)
            # 这个方法应该返回一个包含参数完整信息的字典，以及可能的代码
            # 假设 VariableDeclarationInner 和 Type 本身不产生独立执行的代码，code 主要来自更复杂的类型
            combined_code = var_decl_inner_attrs.get("code", []) + type_attrs.get(
                "code", []
            )
            return {
                "name": var_decl_inner_attrs.get("name"),
                "is_mutable": var_decl_inner_attrs.get("is_mutable", False),
                "type": type_attrs.get("type"),
                "line": var_decl_inner_attrs.get("line", approx_loc),
                "token_obj": var_decl_inner_attrs.get("token_obj"),
                "code": combined_code,
            }

        # --- StatementBlock / StatementList ---
        elif production_rule_str == "StatementBlock -> LBRACE StatementList RBRACE":
            stmt_list_attrs = get_child_attrs(1)
            # 作用域由调用方（如函数声明、块表达式）处理
            return {"code": stmt_list_attrs.get("code", [])}
        elif production_rule_str == "StatementList -> epsilon":
            return {"code": []}
        elif production_rule_str == "StatementList -> Statement StatementList":
            stmt_attrs = get_child_attrs(0)
            stmt_list_tail_attrs = get_child_attrs(1)
            combined_code = stmt_attrs.get("code", []) + stmt_list_tail_attrs.get(
                "code", []
            )
            return {"code": combined_code}

        # --- Statements ---
        elif production_rule_str == "Statement -> SEMICOLON":
            return {"code": []}
        elif production_rule_str == "Statement -> ReturnStatement":
            return get_child_attrs(0)
        elif (
            production_rule_str
            == "Statement -> LET VariableDeclarationInner COLON Type SEMICOLON"
        ):
            var_decl_inner_attrs = get_child_attrs(1)
            type_attrs = get_child_attrs(3)
            # process_variable_declaration 应返回包含 'code' 的属性
            return self.process_variable_declaration(
                var_decl_inner_attrs, type_attrs, approx_loc
            )
        elif (
            production_rule_str == "Statement -> LET VariableDeclarationInner SEMICOLON"
        ):
            var_decl_inner_attrs = get_child_attrs(1)
            return self.process_variable_declaration(
                var_decl_inner_attrs, None, approx_loc
            )
        elif production_rule_str == "Statement -> AssignmentStatement":
            return get_child_attrs(0)
        elif (
            production_rule_str == "Statement -> VariableDeclarationAssignmentStatement"
        ):
            return get_child_attrs(0)  # 这个节点应该返回包含赋值四元式的 code
        elif production_rule_str == "Statement -> Expression SEMICOLON":
            expr_attrs = get_child_attrs(0)
            return {"code": expr_attrs.get("code", []), "type": "void_statement_expr"}
        elif production_rule_str == "Statement -> IfStatement":
            return get_child_attrs(0)
        elif production_rule_str == "Statement -> WhileStatement":
            return get_child_attrs(0)
        elif production_rule_str == "Statement -> ForStatement":
            return get_child_attrs(0)
        elif production_rule_str == "Statement -> LoopStatement":
            return get_child_attrs(0)
        elif production_rule_str == "Statement -> BREAK SEMICOLON":
            break_token = get_token_obj_from_child(0)
            return self.process_break_continue(break_token, None, approx_loc)
        elif production_rule_str == "Statement -> CONTINUE SEMICOLON":
            continue_token = get_token_obj_from_child(0)
            return self.process_break_continue(continue_token, None, approx_loc)
        elif production_rule_str == "Statement -> BREAK Expression SEMICOLON":
            break_token = get_token_obj_from_child(0)
            expr_attrs = get_child_attrs(1)
            return self.process_break_continue(break_token, expr_attrs, approx_loc)

        # --- ReturnStatement ---
        elif production_rule_str == "ReturnStatement -> RETURN SEMICOLON":
            return self.process_return_statement(None, approx_loc)
        elif production_rule_str == "ReturnStatement -> RETURN Expression SEMICOLON":
            expr_attrs = get_child_attrs(1)
            return self.process_return_statement(expr_attrs, approx_loc)

        # --- AssignmentStatement ---
        elif (
            production_rule_str
            == "AssignmentStatement -> VariableDeclarationInner ASSIGN Expression SEMICOLON"
        ):
            var_decl_inner_attrs = get_child_attrs(0)
            expr_attrs = get_child_attrs(2)
            # 此处需要确保 var_decl_inner_attrs 能够被 process_assignment 正确用作左值
            # 通常 VariableDeclarationInner 只包含 name 和 is_mutable, 可能不包含 type 和 place
            # process_assignment 内部需要通过 name 从符号表查找完整的左值信息
            # 或者，如此处设计，构造一个临时的 assignable_attrs
            simulated_assignable_attrs = {
                "name": var_decl_inner_attrs.get("name"),
                "is_lvalue": True,
                "is_mutable": var_decl_inner_attrs.get("is_mutable"),
                "place": var_decl_inner_attrs.get("name"),  # 假设变量名就是其 place
                "code": var_decl_inner_attrs.get("code", []),  # 通常为空
                "token_obj": var_decl_inner_attrs.get("token_obj"),
            }
            # process_assignment 应返回包含 'code' (ASSIGN四元式) 的属性
            assign_attrs = self.process_assignment(
                simulated_assignable_attrs, expr_attrs, approx_loc
            )
            # 合并来自 VariableDeclarationInner (如果有) 和 expr_attrs (如果有) 和 assign_attrs 的代码
            # 但通常前两者代码在 assign_attrs['code'] 中已由 process_assignment 合并
            return assign_attrs

        elif (
            production_rule_str
            == "AssignmentStatement -> Assignable ASSIGN Expression SEMICOLON"
        ):
            assignable_attrs = get_child_attrs(
                0
            )  # Assignable 应包含其自身的 code (如数组/元组索引计算)
            expr_attrs = get_child_attrs(2)  # Expression 应包含其自身的 code
            # process_assignment 返回的 'code' 应包含 Assignable, Expression 的 code, 以及新的 ASSIGN 四元式
            return self.process_assignment(
                assignable_attrs, expr_attrs, approx_loc
            )

        # --- VariableDeclarationAssignmentStatement ---
        elif (
            production_rule_str
            == "VariableDeclarationAssignmentStatement -> LET VariableDeclarationInner ASSIGN Expression SEMICOLON"
        ):
            var_decl_inner_attrs = get_child_attrs(1)
            expr_attrs = get_child_attrs(3)
            # process_variable_declaration_assignment 返回的字典应包含 'code' (内含 ASSIGN)
            return self.process_variable_declaration_assignment(
                var_decl_inner_attrs, None, expr_attrs, approx_loc
            )
        elif (
            production_rule_str
            == "VariableDeclarationAssignmentStatement -> LET VariableDeclarationInner COLON Type ASSIGN Expression SEMICOLON"
        ):
            var_decl_inner_attrs = get_child_attrs(1)
            type_attrs = get_child_attrs(3)
            expr_attrs = get_child_attrs(5)
            return self.process_variable_declaration_assignment(
                var_decl_inner_attrs, type_attrs, expr_attrs, approx_loc
            )

        # --- Expressions (Chain rules) ---
        elif production_rule_str == "Expression -> AdditionExpression":
            return get_child_attrs(0)
        elif production_rule_str == "AdditionExpression -> Term":
            return get_child_attrs(0)
        elif production_rule_str == "Term -> Factor":
            return get_child_attrs(0)
        elif production_rule_str == "Factor -> Primary":
            return get_child_attrs(0)

        # --- Expressions (Operations) ---
        elif (
            production_rule_str
            == "Expression -> Expression ComparisonOperator AdditionExpression"
        ):
            left_expr_attrs = get_child_attrs(0)
            comp_op_attrs = get_child_attrs(1)
            right_add_expr_attrs = get_child_attrs(2)
            op_token = comp_op_attrs.get("token_obj")
            # process_binary_op 返回的字典应包含 'code' (操作的四元式 + 子表达式的 code)
            return self.process_binary_op(
                op_token, left_expr_attrs, right_add_expr_attrs, approx_loc
            )
        elif (
            production_rule_str == "AdditionExpression -> AdditionExpression AddOp Term"
        ):
            left_add_expr_attrs = get_child_attrs(0)
            add_op_attrs = get_child_attrs(1)
            right_term_attrs = get_child_attrs(2)
            op_token = add_op_attrs.get("token_obj")
            return self.process_binary_op(
                op_token, left_add_expr_attrs, right_term_attrs, approx_loc
            )
        elif production_rule_str == "Term -> Term MulOp Factor":
            left_term_attrs = get_child_attrs(0)
            mul_op_attrs = get_child_attrs(1)
            right_factor_attrs = get_child_attrs(2)
            op_token = mul_op_attrs.get("token_obj")
            return self.process_binary_op(
                op_token, left_term_attrs, right_factor_attrs, approx_loc
            )

        # --- Primary Expressions ---
        elif production_rule_str == "Primary -> INTEGER_CONSTANT":
            num_token = get_token_obj_from_child(0)
            # process_element 返回的字典应包含 'code' (通常为空，因为常量不产生指令)
            return self.process_element(num_token, approx_loc)
        elif production_rule_str == "Primary -> MINUS INTEGER_CONSTANT":
            minus_token = get_token_obj_from_child(0)  # Token for MINUS
            num_token = get_token_obj_from_child(1)  # Token for INTEGER_CONSTANT
            # 构造 0 - number
            zero_attrs = {
                "type": "i32",
                "place": 0,
                "code": [],
                "token_obj": None,
            }  # 构造一个临时的0
            num_attrs = self.process_element(
                num_token, approx_loc
            )  # 获取数字的属性
            # process_binary_op 将合并 zero_attrs.code, num_attrs.code, 和 SUB 的代码
            return self.process_binary_op(
                minus_token, zero_attrs, num_attrs, approx_loc
            )
        elif production_rule_str == "Primary -> Assignable":
            assignable_attrs = get_child_attrs(0)
            # process_element 会处理将左值用作右值（可能需要LOAD）并返回 'code'
            return self.process_element(assignable_attrs, approx_loc)
        elif production_rule_str == "Primary -> LPAREN Expression RPAREN":
            return get_child_attrs(1)  # 传递 Expression 的属性，包括 code
        elif production_rule_str == "Primary -> IDENTIFIER LPAREN ArgumentList RPAREN":
            id_token = get_token_obj_from_child(0)
            arg_list_cont_attrs = get_child_attrs(2)
            args_list = arg_list_cont_attrs.get("args", [])
            # process_function_call 返回的字典应包含 'code' (内含 PARAM 和 CALL 四元式 + 参数表达式的 code)
            func_call_attrs = self.process_function_call(
                id_token, args_list, approx_loc
            )
            # 参数列表本身也可能有代码（来自其内部表达式）
            # process_function_call 应该已经合并了参数的代码
            # 但如果 ArgumentList 自身作为非终结符有独立代码，需要在这里合并
            # 假设 process_function_call 已经处理了 args_list 中每个 arg 的 code
            # 并且 arg_list_cont_attrs['code'] 是 ArgumentList 规则自身结构产生的代码（通常不多）
            final_code = arg_list_cont_attrs.get("code", []) + func_call_attrs.get(
                "code", []
            )
            func_call_attrs["code"] = final_code
            return func_call_attrs

        elif (
            production_rule_str == "Primary -> LBRACK ArrayElements RBRACK"
        ):  # 数组字面量
            array_elements_attrs = get_child_attrs(
                1
            )  # 应包含 'elements' 和这些 elements 的 'code'
            # process_array_literal 返回的字典应包含 'code' (ARRAY_INIT, ARRAY_SET 等)
            return self.process_array_literal(
                array_elements_attrs.get("elements", []), None, approx_loc
            )
        elif (
            production_rule_str == "Primary -> LPAREN TupleAssignmentInternal RPAREN"
        ):  # 元组字面量
            tuple_internal_attrs = get_child_attrs(1)
            return self.process_tuple_literal(
                tuple_internal_attrs.get("elements", []), None, approx_loc
            )

        # --- Operators (passing up token_obj) ---
        elif production_rule_str == "ComparisonOperator -> LT":
            return {
                "op_symbol": "<",
                "token_obj": get_token_obj_from_child(0),
                "code": [],
            }
        elif production_rule_str == "ComparisonOperator -> LE":
            return {
                "op_symbol": "<=",
                "token_obj": get_token_obj_from_child(0),
                "code": [],
            }
        elif production_rule_str == "ComparisonOperator -> GT":
            return {
                "op_symbol": ">",
                "token_obj": get_token_obj_from_child(0),
                "code": [],
            }
        elif production_rule_str == "ComparisonOperator -> GE":
            return {
                "op_symbol": ">=",
                "token_obj": get_token_obj_from_child(0),
                "code": [],
            }
        elif production_rule_str == "ComparisonOperator -> EQ":
            return {
                "op_symbol": "==",
                "token_obj": get_token_obj_from_child(0),
                "code": [],
            }
        elif production_rule_str == "ComparisonOperator -> NEQ":
            return {
                "op_symbol": "!=",
                "token_obj": get_token_obj_from_child(0),
                "code": [],
            }
        elif production_rule_str == "AddOp -> PLUS":
            return {
                "op_symbol": "+",
                "token_obj": get_token_obj_from_child(0),
                "code": [],
            }
        elif production_rule_str == "AddOp -> MINUS":
            return {
                "op_symbol": "-",
                "token_obj": get_token_obj_from_child(0),
                "code": [],
            }
        elif production_rule_str == "MulOp -> MULT":
            return {
                "op_symbol": "*",
                "token_obj": get_token_obj_from_child(0),
                "code": [],
            }
        elif production_rule_str == "MulOp -> DIV":
            return {
                "op_symbol": "/",
                "token_obj": get_token_obj_from_child(0),
                "code": [],
            }

        # --- ArgumentList / ArrayElements (List construction) ---
        elif production_rule_str == "ArgumentList -> epsilon":
            return {"args": [], "code": []}
        elif production_rule_str == "ArgumentList -> Expression":
            expr_attrs = get_child_attrs(0)
            return {"args": [expr_attrs], "code": expr_attrs.get("code", [])}
        elif production_rule_str == "ArgumentList -> Expression COMMA ArgumentList":
            expr_attrs = get_child_attrs(0)
            tail_list_attrs = get_child_attrs(2)
            args = [expr_attrs] + tail_list_attrs.get("args", [])
            code = expr_attrs.get("code", []) + tail_list_attrs.get("code", [])
            return {"args": args, "code": code}

        elif production_rule_str == "ArrayElements -> epsilon":
            return {"elements": [], "code": []}
        elif production_rule_str == "ArrayElements -> Expression":
            expr_attrs = get_child_attrs(0)
            return {"elements": [expr_attrs], "code": expr_attrs.get("code", [])}
        elif production_rule_str == "ArrayElements -> Expression COMMA ArrayElements":
            expr_attrs = get_child_attrs(0)
            tail_list_attrs = get_child_attrs(2)
            elements = [expr_attrs] + tail_list_attrs.get("elements", [])
            code = expr_attrs.get("code", []) + tail_list_attrs.get("code", [])
            return {"elements": elements, "code": code}

        # --- Factor -> LBRACK ArrayElementsList RBRACK 对应于 ArrayElementsList 的处理
        elif production_rule_str == "Factor -> LBRACK ArrayElementsList RBRACK":
            array_elements_list_attrs = get_child_attrs(1)
            return self.process_array_literal(
                array_elements_list_attrs.get("elements", []), None, approx_loc
            )

        # --- ArrayElementsList 的规则
        elif production_rule_str == "ArrayElementsList -> epsilon":
            return {"elements": [], "code": []}
        elif production_rule_str == "ArrayElementsList -> Expression":
            expr_attrs = get_child_attrs(0)
            return {"elements": [expr_attrs], "code": expr_attrs.get("code", [])}
        elif (
            production_rule_str
            == "ArrayElementsList -> Expression COMMA ArrayElementsList"
        ):
            expr_attrs = get_child_attrs(0)
            tail_list_attrs = get_child_attrs(2)
            elements = [expr_attrs] + tail_list_attrs.get("elements", [])
            code = expr_attrs.get("code", []) + tail_list_attrs.get("code", [])
            return {"elements": elements, "code": code}

        # --- Control Flow: If, Else, While, For, Loop ---
        elif (
            production_rule_str
            == "IfStatement -> IF Expression StatementBlock ElsePart"
        ):
            cond_expr_attrs = get_child_attrs(1)
            true_block_attrs = get_child_attrs(2)
            else_part_attrs = get_child_attrs(3)  # ElsePart 自身也应传递 'code'
            # process_if_statement 应该负责合并所有这些部分的code并生成跳转指令
            return self.process_if_statement(
                cond_expr_attrs, true_block_attrs, else_part_attrs, approx_loc
            )
        elif production_rule_str == "ElsePart -> epsilon":
            return {"code": [], "is_empty": True}
        elif production_rule_str == "ElsePart -> ELSE StatementBlock":
            else_block_attrs = get_child_attrs(1)  # StatementBlock 包含其 code
            return {"code": else_block_attrs.get("code", []), "is_empty": False}
        elif (
            production_rule_str
            == "ElsePart -> ELSE IF Expression StatementBlock ElsePart"
        ):
            # 这个结构由 process_if_statement 内部通过 else_part_attrs 的 'is_else_if' 标志递归处理
            # 这里返回一个结构体，供 process_if_statement 解析
            cond_expr_attrs = get_child_attrs(2)
            true_block_attrs = get_child_attrs(3)
            tail_else_part_attrs = get_child_attrs(4)
            # 收集这些子部分的 code，尽管主要跳转逻辑在 process_if_statement 中生成
            current_code = (
                cond_expr_attrs.get("code", [])
                + true_block_attrs.get("code", [])
                + tail_else_part_attrs.get("code", [])
            )
            return {
                "is_else_if": True,
                "condition": cond_expr_attrs,
                "true_block": true_block_attrs,
                "remaining_else_part": tail_else_part_attrs,
                "is_empty": False,
                "code": current_code,  # 传递子代码，但实际控制流代码由process_if_statement生成
            }
        # elif production_rule_str == "WhileStatement -> WHILE Expression StatementBlock":
        #     cond_expr_attrs = get_child_attrs(1)
        #     body_block_attrs = get_child_attrs(2)
        #     return self.process_while_loop(
        #         cond_expr_attrs, body_block_attrs, approx_loc
        #     )
        elif (
            production_rule_str
            == "ForStatement -> FOR VariableDeclarationInner IN IterableStructure StatementBlock"
        ):
            loop_var_decl_attrs = get_child_attrs(1)
            iterable_attrs = get_child_attrs(3)
            body_block_attrs = get_child_attrs(4)
            return self.process_for_loop(
                loop_var_decl_attrs, iterable_attrs, body_block_attrs, approx_loc
            )
        elif (
            production_rule_str == "LoopStatement -> LOOP StatementBlock"
        ):  # 普通 loop 语句
            body_block_attrs = get_child_attrs(1)
            return self.process_loop_statement(body_block_attrs, approx_loc)
        ## 1..a+1
        elif production_rule_str == "IterableStructure -> Expression DOTDOT Expression":
            left_expr = get_child_attrs(0)
            right_expr = get_child_attrs(2)
            code = []
            code.extend(left_expr.get("code", []))
            code.extend(right_expr.get("code", []))
            return {"left": left_expr, "right": right_expr, "code": code}
        # --- BlockExpression & related ---
        elif production_rule_str == "Expression -> BlockExpression":
            return get_child_attrs(0)
        elif production_rule_str == "BlockExpression -> LBRACE BlockStmtList RBRACE":
            self.enter_scope()  # 块表达式引入新作用域
            block_stmt_list_attrs = get_child_attrs(1)
            self.exit_scope()
            # BlockStmtList 应返回 {type, place, code}
            return block_stmt_list_attrs
        elif production_rule_str == "BlockStmtList -> Expression":  # 块以表达式结尾
            expr_attrs = get_child_attrs(0)
            return {
                "type": expr_attrs.get("type"),
                "place": expr_attrs.get("place"),
                "code": expr_attrs.get("code", []),
            }
        elif production_rule_str == "BlockStmtList -> Statement BlockStmtList":
            stmt_attrs = get_child_attrs(0)
            tail_list_attrs = get_child_attrs(1)
            combined_code = stmt_attrs.get("code", []) + tail_list_attrs.get("code", [])
            # 类型和place由尾部列表决定 (如果尾部是Expression)
            return {
                "type": tail_list_attrs.get("type", "void"),
                "place": tail_list_attrs.get("place"),
                "code": combined_code,
            }

        # --- Advanced Expressions ---
        elif production_rule_str == "Expression -> ConditionalExpression":
            return get_child_attrs(0)
        elif production_rule_str == "Expression -> LoopExpression":
            return get_child_attrs(0)
        elif (
            production_rule_str == "LoopExpression -> LOOP StatementBlock"
        ):  # loop 表达式
            body_block_attrs = get_child_attrs(1)
            return self.process_loop_expression(body_block_attrs, approx_loc)
        elif (
            production_rule_str
            == "ConditionalExpression -> IF Expression BlockExpression ELSE BlockExpression"
        ):
            cond_expr_attrs = get_child_attrs(1)
            true_block_expr_attrs = get_child_attrs(2)
            false_block_expr_attrs = get_child_attrs(4)
            return self.process_conditional_expression(
                cond_expr_attrs,
                true_block_expr_attrs,
                false_block_expr_attrs,
                approx_loc,
            )

        # --- Tuple Literal Internals ---
        elif production_rule_str == "TupleAssignmentInternal -> epsilon":
            return {"elements": [], "code": []}
        elif (
            production_rule_str
            == "TupleAssignmentInternal -> Expression COMMA TupleAssignmentList"
        ):
            first_expr_attrs = get_child_attrs(0)
            tuple_list_attrs = get_child_attrs(2)
            elements = [first_expr_attrs] + tuple_list_attrs.get("elements", [])
            code = first_expr_attrs.get("code", []) + tuple_list_attrs.get("code", [])
            return {"elements": elements, "code": code}
        elif production_rule_str == "TupleAssignmentList -> epsilon":
            return {"elements": [], "code": []}
        elif production_rule_str == "TupleAssignmentList -> Expression":
            expr_attrs = get_child_attrs(0)
            return {"elements": [expr_attrs], "code": expr_attrs.get("code", [])}
        elif production_rule_str == "Factor -> AMP MUT Factor":
            factor_to_get_address_attrs = get_child_attrs(2)
            return self.process_reference_op("&mut", factor_to_get_address_attrs, approx_loc)
        elif production_rule_str == "Factor -> MULT Factor":
            factor_to_dereference_attrs = get_child_attrs(1)
            return self.process_reference_op("*", factor_to_dereference_attrs, approx_loc)
        elif (
            production_rule_str
            == "TupleAssignmentList -> Expression COMMA TupleAssignmentList"
        ):
            expr_attrs = get_child_attrs(0)
            tail_list_attrs = get_child_attrs(2)
            elements = [expr_attrs] + tail_list_attrs.get("elements", [])
            code = expr_attrs.get("code", []) + tail_list_attrs.get("code", [])
            return {"elements": elements, "code": code}
        elif production_rule_str == "Factor -> AMP Factor":
            factor_to_get_address_attrs = get_child_attrs(1)
            return self.process_reference_op("&", factor_to_get_address_attrs, approx_loc)
        elif production_rule_str == "WhileHeader -> WHILE Expression":
            while_token = get_token_obj_from_child(0)
            cond_expr_attrs = get_child_attrs(1)
            
            line_num = while_token['loc']['row'] if while_token and 'loc' in while_token else approx_loc

            loop_data_from_begin = self.process_while_loop_begin(line_num)
            
            quads_for_condition = []
            quads_for_condition.extend(cond_expr_attrs.get("code", []))
            
            if cond_expr_attrs.get("type") not in ["bool", "i32"]: # 假设条件可以是 bool 或 i32
                raise SemanticError(
                    f"While condition must be bool or i32, found {self.get_type_name(cond_expr_attrs.get('type'))}.",
                    line_num
                )
            
            self.add_quad("IF_FALSE", cond_expr_attrs.get("place"), result=loop_data_from_begin["end_label"])
            quads_for_condition.append(self.quadruples.pop())
            
            all_header_quads = loop_data_from_begin.get("quads", []) + quads_for_condition
            
            return {
                "quads": all_header_quads,
                "loop_data_ref": loop_data_from_begin
            }

        elif production_rule_str == "WhileStatement -> WhileHeader StatementBlock WhileEpilogue":
            header_attrs = get_child_attrs(0)    # 来自 WhileHeader 的归约结果
            body_attrs = get_child_attrs(1)      # 来自 StatementBlock 的归约结果
            epilogue_attrs = get_child_attrs(2)  # 来自 WhileEpilogue 的归约结果

            all_quads = []
            all_quads.extend(header_attrs.get("quads", []))
            all_quads.extend(body_attrs.get("code", []))
            all_quads.extend(epilogue_attrs.get("quads", []))
            
            return {"code": all_quads, "type": "void"}

        elif production_rule_str == "WhileEpilogue -> epsilon":
            if not self.loop_stack or self.loop_stack[-1]["type"] != "while":
                raise SemanticError("Internal error: WhileEpilogue reached with invalid or missing 'while' context on loop_stack.", approx_loc)
            
            current_loop_ctx = self.loop_stack[-1] # 不要立即 pop！！！

            end_attrs = self.process_while_loop_end({"loop_ctx": current_loop_ctx, "start_label": current_loop_ctx["start_label"], "end_label": current_loop_ctx["end_label"]}, approx_loc)
            
            return {"quads": end_attrs.get("quads", [])}
        elif production_rule_str == "LoopExprMarkerBegin -> LOOP":
            loop_token = get_token_obj_from_child(0)
            line_num = loop_token['loc']['row'] if loop_token and 'loc' in loop_token else approx_loc
            
            # 调用 process_loop_begin，标记为表达式，它会压栈 loop_stack
            # 并返回其生成的四元式 (如 LABEL) 和 loop_ctx (包含标签等信息)
            attrs_from_begin = self.process_loop_begin(is_expression=True, line_num=line_num)
            return attrs_from_begin
        
        elif production_rule_str == "LoopExpression -> LoopExprMarkerBegin StatementBlock LoopExprMarkerEnd":
            begin_attrs = get_child_attrs(0)
            body_attrs = get_child_attrs(1)
            end_attrs = get_child_attrs(2)

            # 按顺序合并所有四元式
            all_quads = []
            all_quads.extend(begin_attrs.get("quads", []))
            all_quads.extend(body_attrs.get("code", []))
            all_quads.extend(end_attrs.get("quads", []))
            
            return {
                "type": end_attrs.get("type"),
                "place": end_attrs.get("place"),
                "code": all_quads
            }

        elif production_rule_str == "LoopExprMarkerEnd -> epsilon":
            if not self.loop_stack or self.loop_stack[-1]["type"] != "loop" or not self.loop_stack[-1].get("is_expr_loop"):
                raise SemanticError("Internal error: LoopExprMarkerEnd reached with invalid or missing 'loop expression' context on loop_stack.", approx_loc)
            
            loop_ctx_from_stack = self.loop_stack[-1] # 获取上下文
            
            attrs_from_end = self.process_loop_end({"loop_ctx": loop_ctx_from_stack}, approx_loc)
            return attrs_from_end 

        elif production_rule_str == "LoopStmtMarkerBegin -> LOOP":
            loop_token = get_token_obj_from_child(0)
            line_num = loop_token['loc']['row'] if loop_token and 'loc' in loop_token else approx_loc
            
            attrs_from_begin = self.process_loop_begin(is_expression=False, line_num=line_num)
            return attrs_from_begin

        elif production_rule_str == "LoopStatement -> LoopStmtMarkerBegin StatementBlock LoopStmtMarkerEnd":
            begin_attrs = get_child_attrs(0)
            body_attrs = get_child_attrs(1)
            end_attrs = get_child_attrs(2)

            all_quads = []
            all_quads.extend(begin_attrs.get("quads", []))
            all_quads.extend(body_attrs.get("code", []))
            all_quads.extend(end_attrs.get("quads", []))
            
            return {"code": all_quads, "type": "void"}

        elif production_rule_str == "LoopStmtMarkerEnd -> epsilon":
            if not self.loop_stack or self.loop_stack[-1]["type"] != "loop" or self.loop_stack[-1].get("is_expr_loop"):
                raise SemanticError("Internal error: LoopStmtMarkerEnd reached with invalid or missing 'loop statement' context on loop_stack.", approx_loc)
            
            loop_ctx_from_stack = self.loop_stack[-1]
            
            attrs_from_end = self.process_loop_end({"loop_ctx": loop_ctx_from_stack}, approx_loc)
            return attrs_from_end

        else: # NOT ALLOWED！！！
            print(
                f"警告: dispatch_semantic_action 中 '{production_rule_str}' (行 ~{approx_loc}) 未精确匹配，使用默认聚合/传递。"
            )
            collected_code = []
            passed_attrs = {}
            first_significant_child_attrs = None

            for i, child_attr in enumerate(children_attrs):
                if child_attr:
                    collected_code.extend(child_attr.get("code", []))
                    if i == 0 and not child_attr.get("is_empty", False):
                        first_significant_child_attrs = child_attr

            if first_significant_child_attrs:
                passed_attrs = {
                    k: v
                    for k, v in first_significant_child_attrs.items()
                    if k != "code"
                }

            passed_attrs["code"] = collected_code

            # 更安全的默认：如果不是明确的链式规则 A -> B，只返回合并的 code
            is_simple_chain = False
            parts = production_rule_str.split("->")
            if len(parts) == 2:
                rhs_symbols_str_list = parts[1].strip().split(" ")
                if (
                    len(rhs_symbols_str_list) == 1
                    and children_attrs
                    and children_attrs[0] is not None
                ):
                    is_simple_chain = True

            if is_simple_chain:
                # 对于 A -> B，直接返回 B 的所有属性
                print(
                    f"调试: 应用默认链式规则传递 '{production_rule_str}' -> child 0 attrs: {children_attrs[0]}"
                )
                return children_attrs[0]
            else:
                # 对于其他未处理规则，至少返回收集到的代码
                print(
                    f"警告: '{production_rule_str}' 未显式处理，仅聚合代码。返回: {passed_attrs}"
                )
                return {"code": collected_code}  # 或者 passed_attrs 如果你认为它更合适

    def get_symbol_table_string_for_debug(self):
        output = []
        output.append("\n--- Symbol Table (Final State) ---")
        level = 0
        for scope_table in self.symbol_tables:
            output.append(f"Scope Level: {level}")
            if not scope_table:
                output.append("  <empty>")
            for name, entry in scope_table.items():
                extra = f", extra: {entry.extra_info}" if entry.extra_info else ""
                mut = "mut" if entry.is_mutable else "immut"
                init = "init" if entry.initialized else "uninit"
                output.append(
                    f"  {name}: type={self.get_type_name(entry.data_type)}, kind={entry.sym_type.name}, scope={entry.scope_level}, {mut}, {init}{extra}"
                )
            level += 1
        output.append("--------------------")
        return "\n".join(output)

    # 3.1 if整体处理
    def process_if_statement(
        self, condition_attrs, true_block_attrs, else_block_attrs=None, line_num=0
    ):
        """
        处理 if 语句（或 if-else 语句），用于语义分析器中的四元式生成。

        参数:
            condition_attrs: 条件表达式的属性字典 {'type': str, 'place': str, 'code': list}
            true_block_attrs: if 条件成立时的代码块属性 {'code': list}
            else_block_attrs: else 块的属性，如果没有则为 None {'code': list}
            line_num: 当前处理的源代码行号，用于错误报告
        返回:
            dict: 包含生成的四元式列表：{'code': quads}
        """

        # 1. 处理 if 条件部分
        if_data = self.process_if_construct_begin(condition_attrs, line_num)
        quads = []
        quads.extend(if_data["quads"])  # 条件表达式的代码

        # 2. 添加 true block 的代码
        quads.extend(true_block_attrs.get("code", []))

        # 3. true block 结束后，跳转到整个 if 结构的末尾
        end_label = self._new_label()
        self.add_quad("JUMP", result=end_label)
        quads.append(self.quadruples.pop())

        # 4. 处理 elseif/else 分支
        if else_block_attrs:
            # 添加 elseif 或 else 的 LABEL
            if_else_data = self.process_if_true_block_end(
                if_data, is_if_expression=False, line_num=line_num
            )
            self.process_else_block_begin(if_else_data, line_num)
            quads.append(self.quadruples.pop())

            if else_block_attrs.get("is_else_if"):
                # 递归处理 elseif 分支
                elseif_result = self.process_if_statement(
                    else_block_attrs["condition"],
                    else_block_attrs["true_block"],
                    else_block_attrs["remaining_else_part"],
                    line_num,
                )
                quads.extend(elseif_result["code"])
            else:
                # 处理 else 分支
                quads.extend(else_block_attrs.get("code", []))

        # 5. 添加整个 if 结构的结束 LABEL
        self.add_quad("LABEL", result=end_label)
        quads.append(self.quadruples.pop())

        return {"code": quads}

    # 5.1 while循环整体处理
    def process_while_loop(self, cond_expr_attrs, body_block_attrs, line_num):
        # 1. 开始 while 循环，生成起始 LABEL
        loop_data = self.process_while_loop_begin(line_num)

        # 2. 分析条件表达式，生成 IF_FALSE 条件跳转
        cond_result = self.process_while_condition(cond_expr_attrs, loop_data, line_num)

        # 3. 合并 while 循环体的代码
        body_quads = body_block_attrs.get("code", [])

        # 4. 生成结尾跳转回条件处 和 end_label
        end_result = self.process_while_loop_end(loop_data, line_num)

        # 5. 整合四元式代码
        total_code = []
        total_code.extend(loop_data["quads"])  # 开头 LABEL
        total_code.extend(cond_result["quads"])  # 条件跳转
        total_code.extend(body_quads)  # 循环体
        total_code.extend(end_result["quads"])  # 尾部 JUMP 和 exit LABEL

        return {"code": total_code}

    # 5.3 loop语句整体处理
    # depreciated
    # def process_loop_expression(self, body_block_attrs, line_num):
    #     """
    #     处理 loop 表达式形式（即作为表达式的 loop，而非语句），
    #     如 Rust 中的: `let x = loop { if cond { break 42; } }`
    #     """
    #     # Step 1: 开始 loop 表达式
    #     loop_data = self.process_loop_begin(is_expression=True, line_num=line_num)

    #     # Step 2: 生成 loop 体中间代码
    #     quads = []
    #     quads.extend(loop_data["quads"])  # loop start LABEL
    #     quads.extend(body_block_attrs.get("code", []))

    #     # Step 3: 结束 loop，获取返回表达式的属性
    #     result_attrs = self.process_loop_end(loop_data, line_num)
    #     quads.extend(result_attrs.get("quads", []))  # end LABEL + break assign quads

    #     # Step 4: 返回表达式类型、结果存储变量及中间代码
    #     return {
    #         "type": result_attrs.get("type"),
    #         "place": result_attrs.get("place"),
    #         "code": quads,
    #     }

    # 5.2 for循环整体处理，无process_for_loop属性
    def process_for_loop(
        self, loop_var_decl_attrs, iterable_attrs, body_block_attrs, line_num
    ):
        quads = []

        # 提取循环变量名，例如 i
        loop_var_name = loop_var_decl_attrs["name"]

        # 提取区间左右表达式，如 a..b
        range_start_expr = iterable_attrs["left"]
        range_end_expr = iterable_attrs["right"]

        # 开始 for 循环（初始化 start/end/iter_temp 和跳转逻辑）
        begin_result = self.process_for_loop_begin(
            loop_var_name, range_start_expr, range_end_expr, line_num
        )
        quads.extend(begin_result["quads"])

        # 插入循环体 block 的四元式
        quads.extend(body_block_attrs.get("code", []))

        # 结束 for 循环（++i, 跳转到开始，插入结束标签）
        end_result = self.process_for_loop_end(begin_result["loop_data"], line_num)
        quads.extend(end_result["quads"])

        return {"code": quads}
    
    # 7.3 条件表达式整体处理
    def process_conditional_expression(self, cond_expr_attrs, true_block_attrs, false_block_attrs, line_num):
        quads = []

        # 获取条件表达式的中间代码和结果变量
        quads.extend(cond_expr_attrs.get("code", []))
        cond_place = cond_expr_attrs["place"]

        # 新建标签
        label_true = self._new_label()
        label_false = self._new_label()
        label_end = self._new_label()

        # IF 跳转语句
        quads.append(Quadruple("IF_GOTO", cond_place, None, label_true))
        quads.append(Quadruple("GOTO", None, None, label_false))

        # true 分支
        quads.append(Quadruple("LABEL", None, None, label_true))
        quads.extend(true_block_attrs.get("code", []))
        true_val = true_block_attrs["place"]

        # 使用统一的结果 temp
        result_temp = self._new_temp()
        quads.append(Quadruple("ASSIGN", true_val, None, result_temp))
        quads.append(Quadruple("GOTO", None, None, label_end))

        # false 分支
        quads.append(Quadruple("LABEL", None, None, label_false))
        quads.extend(false_block_attrs.get("code", []))
        false_val = false_block_attrs["place"]
        quads.append(Quadruple("ASSIGN", false_val, None, result_temp))

        # 结束标签
        quads.append(Quadruple("LABEL", None, None, label_end))

        # 类型推导（简单处理：若类型不同，以 true 分支为主，可扩展类型兼容检查）
        result_type = true_block_attrs["type"]
        if true_block_attrs["type"] != false_block_attrs["type"]:
            self._report_type_warning_or_error(true_block_attrs["type"], false_block_attrs["type"], line_num)

        return {
            "type": result_type,
            "place": result_temp,
            "code": quads,
        }


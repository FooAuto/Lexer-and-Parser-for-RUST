from enum import Enum
from lexer.token import tokenType

class SymbolType(Enum):
    VARIABLE = 1
    FUNCTION = 2
    PARAMETER = 3
    ARRAY = 4
    TUPLE = 5
    REFERENCE = 6 # 用于 &T 和 &mut T

class Quadruple:
    def __init__(self, op, arg1, arg2, result):
        self.op = op
        self.arg1 = arg1
        self.arg2 = arg2
        self.result = result

    def __str__(self):
        return f"({self.op}, {self.arg1 or '_'}, {self.arg2 or '_'}, {self.result or '_'})"

class SymbolTableEntry:
    def __init__(self, name, sym_type, data_type, scope_level, is_mutable=False, initialized=True, extra_info=None):
        self.name = name             # 名字
        self.sym_type = sym_type     # id类型 SymbolTypes
        self.data_type = data_type   # 实际数据类型，比如i32
        self.scope_level = scope_level # 作用域
        self.is_mutable = is_mutable # 是否可修改
        self.initialized = initialized # 是否初始化
        self.extra_info = extra_info if extra_info is not None else {} # For func params, array/tuple details, reference details
        # extra_info for FUNCTION: {'params': [{'name': 'p1', 'type': 'i32', 'is_mutable': False}, ...], 'return_type': 'i32'}
        # extra_info for ARRAY: {'element_type': 'i32', 'length': 3}
        # extra_info for TUPLE: {'element_types': ['i32', 'bool']}
        # extra_info for REFERENCE: {'target_type': 'i32', 'is_mutable_ref': True/False}
        self.line_declared = -1 # Placeholder, set this during declaration
        self.active_borrows = {"mutable": 0, "immutable": 0} # For borrow checking

class SemanticError(Exception):
    def __init__(self, message, line_num=None):
        self.message = message
        self.line_num = line_num
        super().__init__(f"Semantic Error: {message}" + (f" at line {line_num}" if line_num else ""))

# 实际语义分析执行类
class SemanticAnalyzer:
    def __init__(self):
        self.symbol_tables = [{}]
        self.current_scope_level = 0
        self.quadruples = []
        self.temp_var_count = 0
        self.label_count = 0
        self.current_function = None # 当前函数的返回值
        self.loop_stack = [] # For break/continue

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

    def add_symbol(self, name, sym_type, data_type, line_num, is_mutable=False, initialized=True, extra_info=None):
        if name in self.symbol_tables[self.current_scope_level]:
            # Handle shadowing: if a symbol with the same name exists in the current scope, it's an error
            # Rust allows shadowing, so we actually overwrite.
            # However, the PDF implies some re-declaration might be errors.
            # For now, we allow shadowing by overwriting.
            # If strict "no re-declaration in same scope" is needed, add a check here.
            # TODO：目前这里对于二次申明是覆盖第一次，认为放行。可能需要进一步考虑
            pass # Shadowing is allowed by overwriting.

        entry = SymbolTableEntry(name, sym_type, data_type, self.current_scope_level, is_mutable, initialized, extra_info)
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
        """ Helper to get a string representation of a complex type. """
        if isinstance(data_type, str):
            return data_type
        elif isinstance(data_type, list): # Array or Reference
            if data_type[0] == '[': # Array: ['[', type, size]
                return f"[{self.get_type_name(data_type[1])}; {data_type[2]}]"
            elif data_type[0] == '&': # Reference: ['&', type] or ['&mut', type]
                if len(data_type) == 2: # Immutable reference
                    return f"&{self.get_type_name(data_type[1])}"
                else: # Mutable reference ['&mut', type]
                    return f"&mut {self.get_type_name(data_type[1])}"
        elif isinstance(data_type, tuple): # Tuple: (type1, type2, ...)
            return f"({', '.join(self.get_type_name(t) for t in data_type)})"
        return "unknown_type"


    def check_type_compatibility(self, type1, type2, line_num, allow_ref_deref=True):
        """
        Checks if type2 can be assigned to or used where type1 is expected.
        Includes basic reference compatibility (e.g., &T can be used for &T, T for *&T).
        """
        s_type1 = self.get_type_name(type1)
        s_type2 = self.get_type_name(type2)

        if s_type1 == s_type2:
            return True

        # Allow assigning T to an uninitialized let binding without explicit type
        if type1 == "unknown_inferred":
            return True

        # Dereferencing: if type1 is T and type2 is &T or &mut T
        if allow_ref_deref:
            if isinstance(type2, list) and type2[0] in ['&', '&mut']: # type2 is a reference
                deref_type2 = type2[1] if type2[0] == '&' else type2[1] # type2[1] is T in &T or &mut T
                if self.get_type_name(type1) == self.get_type_name(deref_type2):
                     # This case is usually handled by explicit deref '*' op,
                     # but some languages allow auto-deref in assignments.
                     # For this Rust-like lang, explicit deref is better.
                     # So, this direct compatibility might be too lenient without a '*'
                    pass # Potentially allow if context implies dereference


        raise SemanticError(f"Type mismatch: expected {s_type1}, found {s_type2}.", line_num)

    # 罗列具体的语义规则与语义分析
    # Rule 0.1: <变量声明内部> -> mut <ID>
    # Rule 6.1: <变量声明内部> -> <ID>
    def process_variable_decl_internal(self, p_id, is_mutable_token, line_num):
        # p_id is the token object for ID
        # is_mutable_token is the token object for 'mut' or None
        # Returns: {'name': id_name, 'is_mutable': True/False, 'line': line_num}
        # This information is then used by rules 2.1, 2.3, 1.4, 5.2
        id_name = p_id['content']
        is_mut = True if is_mutable_token else False
        return {'name': id_name, 'is_mutable': is_mut, 'line': p_id['loc']['row']}

    # Rule 0.2: <类型> -> i32 | & <类型> | & mut <类型> | '[' <类型> ';' <NUM> ']' | '(' <元组类型内部> ')'
    def process_type(self, type_token_or_structure, line_num):
        # type_token_or_structure can be:
        #   - 'i32' (string from token)
        #   - {'op': '&', 'type': processed_type}
        #   - {'op': '&mut', 'type': processed_type}
        #   - {'op': 'array', 'element_type': processed_type, 'size': num_val}
        #   - {'op': 'tuple', 'element_types': [processed_type1, ...]}
        # Returns the internal representation of the type.
        if isinstance(type_token_or_structure, str) and type_token_or_structure == 'i32':
            return 'i32'
        elif isinstance(type_token_or_structure, dict):
            op = type_token_or_structure['op']
            if op == '&':
                return ['&', self.process_type(type_token_or_structure['type'], line_num)]
            elif op == '&mut':
                return ['&mut', self.process_type(type_token_or_structure['type'], line_num)]
            elif op == 'array':
                size = int(type_token_or_structure['size'])
                if size <= 0:
                    raise SemanticError("Array size must be positive.", line_num)
                return ['[', self.process_type(type_token_or_structure['element_type'], line_num), size]
            elif op == 'tuple':
                return tuple(self.process_type(t, line_num) for t in type_token_or_structure['element_types'])
        raise SemanticError(f"Unknown type structure: {type_token_or_structure}", line_num)


    # Rule 1.1, 1.5, 7.2: Function Declaration
    def process_function_declaration_header(self, fn_name_token, params_list, return_type_processed, line_num):
        # params_list: [{'name': str, 'is_mutable': bool, 'type': processed_type, 'line': int}, ...]
        # return_type_processed: processed type or 'void' if no return type
        fn_name = fn_name_token['content']
        if self.lookup_symbol(fn_name, None) is not None and self.symbol_tables[0].get(fn_name).sym_type == SymbolType.FUNCTION:
            raise SemanticError(f"Function '{fn_name}' already declared.", line_num)

        param_info_for_symtable = []
        for p_attr in params_list:
            param_info_for_symtable.append({
                'name': p_attr['name'],
                'type': p_attr['type'],
                'is_mutable': p_attr['is_mutable']
            })

        extra_info = {'params': param_info_for_symtable, 'return_type': return_type_processed}
        self.add_symbol(fn_name, SymbolType.FUNCTION, return_type_processed, line_num, extra_info=extra_info)
        self.current_function = {'name': fn_name, 'return_type': return_type_processed, 'entry_label': self._new_label()}
        self.add_quad("FUNC_BEGIN", arg1=fn_name, result=self.current_function['entry_label'])

        self.enter_scope() # Enter function body scope
        for p_attr in params_list:
            self.add_symbol(p_attr['name'], SymbolType.PARAMETER, p_attr['type'], p_attr['line'], is_mutable=p_attr['is_mutable'], initialized=True)
            self.add_quad("PARAM_DECL", arg1=p_attr['name']) # Or handle params differently in call
        return {'name': fn_name, 'label': self.current_function['entry_label']}


    def process_function_body_end(self, func_name, line_num):
        # Called after processing function body's statements or expression block
        if self.current_function and self.current_function['name'] == func_name:
            # For void functions, ensure no value was left on "stack" if expression block
            # If it's an expression block, the last expression's value should be returned implicitly if types match
            # This is handled by process_return / end of expression block
            self.add_quad("FUNC_END", arg1=func_name)
            self.exit_scope()
            self.current_function = None
        else:
            raise SemanticError("Mismatched function end.", line_num)


    # Rule 1.3: return ;
    # Rule 1.5: return <expr> ;
    # Rule 7.4: break <expr> ; (for loop expressions, context-dependent)
    def process_return_statement(self, expr_attrs, line_num, is_break_expr=False):
        # expr_attrs: {'type': type, 'place': temp_var_or_const, 'code': [quads]} or None for 'return;'
        op = "BREAK_VAL" if is_break_expr else "RETURN_VAL"
        target_type_container = None

        if is_break_expr:
            if not self.loop_stack or not self.loop_stack[-1].get('is_expr_loop'):
                raise SemanticError("'break <expression>;' can only be used inside a loop expression.", line_num)
            loop_ctx = self.loop_stack[-1]
            if loop_ctx.get('expr_type') == "unknown_inferred":
                if not expr_attrs: # break; in loop expr
                    raise SemanticError("Loop expression 'break' must provide a value.", line_num)
                loop_ctx['expr_type'] = expr_attrs['type'] # Infer loop type from first break
            target_type_container = loop_ctx['expr_type']
        else: # Regular return
            if not self.current_function:
                raise SemanticError("Return statement outside of function.", line_num)
            target_type_container = self.current_function['return_type']


        quads = []
        if expr_attrs:
            quads.extend(expr_attrs.get('code', []))
            self.check_type_compatibility(target_type_container, expr_attrs['type'], line_num)
            self.add_quad(op, arg1=expr_attrs['place'])
            return {'type': expr_attrs['type'], 'place': expr_attrs['place'], 'code': quads} # For expression blocks
        else: # return; or break; (break; is not allowed in loop expr)
            if is_break_expr:
                 raise SemanticError("Loop expression 'break' must provide a value.", line_num)

            if target_type_container != 'void':
                raise SemanticError(f"Function '{self.current_function['name']}' expects a return value of type {self.get_type_name(target_type_container)}.", line_num)
            self.add_quad("RETURN") # For void return
            return {'type': 'void', 'place': None, 'code': quads}


    # Rule 2.1: let <var_decl_internal> : <type> ;
    # Rule 2.1: let <var_decl_internal> ; (Type inference needed)
    def process_variable_declaration(self, var_decl_internal_attrs, type_attrs, line_num):
        # var_decl_internal_attrs: {'name': str, 'is_mutable': bool, 'line': int}
        # type_attrs: {'type': processed_type, 'code': []} or None
        var_name = var_decl_internal_attrs['name']
        is_mutable = var_decl_internal_attrs['is_mutable']
        decl_line = var_decl_internal_attrs['line']

        var_type = "unknown_inferred"
        quads = []

        if type_attrs:
            var_type = type_attrs['type']
            if 'code' in type_attrs: quads.extend(type_attrs['code']) # e.g. for array type def

        self.add_symbol(var_name, SymbolType.VARIABLE, var_type, decl_line, is_mutable, initialized=False)
        # No direct quadruple for 'let x: i32;' until assignment, unless for memory allocation planning
        # For now, symbol table entry is enough.
        return {'name': var_name, 'type': var_type, 'is_mutable': is_mutable, 'code': quads, 'place': var_name}


    # Rule 2.2: <assignable> = <expr> ;
    def process_assignment(self, assignable_attrs, expr_attrs, line_num):
        # assignable_attrs: {'name': str, 'type': type, 'is_lvalue': True, 'is_mutable': bool, 'place': var_name_or_addr_calc, 'code': []}
        # expr_attrs: {'type': type, 'place': temp_var_or_const, 'code': []}
        quads = []
        quads.extend(assignable_attrs.get('code', [])) # Code for LHS (e.g., array index calc)
        quads.extend(expr_attrs.get('code', []))     # Code for RHS expression

        lvalue_entry = self.lookup_symbol(assignable_attrs['name'], line_num) # For simple vars

        if not assignable_attrs.get('is_lvalue', False): # Should be caught by grammar if <assignable> is correct
            raise SemanticError(f"Cannot assign to non-lvalue '{assignable_attrs.get('name', 'expression')}'.", line_num)

        # For simple variable assignment:
        if lvalue_entry.sym_type in [SymbolType.VARIABLE, SymbolType.PARAMETER]:
            if not lvalue_entry.is_mutable and lvalue_entry.initialized: # Allow first init of let x;
                raise SemanticError(f"Cannot assign to immutable variable '{lvalue_entry.name}'.", line_num)

            # Type check:
            # If lvalue_entry.data_type is 'unknown_inferred', update it.
            if lvalue_entry.data_type == "unknown_inferred":
                lvalue_entry.data_type = expr_attrs['type']
            else:
                self.check_type_compatibility(lvalue_entry.data_type, expr_attrs['type'], line_num)

            lvalue_entry.initialized = True

        # For array/tuple element assignment, mutability and type checks are more complex:
        # assignable_attrs['type'] here would be the *element* type.
        # assignable_attrs['base_mutable'] would be needed for array/tuple itself.
        elif assignable_attrs.get('sym_type') in [SymbolType.ARRAY, SymbolType.TUPLE]: # Element assignment
             if not assignable_attrs.get('base_is_mutable') and not assignable_attrs.get('is_temp_lvalue', False): # is_temp_lvalue for *(&mut arr)[idx]
                 raise SemanticError(f"Cannot assign to element of immutable '{assignable_attrs['name']}'.", line_num)
             self.check_type_compatibility(assignable_attrs['type'], expr_attrs['type'], line_num)


        self.add_quad("ASSIGN", expr_attrs['place'], result=assignable_attrs['place'])
        quads.append(self.quadruples.pop()) # Add the assign quad to the local list

        return {'code': quads}


    # Rule 2.3: let <var_decl_internal> : <type> = <expr> ;
    # Rule 2.3: let <var_decl_internal> = <expr> ;
    def process_variable_declaration_assignment(self, var_decl_internal_attrs, type_attrs, expr_attrs, line_num):
        var_name = var_decl_internal_attrs['name']
        is_mutable = var_decl_internal_attrs['is_mutable']
        decl_line = var_decl_internal_attrs['line']
        quads = []
        quads.extend(expr_attrs.get('code', []))

        var_type = expr_attrs['type']
        if type_attrs: # Explicit type given
            explicit_type = type_attrs['type']
            if 'code' in type_attrs: quads.extend(type_attrs['code'])
            self.check_type_compatibility(explicit_type, expr_attrs['type'], line_num)
            var_type = explicit_type # Use the declared type

        self.add_symbol(var_name, SymbolType.VARIABLE, var_type, decl_line, is_mutable, initialized=True)
        self.add_quad("ASSIGN", expr_attrs['place'], result=var_name)
        quads.append(self.quadruples.pop())

        return {'name': var_name, 'type': var_type, 'is_mutable': is_mutable, 'code': quads, 'place': var_name}


    # Rule 3.1 <元素> -> <NUM> | <可赋值元素> | ( <表达式> )
    def process_element(self, element_token_or_attrs, line_num):
        # element_token_or_attrs:
        #  - if NUM: {'type': tokenType.INTEGER_CONSTANT, 'content': '123', 'loc': ...}
        #  - if <可赋值元素> (ID, array_access, tuple_access): result of process_assignable_element
        #  - if (<表达式>): result of process_expression (expr_attrs)

        if isinstance(element_token_or_attrs, dict) and 'prop' in element_token_or_attrs : # Terminal token like NUM
            token_prop = element_token_or_attrs['prop']
            token_content = element_token_or_attrs['content']
            if token_prop == tokenType.INTEGER_CONSTANT:
                # For constants, 'place' is the constant value itself
                return {'type': 'i32', 'place': int(token_content), 'code': []}
            # Add other constants like CHAR_CONSTANT, STRING_CONSTANT if they are expressions
            else:
                raise SemanticError(f"Unsupported terminal in expression: {token_content}", line_num)

        # If it's from <可赋值元素> or (<表达式>), it's already processed attrs
        # For <可赋值元素>, it needs to be treated as an R-value.
        # 'place' could be a variable name or a temporary holding an array/tuple element's value.
        # A 'LOAD' quad might be needed if 'place' is a direct variable name and we need its value in a temp.
        # For simplicity, if 'place' is a variable, downstream ops will use it directly.
        # If it's a complex l-value (like a[i]), its 'place' is already a temp from address calculation.
        elif isinstance(element_token_or_attrs, dict) and 'type' in element_token_or_attrs:
            # If it's an LValue used as RValue, ensure it's initialized
            if 'name' in element_token_or_attrs and not element_token_or_attrs.get('is_temp_lvalue'):
                entry = self.lookup_symbol(element_token_or_attrs['name'], line_num)
                if not entry.initialized:
                    raise SemanticError(f"Variable '{entry.name}' used before initialization.", line_num)

                # If the LValue was an array/tuple itself, its 'place' is the name.
                # If it was an element access, its 'place' is a temp holding the value/address.
                # We might need to generate a load instruction if the 'place' is an address.
                # For now, assume 'place' from process_assignable_element holds the value or is directly usable.
                if element_token_or_attrs.get('is_lvalue_address'): # from array/tuple element access not yet dereferenced
                    temp_val = self._new_temp()
                    current_quads = element_token_or_attrs.get('code', [])
                    current_quads.append(Quadruple("LOAD_FROM_ADDR", element_token_or_attrs['place'], None, temp_val))
                    return {'type': element_token_or_attrs['type'],
                            'place': temp_val,
                            'code': current_quads}

            return element_token_or_attrs # Pass through attrs from (expr) or assignable
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
        stype = structure['type']
        quads = []

        if stype == 'id':
            id_token = structure['token']
            id_name = id_token['content']
            entry = self.lookup_symbol(id_name, line_num)
            # For LValue use, place is the name. For RValue, its value might be loaded.
            return {
                'name': id_name, 'type': entry.data_type, 'is_lvalue': True,
                'is_mutable': entry.is_mutable, 'place': id_name, 'code': [],
                'sym_type': entry.sym_type, 'initialized': entry.initialized
            }
        elif stype == 'array_access':
            base_attrs = structure['base'] # Comes from process_element
            index_attrs = structure['index'] # Comes from process_expression

            quads.extend(base_attrs.get('code', []))
            quads.extend(index_attrs.get('code', []))

            base_entry = None
            # Base can be a variable or a result of another operation (e.g. function call returning array, or *ref_to_array)
            if 'name' in base_attrs and not base_attrs.get('is_temp_lvalue'): # if base_attrs['place'] is a direct variable name
                 base_entry = self.lookup_symbol(base_attrs['name'], line_num)
                 base_type = base_entry.data_type
                 base_is_mut = base_entry.is_mutable
                 base_place = base_entry.name
            else: # Base is temporary, e.g. from *(&mut arr)[i] or func_call()[i]
                 base_type = base_attrs['type']
                 base_is_mut = base_attrs.get('is_mutable', True) # Temp results are often mutable in effect
                 base_place = base_attrs['place']


            if not (isinstance(base_type, list) and base_type[0] == '['):
                raise SemanticError(f"Cannot apply index operator to non-array type '{self.get_type_name(base_type)}'.", line_num)
            if index_attrs['type'] != 'i32':
                raise SemanticError(f"Array index must be i32, found {self.get_type_name(index_attrs['type'])}.", line_num)

            element_type = base_type[1]
            array_len = base_type[2]

            # Runtime bounds check (conceptual quad, can be expanded)
            # self.add_quad("BOUNDS_CHECK", index_attrs['place'], array_len, None)
            # quads.append(self.quadruples.pop())

            # Address calculation: result_addr = base_addr + index * element_size
            # element_size needs to be known. For i32, assume 1 unit for simplicity here.
            # More realistically, this would be platform dependent.
            addr_temp = self._new_temp()
            self.add_quad("ARRAY_ACCESS_ADDR", base_place, index_attrs['place'], addr_temp)
            quads.append(self.quadruples.pop())

            return {
                'name': base_attrs.get('name', 'array_element'), # Name for error reporting
                'type': element_type, 'is_lvalue': True, 'is_mutable': base_is_mut, # Element mutability depends on base array
                'place': addr_temp, 'code': quads, 'sym_type': SymbolType.ARRAY,
                'base_is_mutable': base_is_mut, 'is_lvalue_address': True
            }

        elif stype == 'tuple_access':
            base_attrs = structure['base']
            index_val = int(structure['index_token']['content'])
            quads.extend(base_attrs.get('code', []))

            base_entry = None
            if 'name' in base_attrs and not base_attrs.get('is_temp_lvalue'):
                 base_entry = self.lookup_symbol(base_attrs['name'], line_num)
                 base_type = base_entry.data_type
                 base_is_mut = base_entry.is_mutable
                 base_place = base_entry.name
            else:
                 base_type = base_attrs['type']
                 base_is_mut = base_attrs.get('is_mutable', True)
                 base_place = base_attrs['place']

            if not isinstance(base_type, tuple):
                raise SemanticError(f"Cannot apply '.' operator to non-tuple type '{self.get_type_name(base_type)}'.", line_num)

            if not (0 <= index_val < len(base_type)):
                raise SemanticError(f"Tuple index {index_val} out of bounds for tuple of length {len(base_type)}.", line_num)

            element_type = base_type[index_val]
            addr_temp = self._new_temp() # Placeholder for tuple element access
            self.add_quad("TUPLE_ACCESS_ADDR", base_place, index_val, addr_temp)
            quads.append(self.quadruples.pop())

            return {
                'name': base_attrs.get('name', 'tuple_element'),
                'type': element_type, 'is_lvalue': True, 'is_mutable': base_is_mut,
                'place': addr_temp, 'code': quads, 'sym_type': SymbolType.TUPLE,
                'base_is_mutable': base_is_mut, 'is_lvalue_address': True
            }
        raise SemanticError(f"Unknown assignable element structure: {stype}", line_num)


    # Rule 3.2: Arithmetic and Comparison ops
    def process_binary_op(self, op_token, left_attrs, right_attrs, line_num):
        # op_token: {'content': '+', 'prop': tokenType.PLUS, ...}
        # left_attrs, right_attrs: {'type': type, 'place': temp_or_const, 'code': []}
        op_str = op_token['content']
        quads = []
        quads.extend(left_attrs.get('code', []))
        quads.extend(right_attrs.get('code', []))

        # Type checking (assuming i32 for arithmetic, bool for comparison result)
        if op_str in ['+', '-', '*', '/']:
            self.check_type_compatibility('i32', left_attrs['type'], line_num)
            self.check_type_compatibility('i32', right_attrs['type'], line_num)
            result_type = 'i32'
            quad_op_map = {'+': "ADD", '-': "SUB", '*': "MUL", '/': "DIV"}
            quad_op = quad_op_map[op_str]
            if op_str == '/' and isinstance(right_attrs['place'], int) and right_attrs['place'] == 0:
                 raise SemanticError("Division by zero.", line_num)

        elif op_str in ['<', '<=', '>', '>=', '==', '!=']:
            # For simplicity, assume i32 comparison. Could be extended.
            self.check_type_compatibility(left_attrs['type'], right_attrs['type'], line_num) # Must be same type
            if left_attrs['type'] != 'i32': # Or allow other comparable types
                 raise SemanticError(f"Comparison not supported for type {self.get_type_name(left_attrs['type'])}.", line_num)

            result_type = 'bool' # Rust doesn't have a direct bool type like this, but result is a truth value
            quad_op_map = {'<': "LT", '<=': "LE", '>': "GT", '>=': "GE", '==': "EQ", '!=': "NE"}
            quad_op = quad_op_map[op_str]
        else:
            raise SemanticError(f"Unknown binary operator: {op_str}", line_num)

        result_place = self._new_temp()
        self.add_quad(quad_op, left_attrs['place'], right_attrs['place'], result_place)
        quads.append(self.quadruples.pop())

        return {'type': result_type, 'place': result_place, 'code': quads}


    # Rule 3.3: Function Call <ID> ( <实参列表> )
    def process_function_call(self, func_id_token, actual_args_attrs_list, line_num):
        # func_id_token: Token for the function ID
        # actual_args_attrs_list: list of {'type': type, 'place': temp_or_const, 'code': []} for each arg
        func_name = func_id_token['content']
        func_entry = self.lookup_function(func_name, line_num)
        expected_params = func_entry.extra_info['params']
        expected_return_type = func_entry.extra_info['return_type']

        quads = []

        if len(actual_args_attrs_list) != len(expected_params):
            raise SemanticError(f"Function '{func_name}' expected {len(expected_params)} arguments, but got {len(actual_args_attrs_list)}.", line_num)

        for i, arg_attrs in enumerate(actual_args_attrs_list):
            quads.extend(arg_attrs.get('code', []))
            self.check_type_compatibility(expected_params[i]['type'], arg_attrs['type'], line_num)
            self.add_quad("PARAM", arg_attrs['place']) # Push param for call
            quads.append(self.quadruples.pop())


        call_result_place = None
        if expected_return_type != 'void':
            call_result_place = self._new_temp()

        self.add_quad("CALL", func_name, len(actual_args_attrs_list), call_result_place)
        quads.append(self.quadruples.pop())

        return {'type': expected_return_type, 'place': call_result_place, 'code': quads}

    # Rule 4.1, 4.2: If-Else If-Else statement/expression
    def process_if_construct_begin(self, condition_attrs, line_num):
        # condition_attrs: {'type': type, 'place': temp_or_const, 'code': []}
        quads = []
        quads.extend(condition_attrs.get('code', []))
        # Rust's if condition doesn't strictly need 'bool', any type that can be compared to zero (for i32)
        if condition_attrs['type'] not in ['bool', 'i32']: # i32 can be 0 or non-0
            raise SemanticError(f"If condition must be a boolean or integer, found {self.get_type_name(condition_attrs['type'])}.", line_num)

        # Placeholder for jump instruction, address will be backpatched.
        # JUMP_IF_FALSE <condition_place> <label_for_else_or_endif>
        # Store index of this quad for backpatching
        after_if_label = self._new_label() # Label for code after true block (used by JUMP_IF_FALSE)
        if_quad_idx = len(self.quadruples)
        self.add_quad("IF_FALSE", condition_attrs['place'], result=after_if_label) # Target label to be filled
        quads.append(self.quadruples.pop())

        # Return the label for the 'else' or 'endif' part and the list of quads generated for condition
        return {'quads': quads, 'after_if_label': after_if_label, 'if_quad_idx': if_quad_idx}

    def process_if_true_block_end(self, if_data, is_if_expression, line_num):
        # if_data: from process_if_construct_begin
        # is_if_expression: boolean, true if it's 'if expr {block} else {block}'
        # Returns data needed for else/endif, like jump quad index and end_label for statement
        end_if_label = self._new_label() # Label for end of entire if-else structure
        else_quad_idx = -1

        if not is_if_expression: # If it's an if STMT, not if EXPR
             else_quad_idx = len(self.quadruples)
             self.add_quad("JUMP", result=end_if_label) # Jump over else block

        # Backpatch the JUMP_IF_FALSE from the if_construct_begin
        # self.quadruples[if_data['if_quad_idx']].result = if_data['after_if_label'] # this was already set

        return {'end_if_label': end_if_label,
                'after_if_label': if_data['after_if_label'], # This is where JUMP_IF_FALSE goes
                'else_jump_quad_idx': else_quad_idx if not is_if_expression else -1}


    def process_else_block_begin(self, if_else_data, line_num):
        # if_else_data: from process_if_true_block_end
        # Set the target for the original IF_FALSE jump to here (start of else)
        self.add_quad("LABEL", result=if_else_data['after_if_label'])


    def process_if_else_construct_end(self, if_else_data, is_if_expression, true_branch_attrs, else_branch_attrs, line_num):
        # if_else_data: from process_if_true_block_end (or process_else_if)
        # true_branch_attrs, else_branch_attrs: for if expressions, {'type': type, 'place': result_place, 'code': block_quads}
        quads = []

        if is_if_expression:
            if not else_branch_attrs:
                raise SemanticError("If expression must have an else block.", line_num)
            self.check_type_compatibility(true_branch_attrs['type'], else_branch_attrs['type'], line_num)
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
            return {'type': true_branch_attrs['type'], 'place': "if_expr_needs_phi_or_stack_val", 'code': quads}

        else: # If statement
            # Backpatch the JUMP from end of true block (if there was an else)
            if if_else_data.get('else_jump_quad_idx', -1) != -1 :
                 self.quadruples[if_else_data['else_jump_quad_idx']].result = if_else_data['end_if_label']
            elif if_else_data.get('if_quad_idx', -1) != -1: # No else block, backpatch the original IF_FALSE
                 self.quadruples[if_else_data['if_quad_idx']].result = if_else_data['end_if_label']


            self.add_quad("LABEL", result=if_else_data['end_if_label']) # Label for end of if-else structure
            quads.append(self.quadruples.pop())
            return {'code': quads}


    # Rule 5.1: while <expr> <block>
    def process_while_loop_begin(self, line_num):
        loop_start_label = self._new_label() # For 'continue' and jumping back
        loop_end_label = self._new_label()   # For 'break' and exiting loop

        self.add_quad("LABEL", result=loop_start_label)
        self.loop_stack.append({'type': 'while', 'start_label': loop_start_label, 'end_label': loop_end_label})
        return {'start_label': loop_start_label, 'end_label': loop_end_label, 'quads': [self.quadruples[-1]]}

    def process_while_condition(self, condition_attrs, loop_data, line_num):
        quads = []
        quads.extend(condition_attrs.get('code', []))
        if condition_attrs['type'] not in ['bool', 'i32']:
            raise SemanticError(f"While condition must be bool or i32, found {self.get_type_name(condition_attrs['type'])}.", line_num)

        # JUMP_IF_FALSE <condition_place> <loop_end_label>
        self.add_quad("IF_FALSE", condition_attrs['place'], result=loop_data['end_label'])
        quads.append(self.quadruples.pop())
        return {'quads': quads}

    def process_while_loop_end(self, loop_data, line_num):
        self.add_quad("JUMP", result=loop_data['start_label']) # Jump back to condition
        self.add_quad("LABEL", result=loop_data['end_label'])  # Label for loop exit
        if self.loop_stack and self.loop_stack[-1]['type'] == 'while':
            self.loop_stack.pop()
        else:
            raise SemanticError("Mismatched loop structure (while).", line_num)
        return {'quads': [self.quadruples[-2], self.quadruples[-1]]}

    # Rule 5.3: loop <block> (and loop expression)
    def process_loop_begin(self, is_expression, line_num):
        loop_start_label = self._new_label()
        loop_end_label = self._new_label() # break jumps here
        self.add_quad("LABEL", result=loop_start_label)

        loop_ctx = {'type': 'loop', 'start_label': loop_start_label, 'end_label': loop_end_label}
        if is_expression:
            loop_ctx['is_expr_loop'] = True
            loop_ctx['expr_type'] = "unknown_inferred" # To be inferred from 'break <expr>'
            loop_ctx['result_place'] = self._new_temp() # To store the loop expression's result
        self.loop_stack.append(loop_ctx)
        return {'quads': [self.quadruples[-1]], 'loop_ctx': loop_ctx}


    def process_loop_end(self, loop_data, line_num):
        loop_ctx = loop_data['loop_ctx']
        if not loop_ctx.get('is_expr_loop'): # Infinite loop unless break
            self.add_quad("JUMP", result=loop_ctx['start_label'])

        self.add_quad("LABEL", result=loop_ctx['end_label'])

        if self.loop_stack and self.loop_stack[-1]['type'] == 'loop':
            self.loop_stack.pop()
        else:
            raise SemanticError("Mismatched loop structure (loop).", line_num)

        result_attrs = {'quads': [self.quadruples[-1]]}
        if loop_ctx.get('is_expr_loop'):
            if loop_ctx['expr_type'] == "unknown_inferred": # No break <expr> found
                 # This might be an error or a diverging loop (type '!')
                 # For simplicity, let's call it an error if no break <val> determines the type.
                 # Or, if it's allowed to be a diverging loop, its type could be special.
                 # PDF: "the types of their expressions must all be identical. This common type becomes the return type of the loop expression."
                 # This implies at least one break <expr> is expected if it's used as an expression.
                 raise SemanticError("Loop expression lacks a 'break <value>;' to determine its type.", line_num)
            result_attrs['type'] = loop_ctx['expr_type']
            result_attrs['place'] = loop_ctx['result_place'] # This place should be assigned by 'break val' quads
            if loop_ctx.get('break_assign_quads'): # These would be ASSIGN from break <val> to result_place
                result_attrs['quads'].extend(loop_ctx['break_assign_quads'])

        return result_attrs


    # Rule 5.4: break; continue; (and break <expr>; for loop expressions)
    def process_break_continue(self, keyword_token, expr_attrs, line_num):
        # expr_attrs is None for 'break;' or 'continue;'
        # expr_attrs is present for 'break <expr>;'
        keyword = keyword_token['content']
        quads = []

        if not self.loop_stack:
            raise SemanticError(f"'{keyword}' statement outside of a loop.", line_num)

        loop_ctx = self.loop_stack[-1]

        if keyword == "continue":
            if expr_attrs:
                raise SemanticError("'continue' cannot have an expression.", line_num)
            self.add_quad("JUMP", result=loop_ctx['start_label'])
            quads.append(self.quadruples.pop())
        elif keyword == "break":
            if loop_ctx.get('is_expr_loop'):
                if not expr_attrs:
                    raise SemanticError("Loop expression 'break' must provide a value.", line_num)
                quads.extend(expr_attrs.get('code', []))

                # Infer/check loop expression type
                if loop_ctx['expr_type'] == "unknown_inferred":
                    loop_ctx['expr_type'] = expr_attrs['type']
                else:
                    self.check_type_compatibility(loop_ctx['expr_type'], expr_attrs['type'], line_num)

                # Assign break value to the loop's result temp
                self.add_quad("ASSIGN", expr_attrs['place'], result=loop_ctx['result_place'])
                quads.append(self.quadruples.pop())
                # if 'break_assign_quads' not in loop_ctx: loop_ctx['break_assign_quads'] = []
                # loop_ctx['break_assign_quads'].append(self.quadruples[-1])


            elif expr_attrs: # break <expr> in a non-expression loop
                raise SemanticError("'break <expression>;' is only allowed in 'loop' expressions.", line_num)

            self.add_quad("JUMP", result=loop_ctx['end_label'])
            quads.append(self.quadruples.pop())

        return {'code': quads}


    # Rule 6.2: References and Dereferences
    # <因子> -> '*' <因子> | '&' mut <因子> | '&' <因子>
    def process_reference_op(self, op_type, target_attrs, line_num):
        # op_type: '*', '&', '&mut'
        # target_attrs: attributes of the factor being operated on
        quads = []
        quads.extend(target_attrs.get('code', []))
        target_type = target_attrs['type']
        target_place = target_attrs['place']
        result_place = self._new_temp()

        if op_type == '*': # Dereference
            if not (isinstance(target_type, list) and target_type[0] in ['&', '&mut']):
                raise SemanticError(f"Cannot dereference non-reference type '{self.get_type_name(target_type)}'.", line_num)
            
            # Borrow checking: Dereferencing a shared ref is fine. Dereferencing a mut ref requires exclusive access.
            # This simplistic check doesn't fully model Rust's borrow checker.
            # If it's a named variable, check its borrow state.
            if 'name' in target_attrs:
                target_entry = self.lookup_symbol(target_attrs['name'], line_num)
                # Actual borrow checking logic is more complex, involving lifetimes etc.
                # For now, assume valid if type is correct.

            result_type = target_type[1] # The inner type
            self.add_quad("DEREF", target_place, result=result_place)
            # The result_place now holds the value. If used as LValue, it needs to be an address.
            # This means DEREF might produce an address or a value based on context.
            # For simplicity: DEREF here gives value. If *p = ..., then DEREF gives address.
            # Let's refine: DEREF gives address. LOAD_FROM_ADDR gets value.
            # So, if *p is used as RValue, it's (DEREF p, t1), (LOAD_FROM_ADDR t1, t2)
            # If *p is LValue, (DEREF p, t1) and t1 is the address.
            quads.append(self.quadruples.pop())
            return {'type': result_type, 'place': result_place, 'code': quads,
                    'is_lvalue': True, 'is_mutable': (target_type[0] == '&mut'),
                    'is_lvalue_address': True, 'is_temp_lvalue': True } # Temp lvalue from deref

        elif op_type == '&' or op_type == '&mut':
            # Target must be an LValue
            if not target_attrs.get('is_lvalue'):
                raise SemanticError(f"Cannot take reference of non-lvalue.", line_num)

            # For &mut, target must be mutable
            target_name = target_attrs.get('name')
            target_is_actually_mutable = target_attrs.get('is_mutable', False)

            if 'is_temp_lvalue' in target_attrs and target_attrs['is_temp_lvalue']: # e.g. &(*foo) or &arr[i]
                pass # Mutability comes from target_attrs['is_mutable']
            elif target_name:
                target_entry = self.lookup_symbol(target_name, line_num)
                target_is_actually_mutable = target_entry.is_mutable
                # Borrow checking (simplified):
                if op_type == '&mut':
                    if target_entry.active_borrows['immutable'] > 0 or target_entry.active_borrows['mutable'] > 0:
                        raise SemanticError(f"Cannot take mutable reference to '{target_name}' as it's already borrowed.", line_num)
                    target_entry.active_borrows['mutable'] += 1
                else: # op_type == '&'
                    if target_entry.active_borrows['mutable'] > 0:
                        raise SemanticError(f"Cannot take immutable reference to '{target_name}' as it's already mutably borrowed.", line_num)
                    target_entry.active_borrows['immutable'] += 1
            else: # Referencing something without a direct symbol table entry (e.g. complex expr result)
                if op_type == '&mut' and not target_is_actually_mutable:
                     raise SemanticError(f"Cannot take mutable reference to an immutable temporary value.", line_num)


            if op_type == '&mut' and not target_is_actually_mutable:
                raise SemanticError(f"Cannot take mutable reference of immutable '{target_attrs.get('name', 'value')}'.", line_num)

            result_type = [op_type, target_type] # e.g. ['&mut', 'i32']
            self.add_quad("REF", target_place, result=result_place)
            quads.append(self.quadruples.pop())
            # TODO: decrement borrow counts when references go out of scope (complex)

            return {'type': result_type, 'place': result_place, 'code': quads}

        raise SemanticError(f"Unknown reference operation '{op_type}'.", line_num)


    # Rule 7.1, 7.2, 7.3: Expression Blocks
    def process_expression_block_begin(self, line_num):
        self.enter_scope()
        # For if/loop expressions, the block's "result" (type and place) is important.

    def process_expression_block_end(self, stmts_attrs_list, final_expr_attrs, line_num):
        # stmts_attrs_list: list of codes from statements
        # final_expr_attrs: {'type': type, 'place': temp, 'code': []} or None if block ends with ';'
        quads = []
        for stmt_attrs in stmts_attrs_list:
            if stmt_attrs and 'code' in stmt_attrs:
                quads.extend(stmt_attrs['code'])

        self.exit_scope()
        block_result_type = 'void'
        block_result_place = None

        if final_expr_attrs: # Block ends with an expression
            quads.extend(final_expr_attrs.get('code', []))
            block_result_type = final_expr_attrs['type']
            block_result_place = final_expr_attrs['place']
        # If block ends with a statement (e.g. let x=1;}), type is void.

        return {'type': block_result_type, 'place': block_result_place, 'code': quads}


    # Rule 8.1: Array literal ['elem1', 'elem2', ...]
    # Rule 8.1: Array type declaration [type; size] (handled in process_type)
    def process_array_literal(self, elements_attrs_list, declared_type_attrs, line_num):
        # elements_attrs_list: list of {'type': type, 'place': place, 'code': []}
        # declared_type_attrs: (optional) from a 'let a: [i32; 3] = ...;' context.
        #                    {'type': ['[', 'i32', 3], ...}
        quads = []
        element_places = []
        literal_element_type = None

        if not elements_attrs_list: # Empty array literal []
            # Type must be known from context if it's empty
            if not declared_type_attrs:
                raise SemanticError("Cannot infer type of empty array literal without context.", line_num)
            array_type_info = declared_type_attrs['type'] # ['[', el_type, size]
            if array_type_info[2] != 0:
                raise SemanticError(f"Empty array literal used for non-empty array type {self.get_type_name(array_type_info)}.", line_num)
            literal_element_type = array_type_info[1]
            num_elements = 0
        else:
            num_elements = len(elements_attrs_list)
            first_element_type = elements_attrs_list[0]['type']
            for i, elem_attrs in enumerate(elements_attrs_list):
                quads.extend(elem_attrs.get('code', []))
                self.check_type_compatibility(first_element_type, elem_attrs['type'], line_num,
                                            f"Array elements must have the same type. Expected {self.get_type_name(first_element_type)}, found {self.get_type_name(elem_attrs['type'])} at index {i}.")
                element_places.append(elem_attrs['place'])
            literal_element_type = first_element_type


        final_array_type = ['[', literal_element_type, num_elements]

        if declared_type_attrs:
            self.check_type_compatibility(declared_type_attrs['type'], final_array_type, line_num)
            # Use the declared type as the definitive one if compatible
            final_array_type = declared_type_attrs['type']


        array_place = self._new_temp()
        # Quad for array creation. Arguments might be size and then elements, or a special op.
        # For now: (ARRAY_INIT, result_array_place, size, type_info_or_nullptr)
        # Then sequence of (ARRAY_SET_ELEMENT, array_place, index, element_place)
        self.add_quad("ARRAY_INIT", array_place, num_elements, self.get_type_name(final_array_type[1]))
        quads.append(self.quadruples.pop())
        for i, el_place in enumerate(element_places):
            self.add_quad("ARRAY_SET", array_place, i, el_place)
            quads.append(self.quadruples.pop())


        return {'type': final_array_type, 'place': array_place, 'code': quads}


    # Rule 9.1: Tuple literal (elem1, elem2, ...)
    # Rule 9.1: Tuple type declaration (type1, type2, ...) (handled in process_type)
    def process_tuple_literal(self, elements_attrs_list, declared_type_attrs, line_num):
        # elements_attrs_list: list of {'type': type, 'place': place, 'code': []}
        # declared_type_attrs: (optional) from 'let a: (i32, bool) = ...;' context.
        #                    {'type': ('i32', 'bool'), ...}
        quads = []
        element_places = []
        element_types = []

        if not elements_attrs_list: # Empty tuple literal ()
            final_tuple_type = tuple()
        else:
            for elem_attrs in elements_attrs_list:
                quads.extend(elem_attrs.get('code', []))
                element_places.append(elem_attrs['place'])
                element_types.append(elem_attrs['type'])
            final_tuple_type = tuple(element_types)

        if declared_type_attrs:
            self.check_type_compatibility(declared_type_attrs['type'], final_tuple_type, line_num)
            final_tuple_type = declared_type_attrs['type'] # Use declared type if compatible

        tuple_place = self._new_temp()
        # Similar to array, (TUPLE_INIT, result_tuple_place, num_elements)
        # Then (TUPLE_SET_ELEMENT, tuple_place, index, element_place)
        self.add_quad("TUPLE_INIT", tuple_place, len(final_tuple_type))
        quads.append(self.quadruples.pop())
        for i, el_place in enumerate(element_places):
            self.add_quad("TUPLE_SET", tuple_place, i, el_place)
            quads.append(self.quadruples.pop())

        return {'type': final_tuple_type, 'place': tuple_place, 'code': quads}


    def get_quadruples(self):
        return self.quadruples

    def print_quadruples(self):
        print("\n--- Quadruples ---")
        for i, q in enumerate(self.quadruples):
            print(f"{i:03d}: {q}")
        print("------------------")

    def print_symbol_table(self): # For debugging
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
                print(f"  {name}: type={self.get_type_name(entry.data_type)}, kind={entry.sym_type.name}, scope={entry.scope_level}, {mut}, {init}{extra}")
            level +=1
        print("--------------------")

    def dispatch_semantic_action(self, production_rule_str, children_attrs, line_num_approx):
        """
        根据产生式字符串，调度到相应的语义处理函数。

        参数:
            production_rule_str (str): 当前规约的产生式字符串 (如 "Program -> DeclarationList")。
            children_attrs (list): 产生式右部各符号的语义属性字典列表。
                                   每个字典结构: {'type':..., 'place':..., 'code':[], 'token_obj':... (如果是终结符)}
            line_num_approx (int): 用于错误报告的近似行号。
        
        返回:
            dict: 为产生式左部符号计算得到的语义属性。
        """

        # --- 辅助函数，方便从 children_attrs 中获取信息 ---
        def get_child_attrs(idx):
            # 获取指定索引的子节点的属性字典
            if idx < len(children_attrs) and children_attrs[idx] is not None:
                return children_attrs[idx]
            # 如果子节点是epsilon或者由于某些原因没有属性，返回一个默认空属性字典
            return {'code': [], 'token_obj': None, 'place': None, 'type': 'unknown_epsilon'}

        def get_token_obj_from_child(child_idx):
            # 获取指定子节点的 token_obj (通常是终结符的原始token信息)
            child = get_child_attrs(child_idx)
            return child.get('token_obj')

        # --- 产生式规则的条件判断和分发 ---
        # ❗ 你需要根据 production.txt 中的每一个产生式，在这里添加对应的 if/elif 条件
        # 字符串必须完全匹配！

        # --- Program (来自 production.txt) ---
        if production_rule_str == "Program -> DeclarationList":
            # Program 的属性通常是 DeclarationList 的属性 (主要是生成的代码)
            decl_list_attrs = get_child_attrs(0)
            # 可以在这里进行一些全局的初始化或收尾工作，如果需要的话
            # self.add_quad("PROGRAM_START") # 例如
            # final_code = decl_list_attrs.get('code', [])
            # self.add_quad("PROGRAM_END")
            # final_code.append(self.quadruples[-1]) # 假设 add_quad 返回quad对象
            return {'code': decl_list_attrs.get('code', [])}

        # --- VariableDeclarationInner (来自 production.txt) ---
        elif production_rule_str == "VariableDeclarationInner -> MUT IDENTIFIER":
            mut_token = get_token_obj_from_child(0)     # MUT
            identifier_token = get_token_obj_from_child(1) # IDENTIFIER
            return self.process_variable_decl_internal(identifier_token, mut_token, line_num_approx)

        elif production_rule_str == "VariableDeclarationInner -> IDENTIFIER":
            identifier_token = get_token_obj_from_child(0) # IDENTIFIER
            return self.process_variable_decl_internal(identifier_token, None, line_num_approx)

        # --- Assignable (来自 production.txt) ---
        elif production_rule_str == "Assignable -> IDENTIFIER":
            identifier_token = get_token_obj_from_child(0)
            # process_assignable_element 需要一个结构化的输入，或直接处理 token
            return self.process_assignable_element({'type': 'id', 'token': identifier_token}, line_num_approx)

        # --- Type (来自 production.txt) ---
        elif production_rule_str == "Type -> I32":
            # I32 是终结符, 其 token_obj 已经由 ACTION_S 放入 attrs
            # 返回类型属性
            return {'type': 'i32', 'code': [], 'token_obj': get_token_obj_from_child(0)}

        # --- Factor / Expressions (示例) ---
        elif production_rule_str == "Factor -> Primary": # 这是一个典型的链式规则
            return get_child_attrs(0) # 直接传递 Primary 的属性

        elif production_rule_str == "Primary -> INTEGER_CONSTANT":
            num_token = get_token_obj_from_child(0)
            # process_element 通常处理作为右值的 Primary 元素
            return self.process_element(num_token, line_num_approx)

        elif production_rule_str == "Primary -> Assignable":
            # Assignable (如 IDENTIFIER) 作为右值
            assignable_attrs = get_child_attrs(0)
            return self.process_element(assignable_attrs, line_num_approx)
            
        elif production_rule_str == "AdditionExpression -> AdditionExpression AddOp Term":
            left_expr_attrs = get_child_attrs(0)
            add_op_attrs = get_child_attrs(1) # AddOp 可能是一个非终结符，其属性包含 op_token
            op_token = add_op_attrs.get('token_obj') # 或者如果 AddOp -> PLUS, op_token 在 children_attrs[1]['token_obj']
            right_term_attrs = get_child_attrs(2)
            
            # 如果 AddOp 是一个非终结符，确保它的属性包含实际的操作符 token
            # 例如，如果 AddOp -> PLUS, 那么 add_op_attrs 应该是 {'token_obj': <PLUS_token>}
            # 如果 AddOp 直接就是 PLUS (即产生式是 AdditionExpression -> AdditionExpression PLUS Term),
            # 那么 op_token = get_token_obj_from_child(1)
            # 你需要根据你的 AddOp 如何定义来调整这里 op_token 的获取方式
            
            # 假设 AddOp -> PLUS (或 MINUS) 是一个单独的规约，
            # 并且其属性是 {'op_symbol': '+', 'token_obj': <token for '+'>}
            # 那么 op_token = add_op_attrs.get('token_obj')
            # 如果 AddOp -> PLUS 中PLUS是终结符，它的token_obj已经在children_attrs[1]的attrs中
            actual_op_token = op_token # 假设op_token已经正确获取
            if not actual_op_token and 'op_symbol' in add_op_attrs: # 兼容 AddOp -> PLUS 这类规则
                 actual_op_token = add_op_attrs.get('token_obj')


            if not actual_op_token:
                # 这是一个重要的检查点。如果你的 AddOp 是一个非终结符，
                # 你需要确保它的语义动作能把操作符token (`token_obj`) 传递上来。
                # 或者，你的产生式可能是 AdditionExpression -> AdditionExpression PLUS Term，
                # 这种情况下，PLUS (child 1) 的 token_obj 就是操作符。
                # 此处假设 op_token 能被正确取到。
                # 对于 "AddOp -> PLUS", get_token_obj_from_child(0) (在处理 AddOp 规则时)
                # 应该返回 PLUS 的 token_obj
                pass # 确保 op_token 能正确获取


            return self.process_binary_op(actual_op_token, left_expr_attrs, right_term_attrs, line_num_approx)

        # 对于 AddOp -> PLUS, AddOp -> MINUS 等规则:
        elif production_rule_str == "AddOp -> PLUS":
            plus_token = get_token_obj_from_child(0)
            return {'op_symbol': '+', 'token_obj': plus_token, 'code': []}
        elif production_rule_str == "AddOp -> MINUS":
            minus_token = get_token_obj_from_child(0)
            return {'op_symbol': '-', 'token_obj': minus_token, 'code': []}
        # MulOp 类似处理...
        elif production_rule_str == "MulOp -> MULT":
            mult_token = get_token_obj_from_child(0)
            return {'op_symbol': '*', 'token_obj': mult_token, 'code': []}
        elif production_rule_str == "MulOp -> DIV":
            div_token = get_token_obj_from_child(0)
            return {'op_symbol': '/', 'token_obj': div_token, 'code': []}


        # --- Statements ---
        elif production_rule_str == "Statement -> LET VariableDeclarationInner COLON Type SEMICOLON":
            # child 0: LET (token)
            # child 1: VariableDeclarationInner (attrs)
            # child 2: COLON (token)
            # child 3: Type (attrs)
            # child 4: SEMICOLON (token)
            var_decl_inner_attrs = get_child_attrs(1)
            type_attrs = get_child_attrs(3)
            return self.process_variable_declaration(var_decl_inner_attrs, type_attrs, line_num_approx)

        elif production_rule_str == "Statement -> LET VariableDeclarationInner SEMICOLON":
            var_decl_inner_attrs = get_child_attrs(1)
            return self.process_variable_declaration(var_decl_inner_attrs, None, line_num_approx) # Type is None (for inference)

        elif production_rule_str == "AssignmentStatement -> Assignable ASSIGN Expression SEMICOLON":
            # child 0: Assignable (attrs)
            # child 1: ASSIGN (token)
            # child 2: Expression (attrs)
            # child 3: SEMICOLON (token)
            assignable_attrs = get_child_attrs(0)
            expr_attrs = get_child_attrs(2)
            return self.process_assignment(assignable_attrs, expr_attrs, line_num_approx)
        
        # 根据你的 production.txt，AssignmentStatement 也可能是 VariableDeclarationInner ASSIGN Expression SEMICOLON
        # 这其实更像是声明并赋值，但如果 VariableDeclarationInner 被当作 Assignable 的一种（例如通过链式规则）
        # 或者这里 VariableDeclarationInner 的属性需要转换成 Assignable 的属性。
        # 假设 VariableDeclarationInner (通过 IDENTIFIER) 返回的属性与 Assignable -> IDENTIFIER 兼容。
        elif production_rule_str == "AssignmentStatement -> VariableDeclarationInner ASSIGN Expression SEMICOLON":
            # 如果 VariableDeclarationInner 的属性可以直接用作 process_assignment 的第一个参数
            # (即它包含了 name, type, is_lvalue, is_mutable, place 等)，那么：
            var_decl_inner_as_assignable_attrs = get_child_attrs(0)
            expr_attrs = get_child_attrs(2)
            # 你可能需要一个转换函数或确保 process_variable_decl_internal 返回的属性与 process_assignment 兼容
            # 这是一个潜在的复杂点，取决于这两个 process_ 函数的返回值/期望值。
            # 假设 process_variable_decl_internal 返回的 name, is_mutable 足够，
            # 并且 process_assignment 内部会通过 name 查找符号表获取 type 等信息。
            # 为了安全，我们应该确保 var_decl_inner_as_assignable_attrs 包含 'name' 和 'is_mutable'
            # 并且 process_assignment 的第一个参数能处理这种情况，或者有一个适配层。
            #
            # 一个更清晰的方式可能是，VariableDeclarationInner 本身不直接作为 Assignable。
            # 如果它确实可以，那么它的属性结构需要符合 Assignable 的期望。
            # 对于 'mut x = y;', 'mut x' 是 VariableDeclarationInner, 不是 Assignable。
            # Assignable 主要是 'x = y;' 中的 'x'。
            # 因此，这个产生式 AssignmentStatement -> VariableDeclarationInner ASSIGN Expression SEMICOLON
            # 语义上更像是一个带有初始化的可变变量声明，但没有 'let'。这在 Rust 中不常见。
            # 如果这是语言设计的一部分，你需要一个特定的 process_ 函数。
            #
            # 鉴于 production.txt 中有专门的 VariableDeclarationAssignmentStatement,
            # 这个 AssignmentStatement 规则可能用于已经声明的变量。
            # 如果 VariableDeclarationInner 总是通过 IDENTIFIER 归约而来，
            # 并且 process_variable_decl_internal 只返回 {'name': ..., 'is_mutable': ...},
            # 那么 process_assignment 需要通过这个名字去符号表中查找完整的符号信息。
            #
            # 假设：process_assignment 会用 var_decl_inner_as_assignable_attrs['name'] 去符号表查找。
            assignable_simulated_attrs = {
                'name': var_decl_inner_as_assignable_attrs.get('name'),
                'is_lvalue': True, # Implied by context
                'is_mutable': var_decl_inner_as_assignable_attrs.get('is_mutable'), # From VariableDeclarationInner
                # 'type' and 'place' will be looked up or determined by process_assignment
                'code': var_decl_inner_as_assignable_attrs.get('code', []),
                'token_obj': var_decl_inner_as_assignable_attrs.get('token_obj')
            }
            return self.process_assignment(assignable_simulated_attrs, expr_attrs, line_num_approx)


        elif production_rule_str == "VariableDeclarationAssignmentStatement -> LET VariableDeclarationInner ASSIGN Expression SEMICOLON":
            var_decl_inner_attrs = get_child_attrs(1)
            expr_attrs = get_child_attrs(3)
            return self.process_variable_declaration_assignment(var_decl_inner_attrs, None, expr_attrs, line_num_approx)

        elif production_rule_str == "VariableDeclarationAssignmentStatement -> LET VariableDeclarationInner COLON Type ASSIGN Expression SEMICOLON":
            var_decl_inner_attrs = get_child_attrs(1)
            type_attrs = get_child_attrs(3)
            expr_attrs = get_child_attrs(5)
            return self.process_variable_declaration_assignment(var_decl_inner_attrs, type_attrs, expr_attrs, line_num_approx)


        # --- Function Calls (需要根据你的 ArgumentList 等规则具体化) ---
        elif production_rule_str == "Primary -> IDENTIFIER LPAREN ArgumentList RPAREN":
            identifier_token = get_token_obj_from_child(0)
            # ArgumentList 规约后，其 attrs 应该包含一个 args 列表和生成的 code
            arg_list_container_attrs = get_child_attrs(2) # ArgumentList 的属性
            actual_args_attrs_list = arg_list_container_attrs.get('args', []) if arg_list_container_attrs else []
            # 合并 ArgumentList 自身生成的代码
            call_code = arg_list_container_attrs.get('code', []) if arg_list_container_attrs else []
            
            result_attrs = self.process_function_call(identifier_token, actual_args_attrs_list, line_num_approx)
            # 将参数列表生成的代码和函数调用本身生成的代码合并
            result_attrs['code'] = call_code + result_attrs.get('code', [])
            return result_attrs

        # ArgumentList 的规约规则
        elif production_rule_str == "ArgumentList -> epsilon":
            return {'args': [], 'code': []} # 没有参数，没有代码
        elif production_rule_str == "ArgumentList -> Expression":
            expr_attrs = get_child_attrs(0)
            # 返回一个包含单个参数属性和其代码的列表
            return {'args': [expr_attrs], 'code': expr_attrs.get('code', [])}
        elif production_rule_str == "ArgumentList -> Expression COMMA ArgumentList":
            # 这是右递归的列表， Expression 是头，ArgumentList 是尾
            expr_attrs = get_child_attrs(0) # 当前的 Expression
            arg_list_tail_attrs = get_child_attrs(2) # 剩余的 ArgumentList
            
            all_args = [expr_attrs] + (arg_list_tail_attrs.get('args', []) if arg_list_tail_attrs else [])
            
            # 合并代码：当前 Expression 的代码 + 尾部 ArgumentList 的代码
            combined_code = expr_attrs.get('code', [])
            if arg_list_tail_attrs:
                combined_code.extend(arg_list_tail_attrs.get('code', []))
            return {'args': all_args, 'code': combined_code}


        # --- 空语句 ---
        elif production_rule_str == "Statement -> SEMICOLON":
            return {'code': []} # 空语句不产生代码

        # --- 链式规则的默认处理 (如果上面没有显式处理) ---
        # 例如: Expression -> AdditionExpression
        #      Term -> Factor
        #      ...等等
        # 注意：这个默认处理比较通用，如果某个链式规则有特殊需求，应在上面显式处理。
        # 一个简单的判断：如果产生式右部只有一个非终结符。
        parts = production_rule_str.split("->")
        if len(parts) == 2:
            rhs_symbols = parts[1].strip().split(" ")
            if len(rhs_symbols) == 1 and rhs_symbols[0].isupper(): # 假设非终结符大写开头
                # print(f"Info: Applying default chain rule pass-through for '{production_rule_str}'")
                return get_child_attrs(0) # 直接返回唯一子节点的属性

        # --- 如果没有任何规则匹配 ---
        else:
            # print(f"警告: dispatch_semantic_action 中没有找到产生式 '{production_rule_str}' 的特定处理。")
            # 返回一个默认的空属性，或者抛出错误，取决于你的设计
            # 对于很多纯粹的语法结构规则 (比如 StatementList -> Statement StatementList 的容器规则)
            # 可能只需要合并子节点的 'code' 属性。
            # 这个默认返回需要非常小心。
            # 一个更安全的默认可能是：
            # collected_code = []
            # for child_attr in children_attrs:
            #     if child_attr and 'code' in child_attr:
            #         collected_code.extend(child_attr['code'])
            # return {'code': collected_code}
            # 但这对于期望特定返回结构 (如 type, place) 的规则是不够的。
            # 最好的做法是为 *所有* 会产生语义值的产生式编写显式的处理分支。
            return {'code': []} # 或者根据需要更复杂的默认聚合逻辑

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
                output.append(f"  {name}: type={self.get_type_name(entry.data_type)}, kind={entry.sym_type.name}, scope={entry.scope_level}, {mut}, {init}{extra}")
            level +=1
        output.append("--------------------")
        return "\n".join(output)

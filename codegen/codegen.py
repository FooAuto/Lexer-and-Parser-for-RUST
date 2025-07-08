from semantic.semantic import SymbolType


class CodeGenerator:
    def __init__(self):
        self.mips_code = []
        self.var_map = {}
        self.current_func_stack_offset = 0
        self.param_count = 0
        self.temp_regs = [f"$t{i}" for i in range(10)]
        self.free_regs = self.temp_regs[:]
        self.global_symbols = {}
        self.current_symbol_map = {}

    def _get_reg(self):
        if not self.free_regs:
            raise Exception("Register spill not implemented: temporary registers exhausted.")
        return self.free_regs.pop(0)

    def _release_reg(self, reg):
        if reg in self.temp_regs and reg not in self.free_regs:
            self.free_regs.insert(0, reg)
            self.free_regs.sort(key=lambda r: int(r[2:]))

    def _get_var_stack_offset(self, var_name):
        if var_name not in self.var_map:
            var_entry = self.current_symbol_map.get(var_name)
            size = 4
            if var_entry and isinstance(var_entry.data_type, list) and var_entry.data_type[0] == "[":
                array_len = var_entry.data_type[2]
                size = array_len * 4

            self.current_func_stack_offset -= size
            self.var_map[var_name] = self.current_func_stack_offset
        return self.var_map[var_name]

    def _load_value_to_reg(self, operand, reg):
        if isinstance(operand, int):
            self.mips_code.append(f"    li {reg}, {operand}")
        else:
            offset = self._get_var_stack_offset(operand)
            self.mips_code.append(f"    lw {reg}, {offset}($fp)")

    def _load_address_to_reg(self, var_name, reg):
        entry = self.current_symbol_map.get(var_name)
        offset = self._get_var_stack_offset(var_name)

        is_array_param = (
            entry
            and entry.sym_type == SymbolType.PARAMETER
            and isinstance(entry.data_type, list)
            and entry.data_type[0] == "["
        )

        if is_array_param:
            self.mips_code.append(f"    lw {reg}, {offset}($fp)")
        else:
            self.mips_code.append(f"    addiu {reg}, $fp, {offset}")

    def _calculate_stack_space(self, func_quads):
        size = 0
        local_vars = set()
        for quad in func_quads:
            for item in [quad.arg1, quad.arg2, quad.result]:
                if isinstance(item, str) and not item.startswith("L"):
                    entry = self.current_symbol_map.get(item)
                    if not entry or entry.sym_type not in [SymbolType.FUNCTION]:
                        local_vars.add(item)

        processed_vars = set()
        for var_name in local_vars:
            if var_name in processed_vars:
                continue

            entry = self.current_symbol_map.get(var_name)
            if entry and entry.sym_type != SymbolType.PARAMETER:
                if isinstance(entry.data_type, list) and entry.data_type[0] == "[":
                    size += entry.data_type[2] * 4
                else:
                    size += 4
                processed_vars.add(var_name)
            elif not entry:  # Temporaries
                size += 4
                processed_vars.add(var_name)

        return (size + 15) & -16

    def _translate_quads(self, quads, func_entry):
        for quad in quads:
            op, arg1, arg2, result = quad.op, quad.arg1, quad.arg2, quad.result

            if op == "FUNC_BEGIN":
                self.mips_code.append(f"\n{arg1}:")
                self.mips_code.append("    addiu $sp, $sp, -8")
                self.mips_code.append("    sw $ra, 4($sp)")
                self.mips_code.append("    sw $fp, 0($sp)")
                self.mips_code.append("    move $fp, $sp")

                stack_space = self._calculate_stack_space(quads)
                self.mips_code.append(f"    addiu $sp, $sp, -{stack_space}")
                self.current_func_stack_offset = 0
                self.var_map.clear()

                if func_entry and func_entry.sym_type == SymbolType.FUNCTION:
                    for i, param in enumerate(func_entry.extra_info.get("params", [])):
                        if i < 4:
                            param_offset = self._get_var_stack_offset(param["name"])
                            self.mips_code.append(f"    sw $a{i}, {param_offset}($fp)")

            elif op == "ARRAY_LOAD":
                reg_base_addr = self._get_reg()
                reg_index = self._get_reg()
                dest_reg = self._get_reg()

                self._load_address_to_reg(arg1, reg_base_addr)
                self._load_value_to_reg(arg2, reg_index)

                self.mips_code.append(f"    sll {reg_index}, {reg_index}, 2")
                self.mips_code.append(f"    addu {reg_base_addr}, {reg_base_addr}, {reg_index}")
                self.mips_code.append(f"    lw {dest_reg}, 0({reg_base_addr})")

                dest_addr_on_stack = self._get_var_stack_offset(result)
                self.mips_code.append(f"    sw {dest_reg}, {dest_addr_on_stack}($fp)")

                self._release_reg(reg_base_addr)
                self._release_reg(reg_index)
                self._release_reg(dest_reg)

            elif op == "ARRAY_STORE":
                reg_base_addr = self._get_reg()
                reg_index = self._get_reg()
                reg_value = self._get_reg()

                self._load_address_to_reg(arg1, reg_base_addr)
                self._load_value_to_reg(arg2, reg_index)
                self._load_value_to_reg(result, reg_value)

                self.mips_code.append(f"    sll {reg_index}, {reg_index}, 2")
                self.mips_code.append(f"    addu {reg_base_addr}, {reg_base_addr}, {reg_index}")
                self.mips_code.append(f"    sw {reg_value}, 0({reg_base_addr})")

                self._release_reg(reg_base_addr)
                self._release_reg(reg_index)
                self._release_reg(reg_value)

            elif op == "PARAM":
                arg_entry = self.current_symbol_map.get(arg1)
                is_array = arg_entry and isinstance(arg_entry.data_type, list) and arg_entry.data_type[0] == "["

                if self.param_count < 4:
                    arg_reg = f"$a{self.param_count}"
                    if is_array:
                        self._load_address_to_reg(arg1, arg_reg)
                    else:
                        self._load_value_to_reg(arg1, arg_reg)
                else:
                    raise NotImplementedError("Stack-based parameter passing beyond 4 arguments not implemented.")
                self.param_count += 1

            elif op == "ARRAY_INIT":
                array_name = arg1
                num_elements = arg2
                if array_name not in self.var_map:
                    size = num_elements * 4
                    self.current_func_stack_offset -= size
                    self.var_map[array_name] = self.current_func_stack_offset

            elif op == "ARRAY_SET":
                array_name = arg1
                index_val = arg2
                value_to_store = result
                array_base_addr_offset = self._get_var_stack_offset(array_name)
                element_offset_in_bytes = index_val * 4
                final_offset_on_stack = array_base_addr_offset + element_offset_in_bytes
                reg_val = self._get_reg()
                self._load_value_to_reg(value_to_store, reg_val)
                self.mips_code.append(f"    sw {reg_val}, {final_offset_on_stack}($fp)")
                self._release_reg(reg_val)

            elif op == "ASSIGN":
                dest_entry = self.current_symbol_map.get(result)
                is_array_assign = (
                    dest_entry and isinstance(dest_entry.data_type, list) and dest_entry.data_type[0] == "["
                )
                if is_array_assign:
                    array_len = dest_entry.data_type[2]
                    reg_src, reg_dest, reg_tmp = self._get_reg(), self._get_reg(), self._get_reg()
                    self._load_address_to_reg(arg1, reg_src)
                    self._load_address_to_reg(result, reg_dest)
                    for i in range(array_len):
                        offset = i * 4
                        self.mips_code.append(f"    lw {reg_tmp}, {offset}({reg_src})")
                        self.mips_code.append(f"    sw {reg_tmp}, {offset}({reg_dest})")
                    self._release_reg(reg_src)
                    self._release_reg(reg_dest)
                    self._release_reg(reg_tmp)
                else:
                    reg1 = self._get_reg()
                    self._load_value_to_reg(arg1, reg1)
                    result_addr_offset = self._get_var_stack_offset(result)
                    self.mips_code.append(f"    sw {reg1}, {result_addr_offset}($fp)")
                    self._release_reg(reg1)

            elif op in ("ADD", "SUB", "MUL", "DIV"):
                reg1, reg2, result_reg = self._get_reg(), self._get_reg(), self._get_reg()
                self._load_value_to_reg(arg1, reg1)
                self._load_value_to_reg(arg2, reg2)
                op_map = {"ADD": "addu", "SUB": "subu", "MUL": "mul", "DIV": "div"}
                self.mips_code.append(f"    {op_map[op]} {result_reg}, {reg1}, {reg2}")
                if op == "DIV":
                    self.mips_code.append(f"    mflo {result_reg}")
                result_addr_offset = self._get_var_stack_offset(result)
                self.mips_code.append(f"    sw {result_reg}, {result_addr_offset}($fp)")
                self._release_reg(reg1)
                self._release_reg(reg2)
                self._release_reg(result_reg)

            elif op in ("GT", "GE", "LT", "LE", "EQ", "NE"):
                reg1, reg2, result_reg = self._get_reg(), self._get_reg(), self._get_reg()
                self._load_value_to_reg(arg1, reg1)
                self._load_value_to_reg(arg2, reg2)

                op_map = {
                    "GT": "sgt",  # set on greater than
                    "GE": "sge",  # set on greater than or equal
                    "LT": "slt",  # set on less than
                    "LE": "sle",  # set on less than or equal
                    "EQ": "seq",  # set on equal
                    "NE": "sne",  # set on not equal
                }
                self.mips_code.append(f"    {op_map[op]} {result_reg}, {reg1}, {reg2}")

                result_addr_offset = self._get_var_stack_offset(result)
                self.mips_code.append(f"    sw {result_reg}, {result_addr_offset}($fp)")

                self._release_reg(reg1)
                self._release_reg(reg2)
                self._release_reg(result_reg)

            elif op == "LABEL":
                self.mips_code.append(f"{result}:")

            elif op == "JUMP":
                self.mips_code.append(f"    j {result}")

            elif op == "IF_FALSE":
                reg1 = self._get_reg()
                self._load_value_to_reg(arg1, reg1)
                self.mips_code.append(f"    beqz {reg1}, {result}")
                self._release_reg(reg1)

            elif op == "CALL":
                self.mips_code.append(f"    jal {arg1}")
                self.param_count = 0
                if result:
                    result_addr_offset = self._get_var_stack_offset(result)
                    self.mips_code.append(f"    sw $v0, {result_addr_offset}($fp)")

            elif op == "RETURN_VAL":
                self._load_value_to_reg(arg1, "$v0")

            elif op == "FUNC_END":
                self.mips_code.append("    move $sp, $fp")
                self.mips_code.append("    lw $ra, 4($sp)")
                self.mips_code.append("    lw $fp, 0($sp)")
                self.mips_code.append("    addiu $sp, $sp, 8")
                self.mips_code.append("    jr $ra")

            elif op == "REF":  # result = &arg1
                reg_addr = self._get_reg()
                self._load_address_to_reg(arg1, reg_addr)

                result_addr_offset = self._get_var_stack_offset(result)
                self.mips_code.append(f"    sw {reg_addr}, {result_addr_offset}($fp)")

                self._release_reg(reg_addr)

            elif op == "DEREF_LOAD":  # result = *arg1
                reg_ptr = self._get_reg()
                reg_val = self._get_reg()

                self._load_value_to_reg(arg1, reg_ptr)  # 加载指针（地址）
                self.mips_code.append(f"    lw {reg_val}, 0({reg_ptr})")  # 从该地址加载值

                result_addr_offset = self._get_var_stack_offset(result)
                self.mips_code.append(f"    sw {reg_val}, {result_addr_offset}($fp)")

                self._release_reg(reg_ptr)
                self._release_reg(reg_val)

            elif op == "DEREF_STORE":  # *arg1 = result
                reg_ptr = self._get_reg()
                reg_val = self._get_reg()

                self._load_value_to_reg(arg1, reg_ptr)  # 加载指针（地址）
                self._load_value_to_reg(result, reg_val)  # 加载要存储的值

                self.mips_code.append(f"    sw {reg_val}, 0({reg_ptr})")  # 在指针指向的地址存储值

                self._release_reg(reg_ptr)
                self._release_reg(reg_val)

    def generate(self, quadruples, global_symbol_table):
        functions = {}
        current_func_name = None
        for quad in quadruples:
            if quad.op == "FUNC_BEGIN":
                current_func_name = quad.arg1
                functions[current_func_name] = []
            if current_func_name:
                functions[current_func_name].append(quad)

        self.global_symbols = global_symbol_table

        self.mips_code = [".data"]
        self.mips_code.extend(["\n.text", ".globl main", "\n__start:", "    jal main", "    j main_exit"])

        main_quads = functions.pop("main", [])
        if main_quads:
            self.current_symbol_map = {}
            self.current_symbol_map.update(self.global_symbols)
            main_entry = self.global_symbols.get("main")
            if main_entry and "scope" in main_entry.extra_info:
                self.current_symbol_map.update(main_entry.extra_info["scope"])
            self._translate_quads(main_quads, self.global_symbols.get("main"))

        self.mips_code.extend(["\nmain_exit:", "    li $v0, 10", "    syscall"])

        for name, quads in functions.items():
            self.current_symbol_map = {}
            self.current_symbol_map.update(self.global_symbols)
            func_entry = self.global_symbols.get(name)
            if func_entry and "scope" in func_entry.extra_info:
                self.current_symbol_map.update(func_entry.extra_info["scope"])
            self._translate_quads(quads, func_entry)

        return "\n".join(self.mips_code)

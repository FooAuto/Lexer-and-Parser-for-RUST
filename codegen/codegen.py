from semantic.semantic import SymbolType


class CodeGenerator:
    def __init__(self):
        self.mips_code = []
        self.var_map = {}
        self.current_func_stack_offset = 0
        self.temp_regs = [f"$t{i}" for i in range(10)]
        self.free_regs = self.temp_regs[:]

    def _get_reg(self):
        if not self.free_regs:
            raise Exception("Register spill not implemented: temporary registers exhausted.")
        return self.free_regs.pop(0)

    def _release_reg(self, reg):
        if reg in self.temp_regs and reg not in self.free_regs:
            self.free_regs.insert(0, reg)
            self.free_regs.sort(key=lambda r: int(r[2:]))

    def _get_var_addr(self, var_name):
        if var_name not in self.var_map:
            self.current_func_stack_offset -= 4
            self.var_map[var_name] = self.current_func_stack_offset
        return f"{self.var_map[var_name]}($fp)"

    def _load_operand_to_reg(self, operand, reg):
        if isinstance(operand, int):
            self.mips_code.append(f"    li {reg}, {operand}")
        else:
            operand_addr = self._get_var_addr(operand)
            self.mips_code.append(f"    lw {reg}, {operand_addr}")

    def _translate_quads(self, quads):
        for quad in quads:
            op, arg1, arg2, result = quad.op, quad.arg1, quad.arg2, quad.result

            if op == "FUNC_BEGIN":
                self.mips_code.append(f"\n{arg1}:")
                self.mips_code.append("    # Function Prologue")
                self.mips_code.append("    addiu $sp, $sp, -8")
                self.mips_code.append("    sw $ra, 4($sp)")
                self.mips_code.append("    sw $fp, 0($sp)")
                self.mips_code.append("    move $fp, $sp")

                stack_space = 128
                self.mips_code.append(f"    addiu $sp, $sp, -{stack_space}")
                self.current_func_stack_offset = 0
                self.var_map.clear()

            elif op == "PARAM":
                reg_arg = self._get_reg()
                self._load_operand_to_reg(arg1, reg_arg)
                self.mips_code.append(f"    addiu $sp, $sp, -4")
                self.mips_code.append(f"    sw {reg_arg}, 0($sp)")
                self._release_reg(reg_arg)

            elif op == "ASSIGN":
                reg1 = self._get_reg()
                self._load_operand_to_reg(arg1, reg1)
                result_addr = self._get_var_addr(result)
                self.mips_code.append(f"    sw {reg1}, {result_addr}")
                self._release_reg(reg1)

            elif op in ("ADD", "SUB", "MUL", "DIV"):
                reg1 = self._get_reg()
                reg2 = self._get_reg()
                self._load_operand_to_reg(arg1, reg1)
                self._load_operand_to_reg(arg2, reg2)

                op_map = {"ADD": "addu", "SUB": "subu", "MUL": "mul", "DIV": "div"}
                self.mips_code.append(f"    {op_map[op]} {reg1}, {reg1}, {reg2}")

                result_addr = self._get_var_addr(result)
                self.mips_code.append(f"    sw {reg1}, {result_addr}")
                self._release_reg(reg1)
                self._release_reg(reg2)

            elif op in ("LT", "LE", "GT", "GE", "EQ", "NE"):
                reg1 = self._get_reg()
                reg2 = self._get_reg()
                self._load_operand_to_reg(arg1, reg1)
                self._load_operand_to_reg(arg2, reg2)

                op_map = {"LT": "slt", "LE": "sle", "GT": "sgt", "GE": "sge", "EQ": "seq", "NE": "sne"}
                self.mips_code.append(f"    {op_map[op]} {reg1}, {reg1}, {reg2}")

                result_addr = self._get_var_addr(result)
                self.mips_code.append(f"    sw {reg1}, {result_addr}")
                self._release_reg(reg1)
                self._release_reg(reg2)

            elif op == "LABEL":
                self.mips_code.append(f"{result}:")

            elif op == "JUMP":
                self.mips_code.append(f"    j {result}")

            elif op == "IF_FALSE":
                reg1 = self._get_reg()
                self._load_operand_to_reg(arg1, reg1)
                self.mips_code.append(f"    beqz {reg1}, {result}")
                self._release_reg(reg1)

            elif op == "CALL":
                self.mips_code.append(f"    jal {arg1}")
                if result:
                    result_addr = self._get_var_addr(result)
                    self.mips_code.append(f"    sw $v0, {result_addr}")

            elif op == "RETURN_VAL":
                self._load_operand_to_reg(arg1, "$v0")

            elif op == "FUNC_END":
                self.mips_code.append("    # Function Epilogue")
                self.mips_code.append("    move $sp, $fp")
                self.mips_code.append("    lw $ra, 4($sp)")
                self.mips_code.append("    lw $fp, 0($sp)")
                self.mips_code.append("    addiu $sp, $sp, 8")
                self.mips_code.append("    jr $ra")

    def generate(self, quadruples, symbol_tables):
        # 1. 按函数分割四元式
        functions = {}
        current_func_name = None
        for quad in quadruples:
            if quad.op == "FUNC_BEGIN":
                current_func_name = quad.arg1
                functions[current_func_name] = []
            if current_func_name:
                functions[current_func_name].append(quad)

        # 2. 生成 .data 段
        self.mips_code = [".data"]
        global_scope = symbol_tables[0]
        for name, entry in global_scope.items():
            if entry.sym_type == SymbolType.VARIABLE:
                self.mips_code.append(f"{name}: .word 0")

        # 3. 生成 .text 段的引导部分
        self.mips_code.extend(["\n.text", ".globl main", "\n# Program entry point", "__start:" "    j main"])

        # 4. 生成 main 函数代码
        if "main" in functions:
            self._translate_quads(functions["main"])

        # 5. 生成 main 函数结束后的退出代码
        self.mips_code.append("\n# Exit program after main returns")
        self.mips_code.append("main_exit:")
        self.mips_code.append("    li $v0, 10")
        self.mips_code.append("    syscall")

        # 6. 生成所有其他函数的代码
        for name, quads in functions.items():
            if name != "main":
                self._translate_quads(quads)

        return "\n".join(self.mips_code)

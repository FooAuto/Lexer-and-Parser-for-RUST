### 语义分析改说明

#### 1、调用
在语法分析器类中实例化了一个语义分析器。每次规约时调用：```self.semantic_analyzer.dispatch_semantic_action()```
最后到达接收状态返回时，可以返回语法树，四元式和字符表

#### 2、语义分析流程
语法分析中调用的```dispatch_semantic_action()```函数是一个调度函数。它会根据这一次规约使用的产生式，决定调用哪个函数去处理（处理就是做语义分析）。语义具体分析的流程就类似PPT里对于各类语句的语义分析。

### TODO：
1. 函数声明在函数调用前不会出错，但是函数声明在后会导致出错找不到函数。可能需要修改`lexparser.py`，添加函数预声明功能（即预先遍历全部函数并添加到符号表中）。
2. break、continue时loop stack永远为空。因为在翻译“WhileStatement -> WHILE Expression StatementBlock”时get_child_attrs()会提前处理loop stack中的信息，导致loop stack为空，所以处理break、continue时永远报错。
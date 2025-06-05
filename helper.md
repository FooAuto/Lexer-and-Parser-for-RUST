### 语义分析改说明

#### 1、调用
在语法分析器类中实例化了一个语义分析器。每次规约时调用：```self.semantic_analyzer.dispatch_semantic_action()```
最后到达接收状态返回时，可以返回语法树，四元式和字符表

#### 2、语义分析流程
语法分析中调用的```dispatch_semantic_action()```函数是一个调度函数。它会根据这一次规约使用的产生式，决定调用哪个函数去处理（处理就是做语义分析）。语义具体分析的流程就类似PPT里对于各类语句的语义分析。

### TODO：
1. 3.3 函数调用

```
 fn program_3_3__5__a() {
 }
 fn program_3_3__5__b() {
 let mut a=program_3_3__5__a();
 }
```

应该报错：无返回值函数不能作为右值

但是正常解析

2. 7.4 循环表达式

```
fn program_7_4() {
    let mut a=loop {
    break 2;
    };
}
```

应该正常解析，但是报错

**'break' statement outside of a loop**
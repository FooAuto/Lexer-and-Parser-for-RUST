// 测试文件：涵盖 Rust 基础语法规则
// 用于词法和语法分析工具的测试

// 1. 注释
// 单行注释
/* 块注释 */
/* 嵌套块注释 /* 内部注释 */ 外部注释 */

// 2. 标识符（包括特定用例 if123）
fn if123() {
    println!("This is a function named if123");
}

// 3. 关键字、符号和整数（包括特定用例 if=123）
fn test_if_assignment() {
    let x = if=123; // 应解析为：if (关键字), = (符号), 123 (整数)
    println!("x = {}", x);
}

// 4. 基本数据类型
fn basic_types() {
    let integer: i32 = 42; // 整数
    let float: f64 = 3.14; // 浮点数
    let boolean: bool = true; // 布尔值
    let character: char = 'A'; // 字符
    let string: &str = "Hello, Rust!"; // 字符串
}

// 5. 变量声明与绑定
fn variables() {
    let immutable = 10; // 不可变绑定
    let mut mutable = 20; // 可变绑定
    mutable = 30; // 修改可变变量
    const CONSTANT: i32 = 100; // 常量
}

// 6. 控制流
fn control_flow() {
    // if 语句
    let number = 7;
    if number > 5 {
        println!("Number is greater than 5");
    } else if number == 5 {
        println!("Number is 5");
    } else {
        println!("Number is less than 5");
    }

    // loop 循环
    let mut count = 0;
    loop {
        count += 1;
        if count == 3 {
            break;
        }
    }

    // while 循环
    while count < 5 {
        count += 1;
    }

    // for 循环
    for i in 0..3 {
        println!("i = {}", i);
    }
}

// 7. 函数定义与调用
fn add(a: i32, b: i32) -> i32 {
    a + b
}

// 8. 结构体
struct Point {
    x: i32,
    y: i32,
}

// 9. 枚举
enum Color {
    Red,
    Green,
    Blue,
}

// 10. 模式匹配
fn pattern_matching() {
    let color = Color::Red;
    match color {
        Color::Red => println!("It's red"),
        Color::Green => println!("It's green"),
        Color::Blue => println!("It's blue"),
    }
}

// 11. 数组与切片
fn arrays_and_slices() {
    let array = [1, 2, 3, 4, 5];
    let slice: &[i32] = &array[1..3];
}

// 12. 元组
fn tuples() {
    let tuple: (i32, f64, char) = (42, 3.14, 'Z');
    let (x, y, z) = tuple;
}

// 13. 运算符
fn operators() {
    let a = 10;
    let b = 5;
    let sum = a + b; // 加法
    let product = a * b; // 乘法
    let logical = a > b && b != 0; // 逻辑运算
}

// 14. 主函数
fn main() {
    if123();
    test_if_assignment();
    basic_types();
    variables();
    control_flow();
    println!("Sum: {}", add(5, 3));
    pattern_matching();
    arrays_and_slices();
    tuples();
    operators();
}
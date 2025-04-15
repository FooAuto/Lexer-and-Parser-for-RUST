fn add(mut a:i32, mut b:i32) -> i32 {
    let mut sum:i32 = a + b;
    return sum;
}

fn main() {
    let mut x:i32;
    x = 10;
    let mut y:i32 = 20;
    let mut z = add(x, y);
    return;
}
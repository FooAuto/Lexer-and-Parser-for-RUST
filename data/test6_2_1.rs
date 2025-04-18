fn program_6_2_1() {
    let mut a:i32 = 1;
    let mut b:&mut i32 = &mut a;
    let mut c:i32 = *b;
    *b = 2;
}
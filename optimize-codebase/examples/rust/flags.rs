// Standalone, no dependencies. Use an explicit project-local output path; see references/examples.md.
// This is an illustrative fixture, not a concurrency-safe or versioned wire API.
fn pack(src: &[u8]) -> Vec<u64> {
    let mut words=vec![0; src.len()/64 + usize::from(src.len()%64 != 0)];
    for (i,v) in src.iter().enumerate() {
        if *v!=0 {words[i/64] |= 1u64 << (i%64);}
    }
    words
}
fn count(words: &[u64], n: usize) -> usize {
    words.iter().enumerate().map(|(i,&v)| {
        let clean=if i+1==words.len() && n%64!=0 {v & ((1u64<<(n%64))-1)} else {v};
        clean.count_ones() as usize
    }).sum()
}
#[test]
fn boundary_counts() {
    for n in [0usize,1,63,64,65,127,128,129,1000000] {
        let src: Vec<u8>=(0..n).map(|i|u8::from(i%3==0)).collect();
        assert_eq!(count(&pack(&src),n),src.iter().filter(|&&x|x!=0).count());
    }
}
#[test]
fn ignores_dirty_tail() {assert_eq!(count(&[u64::MAX,u64::MAX],65),65);}

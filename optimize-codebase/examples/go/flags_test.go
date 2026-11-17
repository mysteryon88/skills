package flags

import (
	"math/rand"
	"testing"
)

var sink int
var byteSink []byte
var wordSink []uint64

func TestRoundTripAndUpdates(t *testing.T) {
	rng := rand.New(rand.NewSource(42))
	for _, n := range []int{0, 1, 7, 8, 63, 64, 65, 127, 128, 129, 1001, 1000000} {
		src := make([]byte, n)
		for i := range src {
			src[i] = byte(rng.Intn(2))
		}
		words := pack(src)
		if countBytes(src) != countWords(words, n) {
			t.Fatalf("count n=%d", n)
		}
		for i, v := range src {
			got, ok := get(words, n, i)
			if !ok || got != (v != 0) {
				t.Fatalf("get %d/%d", i, n)
			}
		}
		if set(words, n, -1, true) || set(words, n, n, true) {
			t.Fatal("out of range accepted")
		}
		if _, ok := get(words, n, n); ok {
			t.Fatal("out of range get")
		}
		if n > 0 {
			for _, i := range []int{0, n / 2, n - 1} {
				if !set(words, n, i, true) {
					t.Fatal("set")
				}
				src[i] = 1
				if countBytes(src) != countWords(words, n) {
					t.Fatal("after set")
				}
				set(words, n, i, false)
				src[i] = 0
				if countBytes(src) != countWords(words, n) {
					t.Fatal("after clear")
				}
			}
		}
	}
}
func TestTailBitsAndPayload(t *testing.T) {
	if countWords([]uint64{^uint64(0), ^uint64(0)}, 65) != 65 {
		t.Fatal("tail bits counted")
	}
	n := 1000000
	words := pack(make([]byte, n))
	if len(words)*8 != 125000 {
		t.Fatal("unexpected payload")
	}
	t.Logf("payload bytes=%d packed=%d; excludes headers/capacity/RSS", n, len(words)*8)
}
func TestRepeatedIdempotentSet(t *testing.T) {
	words := pack(make([]byte, 65))
	for i := 0; i < 100; i++ {
		set(words, 65, 64, true)
	}
	if countWords(words, 65) != 1 {
		t.Fatal("duplicate set")
	}
}

// Read-only steady-state: construction is intentionally outside BOTH timers.
func BenchmarkCountBytes(b *testing.B) {
	src := make([]byte, 1000000)
	for i := range src {
		if i%3 == 0 {
			src[i] = 1
		}
	}
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		sink = countBytes(src)
	}
}
func BenchmarkCountPacked(b *testing.B) {
	src := make([]byte, 1000000)
	for i := range src {
		if i%3 == 0 {
			src[i] = 1
		}
	}
	words := pack(src)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		sink = countWords(words, len(src))
	}
}

// End-to-end from identical already available byte input: copy/pack + 20 counts.
func BenchmarkLifecycleBytes(b *testing.B) {
	src := make([]byte, 1000000)
	for i := range src {
		if i%3 == 0 {
			src[i] = 1
		}
	}
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		owned := append([]byte(nil), src...)
		total := 0
		for j := 0; j < 20; j++ {
			total += countBytes(owned)
		}
		byteSink = owned
		sink = total
	}
}
func BenchmarkLifecyclePacked(b *testing.B) {
	src := make([]byte, 1000000)
	for i := range src {
		if i%3 == 0 {
			src[i] = 1
		}
	}
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		owned := pack(src)
		total := 0
		for j := 0; j < 20; j++ {
			total += countWords(owned, len(src))
		}
		wordSink = owned
		sink = total
	}
}

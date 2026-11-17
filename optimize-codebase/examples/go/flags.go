// Package flags is a synthetic fixture, not an API or wire-format migration.
package flags

import "math/bits"

// pack accepts only internal 0/1 bytes. The caller owns the returned words.
func pack(src []byte) []uint64 {
	words := make([]uint64, len(src)/64+boolInt(len(src)%64 != 0))
	for i, v := range src {
		if v != 0 {
			words[i/64] |= uint64(1) << uint(i%64)
		}
	}
	return words
}
func boolInt(v bool) int {
	if v {
		return 1
	}
	return 0
}
func countBytes(src []byte) int {
	count := 0
	for _, v := range src {
		if v != 0 {
			count++
		}
	}
	return count
}
func countWords(words []uint64, n int) int {
	count := 0
	for i, v := range words {
		if i == len(words)-1 && n%64 != 0 {
			v &= (uint64(1) << uint(n%64)) - 1
		}
		count += bits.OnesCount64(v)
	}
	return count
}
func get(words []uint64, n, i int) (bool, bool) {
	if i < 0 || i >= n {
		return false, false
	}
	return words[i/64]&(uint64(1)<<uint(i%64)) != 0, true
}
func set(words []uint64, n, i int, value bool) bool {
	if i < 0 || i >= n {
		return false
	}
	mask := uint64(1) << uint(i%64)
	if value {
		words[i/64] |= mask
	} else {
		words[i/64] &^= mask
	}
	return true
}

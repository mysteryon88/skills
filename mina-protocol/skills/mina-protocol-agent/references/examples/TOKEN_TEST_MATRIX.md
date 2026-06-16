# Example token test matrix

| Invariant | Positive test | Negative test | Edge test |
|---|---|---|---|
| Only admin can mint | admin mints | attacker mint fails | old admin fails after rotation |
| Burn cannot exceed balance | user burns owned tokens | burn too much fails | burn zero behavior documented |
| Supply invariant holds | mint/burn sequence | failed tx does not change supply | max UInt64 attempt |
| Transfer approval is strict | valid transfer | child update abuse fails | wrong tokenId fails |
| VK cannot be replaced by user | intended upgrade works | attacker VK change fails | locked app cannot upgrade |

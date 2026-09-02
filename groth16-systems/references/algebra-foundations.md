# Algebra Foundations

Use only the parts needed by the current derivation. Groth16 circuit arithmetic, elliptic-curve coordinates, and pairing groups are related but distinct objects.

## Fields and polynomials

R1CS values live in a finite scalar field $F_r$. Addition, subtraction, and multiplication are reduced modulo the prime $r$. Every nonzero element has a multiplicative inverse; zero does not. Therefore a field equation does not by itself preserve an intended interpretation as a nonnegative integer.

For $f(X), g(X) \in F_r[X]$ with $g \ne 0$, polynomial division gives unique $q(X)$ and $s(X)$ such that:

$$
f(X)=q(X)g(X)+s(X), \qquad \deg s < \deg g.
$$

Distinct points $\omega_1,\ldots,\omega_m$ determine a unique polynomial of degree below $m$ for any chosen values. The Lagrange basis is:

$$
L_i(X)=\prod_{k\ne i}\frac{X-\omega_k}{\omega_i-\omega_k},
\qquad L_i(\omega_k)=
\begin{cases}
1 & i=k,\\
0 & i\ne k.
\end{cases}
$$

This interpolation property is the bridge from individual R1CS rows to QAP polynomials.

## Groups and pairings

Groth16 uses prime-order groups $G_1$, $G_2$, and $G_T$ of the same order $r$, with a bilinear, non-degenerate pairing:

$$
e:G_1\times G_2\to G_T,
\qquad
e([a]P,[b]Q)=e(P,Q)^{ab}.
$$

Scalar multiplication encodes a field scalar as a group element. Recovering $a$ from $[a]P$ is assumed hard under the discrete-logarithm problem; the deterministic encoding alone does not provide zero knowledge. The pairing exposes selected multiplicative relations between encoded exponents. Security relies on the concrete curve, subgroup, pairing construction, and assumptions in the protocol analysis—not merely on the displayed identity.

The elliptic curve is defined over a base field $F_q$, while its prime-order subgroup has scalar field $F_r$. Do not interchange base-field coordinates with circuit scalars. When accepting serialized points, validate canonical encoding, curve membership, subgroup membership, and exceptional points according to the implementation.

At an external boundary, accept one canonical encoding for each field element or point. Do not repair malformed data by reducing coordinates or public values modulo a field, swapping extension-field components, padding or truncating coordinates, or relabeling a curve. Regenerate the artifact or fix the converter and verify it across implementations.

Validation responsibility depends on the boundary:

- fixed verification-key points can be validated before they are embedded;
- proof points are attacker-controlled and need runtime validation or an equivalent guarantee from the consuming API;
- a successful decoder does not necessarily prove subgroup membership or reject the identity.

## What to keep distinct

| Object | Role |
|---|---|
| $F_r$ element | Circuit value, witness coordinate, or protocol scalar |
| $F_r[X]$ polynomial | QAP encoding of all constraint rows |
| $G_1/G_2$ point | Encoded scalar or polynomial evaluation |
| $G_T$ element | Pairing result used by verification |
| $F_q$ element | Elliptic-curve coordinate |

Keep application integers separate from $F_r$. If an external value has business meaning, reject non-canonical field aliases and enforce the application range before using it.

## Primary sources

- [Groth16 paper](https://eprint.iacr.org/2016/260)
- [Circom field elements](https://docs.circom.io/circom-language/basic-operators/#field-elements)

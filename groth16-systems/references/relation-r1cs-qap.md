# Relation, R1CS, and QAP

Use this reference to carry one claim from a formal relation into constraints and then into the polynomial identity consumed by Groth16.

## Contents

- Relation, assignment, and R1CS rows
- Column interpolation and QAP divisibility
- Fresh worked example with valid and invalid witnesses
- Interpretation and debugging order

## Relation and assignment

Let $R(I,W)$ be a relation over a field $F_r$. The ordered public instance is $I$; private inputs and auxiliary values are $W$. A satisfying witness obeys:

$$
R(I,W)=\mathrm{true}.
$$

R1CS uses an assignment vector such as:

$$
z=(1,I_1,\ldots,I_n,W_1,\ldots,W_t).
$$

The leading $1$ lets a linear combination contain constants. The exact column order is part of the compiled artifact. Public/private partitioning changes what the verifier learns and binds, even if the arithmetic rows are otherwise identical.

## R1CS

An R1CS instance is three matrices $A,B,C\in F_r^{m\times N}$. Row $i$ requires:

$$
\langle A_i,z\rangle\,\langle B_i,z\rangle=\langle C_i,z\rangle.
$$

Additions and scalar multiples stay inside a linear combination. Higher-degree products require auxiliary witness values and more rows. R1CS satisfaction is field equality, so integer ranges, signedness, bitness, and nonzero conditions need explicit constraints.

## From rows to polynomials

Choose distinct row points $\omega_1,\ldots,\omega_m\in F_r$ and their Lagrange basis polynomials $L_i(X)$. Interpolate each matrix column:

$$
A_j(X)=\sum_{i=1}^{m}A_{i,j}L_i(X),\quad
B_j(X)=\sum_{i=1}^{m}B_{i,j}L_i(X),\quad
C_j(X)=\sum_{i=1}^{m}C_{i,j}L_i(X).
$$

Combine those columns with the assignment:

$$
A_z(X)=\sum_j z_jA_j(X),\quad
B_z(X)=\sum_j z_jB_j(X),\quad
C_z(X)=\sum_j z_jC_j(X).
$$

At a row point, interpolation recovers that row's linear combinations:

$$
A_z(\omega_i)=\langle A_i,z\rangle,
\quad B_z(\omega_i)=\langle B_i,z\rangle,
\quad C_z(\omega_i)=\langle C_i,z\rangle.
$$

Define:

$$
P_z(X)=A_z(X)B_z(X)-C_z(X),
\qquad
T(X)=\prod_{i=1}^{m}(X-\omega_i).
$$

The assignment satisfies every row exactly when $P_z(\omega_i)=0$ for every $i$. Because the row points are distinct and the coefficients form a field, this is equivalent to:

$$
T(X)\mid P_z(X),
\qquad
P_z(X)=H(X)T(X)
$$

for a quotient polynomial $H(X)$. With the interpolation above, $A_z,B_z,C_z$ have degree below $m$, so $P_z$ has degree at most $2m-2$ and $H$ at most $m-2$ when the identity holds.

## Fresh worked example: $y=x^2$

This example is derived here rather than copied from an external tutorial. Work over a scalar field $F_r$ with $r>29$ so the displayed integer representatives are easy to read; every coefficient is still interpreted modulo $r$.

Make $y$ public, $x$ private, and introduce the auxiliary witness $v$. With column order

$$
z=(1,y,x,v),
$$

encode the relation with two rows:

$$
x\cdot x=v,
\qquad
v\cdot1=y.
$$

The matrices are:

$$
A=\begin{pmatrix}0&0&1&0\\0&0&0&1\end{pmatrix},\quad
B=\begin{pmatrix}0&0&1&0\\1&0&0&0\end{pmatrix},\quad
C=\begin{pmatrix}0&0&0&1\\0&1&0&0\end{pmatrix}.
$$

Choose row points $\omega_1=1$ and $\omega_2=2$. Their Lagrange basis is:

$$
L_1(X)=2-X,
\qquad
L_2(X)=X-1.
$$

The nonzero column interpolants are:

$$
A_x=L_1,\quad A_v=L_2,\qquad
B_0=L_2,\quad B_x=L_1,\qquad
C_y=L_2,\quad C_v=L_1.
$$

For the valid assignment $z=(1,9,3,9)$:

$$
A_z=3L_1+9L_2=6X-3,
$$

$$
B_z=3L_1+L_2=5-2X,
\qquad
C_z=9L_1+9L_2=9.
$$

Therefore:

$$
\begin{aligned}
P_z(X)
&=(6X-3)(5-2X)-9\\
&=-12X^2+36X-24\\
&=-12(X-1)(X-2).
\end{aligned}
$$

Thus $T(X)=(X-1)(X-2)$ divides $P_z(X)$ and $H(X)=-12$.

Now use the invalid assignment $z'=(1,8,3,8)$. The second row still holds, but the first has residual $3\cdot3-8=1$. Its aggregate polynomial is:

$$
P_{z'}(X)=(5X-2)(5-2X)-8=-10X^2+29X-18.
$$

Polynomial division gives:

$$
P_{z'}(X)=-10T(X)+(2-X).
$$

The nonzero remainder $2-X$ records the failed row: it evaluates to $1$ at $\omega_1$ and to $0$ at $\omega_2$. Hence $T\nmid P_{z'}$.

## What the equivalence does and does not say

- A nonzero remainder identifies an unsatisfied compiled constraint system.
- A zero remainder says all compiled rows hold; it does not show that the rows encode the intended application relation.
- Different R1CS encodings can represent the same relation and produce different QAPs and keys.
- Compiler optimization may change row and wire layout without changing the accepted relation.
- QAP divisibility is an algebraic aggregation of all rows, not a separate application-level check.

## Debugging order

1. Evaluate each R1CS row on the concrete assignment.
2. Find the first nonzero residual before constructing QAP polynomials.
3. Confirm row points are distinct and field operations use the circuit scalar field.
4. Evaluate $P_z(\omega_i)$ and compare it with the row residual.
5. Divide by $T$ only after the pointwise checks agree.

## Primary sources

- [Groth16 paper](https://eprint.iacr.org/2016/260)
- [Circom constraint generation](https://docs.circom.io/circom-language/constraint-generation/)

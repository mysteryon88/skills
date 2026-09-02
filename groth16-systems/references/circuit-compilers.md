# Circuit Compilers and Witness Generation

Use this reference when source code, compiled constraints, and witness behavior appear to disagree.

## Two programs, one relation

A circuit toolchain typically produces:

1. a fixed constraint system checked by the proof system;
2. witness-generation code that computes one proposed assignment.

The witness generator can calculate values that never become constrained. Conversely, a correct constraint can reject a buggy witness generator. Audit these programs separately, then confirm they agree on valid inputs.

## Statement and signal inventory

Before reviewing source, classify each value as public input, private witness, public output, compile-time parameter, or externally derived value. Record public-input order, type, range, encoding, and application meaning. Then trace every value that affects an output or authorization decision through an actual constraint path.

Look for computed-but-unconstrained witnesses, free selector branches, hint results without an independent equation, dead outputs, partially constrained composite values, and unintended alternative witnesses. A successful witness calculation or one valid proof is not constraint-completeness evidence.

## Static topology

R1CS dimensions and wiring are fixed at compilation time. Private values may select between already-defined branches, but they cannot decide how many constraints exist. Loops, array sizes, and component construction therefore need compile-time-known structure unless the language explicitly lowers them to fixed constraints.

## Common encodings

### Equality and assignment

A host-language or witness-only assignment is not an equality constraint. In Circom, `<--` assigns during witness generation, while `<==` assigns and adds the corresponding equality constraint. Read the compiled R1CS when operator behavior matters.

### Booleanity

For a selector $b$, require:

$$
b(b-1)=0.
$$

Using $b$ in a selection formula does not make it boolean.

### Inverse and zero policy

To prove that $x$ is nonzero, constrain an inverse witness:

$$
x\cdot x^{-1}=1.
$$

If zero is valid, encode an explicit flag and gate both cases. Division in witness-generation code alone is not a constraint.

### Conditional selection

For boolean $b$:

$$
z=bx+(1-b)y.
$$

Both candidate branches must have defined witness values because circuit topology is fixed.

### Bits and ranges

An $n$-bit decomposition needs both reconstruction and bit constraints:

$$
x=\sum_{i=0}^{n-1}2^ib_i,
\qquad b_i(b_i-1)=0.
$$

Choose $n$ so the representation is canonical in $F_r$. Otherwise different integers may reduce to the same field element.

### Higher-degree expressions

Split a product into multiplication gates with constrained auxiliary values. An R1CS row permits a product of two linear combinations, not an arbitrary-degree expression.

### Hashes, Merkle paths, and serialization

The circuit and application must agree on hash parameters, domain tag, byte and bit order, chunk width, padding, length commitment, and field conversion. A Merkle path must constrain both siblings and direction/index data. Fix depth, leaf encoding, node order, and empty-node convention; variable-depth paths need a rule that prevents omitted levels from changing the statement.

## Compiler evidence

- Source describes intended construction.
- Compiled R1CS is the relation actually proved.
- Symbol data maps source signals to compiled wires.
- Witness code explains how assignments are produced.
- Compiler diagnostics and optimization settings affect what is visible for review.

Do not infer constraint coverage from source assignments alone. Inspect generated artifacts and mutate security-relevant witness classes against the R1CS.

Framework hints, custom solvers, host assertions, and witness-only assignments are all untrusted computations until an independent constraint binds their results. This invariant applies across Circom, Gnark, Arkworks, and other R1CS frontends even though their APIs differ.

## Primary sources

- [Circom constraint generation](https://docs.circom.io/circom-language/constraint-generation/)
- [Circom compiler phases](https://docs.circom.io/circom-language/compiler-phases/)
- [Circom compiler messages](https://docs.circom.io/circom-language/circom-insight/compiler-messages/)

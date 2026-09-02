# Groth16 Protocol

Use this reference after the relation, R1CS, and QAP are clear. It describes the protocol boundary without replacing the notation and serialization rules of a concrete library.

## Contents

- Statement and circuit-specific setup
- Canonical CRS queries and prover equations
- Pairing verification
- Zero-knowledge simulation and toxic-waste distinction
- Setup lifecycle and failure classification

## Statement proved

Groth16 is a preprocessing zk-SNARK for an arithmetic relation. For a fixed circuit, the prover demonstrates knowledge of private witness values that complete an ordered public instance into a satisfying assignment. The proof does not authenticate the prover, authorize an action, or validate predicates omitted from the circuit.

## Setup

The setup samples hidden field elements conventionally written $\tau,\alpha,\beta,\gamma,\delta$, with $\gamma,\delta\ne0$ and $T(\tau)\ne0$, and publishes group encodings of the combinations needed for proving and verification. The circuit's QAP polynomials are evaluated at the hidden point $\tau$ inside those encodings; users should not learn the trapdoor values themselves.

Vanilla Groth16 has circuit-specific preprocessing. Toolchains may split a ceremony into a reusable powers-of-tau phase and a circuit-specific phase, but that workflow is an implementation construction around the protocol, not a universal Groth16 verification key.

The resulting material is commonly divided into:

- a proving key containing encodings needed for private witness terms, the QAP quotient, and proof randomization;
- a verification key containing fixed protocol terms and encodings for the ordered public instance.

## Canonical query notation

Use additive group notation $[a]_1=aP\in G_1$ and $[a]_2=aQ\in G_2$. Let

$$
z=(z_0,z_1,\ldots,z_N),\qquad z_0=1,
$$

where indices $0\ldots\ell$ are the constant and public inputs, while indices $\ell+1\ldots N$ are private or auxiliary witness values. For the QAP polynomials from the relation reference, define:

$$
K_j(\tau)=\beta A_j(\tau)+\alpha B_j(\tau)+C_j(\tau).
$$

A direct query-form proving key contains the elements needed to form:

$$
[\alpha]_1,\ [\beta]_1,\ [\beta]_2,\ [\delta]_1,\ [\delta]_2,
$$

$$
\{[A_j(\tau)]_1\}_j,
\qquad
\{[B_j(\tau)]_1,[B_j(\tau)]_2\}_j,
$$

$$
\left\{\left[\frac{K_j(\tau)}{\delta}\right]_1\right\}_{j>\ell},
\qquad
\left\{\left[\frac{\tau^kT(\tau)}{\delta}\right]_1\right\}_{0\le k\le\deg H}.
$$

The verification key contains:

$$
[\alpha]_1,\ [\beta]_2,\ [\gamma]_2,\ [\delta]_2,
\qquad
\left\{\left[\frac{K_j(\tau)}{\gamma}\right]_1\right\}_{0\le j\le\ell}.
$$

Concrete proving keys may store equivalent powers or prepared points instead of this literal list. Check the target library before mapping these equations to serialized fields.

## Proving

The prover computes a satisfying assignment, the corresponding QAP quotient $H(X)=\sum_k h_kX^k$, and randomized group combinations derived from the proving key. Define:

$$
U=\sum_{j=0}^{N}z_jA_j(\tau),
\qquad
V=\sum_{j=0}^{N}z_jB_j(\tau).
$$

For fresh independent $\rho,\sigma\leftarrow F_r$, form:

$$
\pi_A=[\alpha+U+\rho\delta]_1,
$$

$$
\pi_B=[\beta+V+\sigma\delta]_2,
\qquad
\pi_{B,1}=[\beta+V+\sigma\delta]_1,
$$

and

$$
\begin{aligned}
\pi_C={}&
\sum_{j=\ell+1}^{N}z_j
\left[\frac{K_j(\tau)}{\delta}\right]_1
+\sum_k h_k
\left[\frac{\tau^kT(\tau)}{\delta}\right]_1\\
&+\sigma\pi_A+\rho\pi_{B,1}-\rho\sigma[\delta]_1.
\end{aligned}
$$

A Groth16 proof has three group elements:

$$
\pi_A\in G_1,\qquad \pi_B\in G_2,\qquad \pi_C\in G_1.
$$

The complete exponents of $\pi_A$ and $\pi_B$ are independently uniform because $\rho$ and $\sigma$ are fresh and $\delta\ne0$. The compensating terms in $\pi_C$ preserve the verification equation. Mathematical proof tuples are commonly written $(\pi_A,\pi_B,\pi_C)$, but serialized point ordering and sign conventions are implementation contracts.

## Verification

The verifier first forms the verification-key linear combination, including the constant coordinate:

$$
vk_I=\sum_{j=0}^{\ell}z_j
\left[\frac{K_j(\tau)}{\gamma}\right]_1.
$$

A common multiplicative presentation is:

$$
e(\pi_A,\pi_B)=
e([\alpha]_1,[\beta]_2)\,
e(vk_I,[\gamma]_2)\,
e(\pi_C,[\delta]_2).
$$

The pairing equation checks the encoded QAP identity at the hidden setup point while binding the proof to the supplied public instance. Exact signs and operand order must come from the target implementation.

Before this equation, a verifier must enforce the implementation's input contract: public-input count and order, canonical scalar encoding, proof decoding, curve and subgroup membership, and exceptional-point rules.

## Zero-knowledge simulation

Zero knowledge is stronger than saying that group encodings "look hidden." It is formalized by a simulator that can reproduce the proof distribution from the public instance and a simulation trapdoor, without receiving the witness.

For the canonical equations above, let the simulation trapdoor reveal the setup scalars and define the public contribution:

$$
K_{\mathrm{pub}}=\sum_{j=0}^{\ell}z_jK_j(\tau).
$$

Choose independent uniform $a,b\leftarrow F_r$ and output:

$$
\pi_A=[a]_1,
\qquad
\pi_B=[b]_2,
\qquad
\pi_C=\left[\frac{ab-\alpha\beta-K_{\mathrm{pub}}}{\delta}\right]_1.
$$

The verifier equation holds because $vk_I=[K_{\mathrm{pub}}/\gamma]_1$. In a real proof, $\alpha+U+\rho\delta$ and $\beta+V+\sigma\delta$ are independently uniform when $\rho,\sigma$ are uniform, and the verification equation fixes the matching $\pi_C$. This gives the same proof distribution in the canonical prime-order model and explains the perfect zero-knowledge argument.

Simulation is a security-proof capability, not an API offered to an ordinary prover. The simulator receives trapdoor information that production participants must not retain. If an attacker obtains enough setup trapdoor data to perform this computation, they can generate accepting proofs without witnesses; that breaks soundness of the deployed CRS rather than contradicting zero knowledge.

## Security boundary

| Property | What must hold |
|---|---|
| Completeness | Honest proving for a satisfying assignment verifies |
| Knowledge soundness | An accepted proof implies knowledge of a satisfying witness under the paper's model and assumptions |
| Zero knowledge | Proofs hide the witness beyond what the public instance reveals |
| Succinctness | Proof size and pairing-based verification stay small relative to the circuit |

These properties apply to the encoded relation and valid parameters. They do not repair an underconstrained circuit, unsafe deserialization, a public-input mapping bug, or compromised setup.

Setup trapdoors are toxic waste: retaining enough of them can undermine soundness. For a multiparty ceremony, verify each contribution and the final circuit binding, preserve the transcript, and rely on the concrete ceremony's guarantee that at least one honest participant destroyed its secret contribution.

## Setup lifecycle

A single local contributor is suitable only for disposable development parameters. Mark those artifacts as non-production and keep their entropy, private inputs, witnesses, and temporary contributor state out of repositories and logs.

For production parameters:

1. freeze and review the exact circuit or R1CS before circuit-specific setup;
2. select setup material with sufficient capacity and traceable provenance;
3. define participant, coordinator, entropy, interruption, retry, and incident procedures;
4. verify every contribution and the final transcript with the pinned proving tool;
5. publish stable hashes, versions, commands, attestations, and verification output;
6. bind the deployed verifier to the final circuit, proving-key, and verification-key identity;
7. define which circuit, compiler, public-layout, backend, or protocol changes require new parameters.

A transcript can show that contributions were processed and verified; it cannot by itself prove that every participant destroyed secret state. Document the trust argument and the response to suspected compromise.

The phrase “universal setup” does not remove provenance requirements. It changes which material can be reused and which circuit-specific preprocessing remains. Follow the selected proof system rather than applying Groth16 phase terminology to another system.

## Failure classification

- Witness construction fails: inspect inputs and witness-generation code.
- R1CS check fails: find the first unsatisfied row.
- Proof generation fails after R1CS passes: check proving-key/circuit compatibility and tool versions.
- Local proof verifies but deployed verification fails: compare verification key, public ordering, field reduction, serialization, curve checks, and verifier conventions.
- Every test proof verifies but the claim is wrong: look for missing constraints or application checks before investigating pairings.

## Primary source

- [Jens Groth, “On the Size of Pairing-based Non-interactive Arguments”](https://eprint.iacr.org/2016/260)

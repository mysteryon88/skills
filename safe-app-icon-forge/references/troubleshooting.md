# Troubleshooting

## Renderer not found
Install Inkscape through the operating system or a trusted administrator process and place the official launcher on `PATH`. The skill never downloads it.

## Version, hash, or environment mismatch
Run `renderer-info`. Confirm binary origin and the current OS/architecture/Python environment. Maintainers may create a separate candidate lock with `update-renderer-lock`; never weaken the release lock just to pass.

## Path rejected
Run from a common invocation directory and use forward-slash relative paths without `..`. Do not use symlinks. On Windows avoid device names, trailing dots/spaces, backslash ambiguity, and names colliding only by case.

## JSON is noncanonical
Use the generated template structure and write JSON with sorted keys, two-space indentation, ASCII escaping, and one trailing newline. Do not manually copy compact or reordered JSON. Preview/build hashes canonical bytes exactly.

## SVG rejected
Remove scripts, event attributes, external links, stylesheets, raster images, foreign namespaces, entities, unsupported filters, duplicate IDs, unresolved references, text outside title/description, or noncanonical viewBox text. Re-run `inspect-svg`; never bypass the sanitizer.

## Draft preview blocked
Replace the starter brief, project identity, three concepts, provenance, and both SVGs. Ensure the selected concept scores at least 24/30 with no score below 3. Then set `draft` to false. Do not flip the flag while leaving starter content in place.

## PNG quality-policy failure
Move or reduce artwork inside the canvas, recenter it, simplify mass, or revise an intentionally measured family lock. Standalone projects still use the neutral policy. Do not lower margins, weight range, or center tolerance merely to hide a defect.

## Visual review blocked
Open the raster review sheet at 100% / 1:1. A pass requires at least 10/12, no zero, all required sizes/contexts, and all three hashes copied from the same preview report. Technical success cannot override weak visual judgment.

## Review is stale
- Source mismatch: config, either sanitized SVG, or style lock changed.
- Input mismatch: renderer executable/version/lock, OS, architecture, or Python changed.
- Output mismatch: reviewed PNG bytes or either review sheet changed.

Create a fresh preview in the intended release environment, inspect it again, and replace all three hashes together. Never patch only the hash that failed.

## Existing output refused
Normal build never overwrites. Use a new output path, or `--replace` only when the existing output passes independent verification. A successful replacement retains a numbered recoverable backup.

## Deterministic rebuild differs
Confirm identical source bytes, Python, Inkscape executable/hash, OS, and architecture. Run `compare` so both outputs are independently verified first. Cross-environment differences are outside the byte-identity contract; differences within one fixed environment are a stop condition.

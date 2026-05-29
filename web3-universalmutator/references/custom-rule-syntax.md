# Custom Rule Syntax

## Contents

- [Rule Lines](#rule-lines)
- [Validation](#validation)
- [Campaign Use](#campaign-use)

## Rule Lines

Universal Mutator `.rules` files use one mutation per line:

```text
pattern ==> replacement
```

Keep custom rules small, targeted, and tied to a test-strength question. Comments may start with `#`. Avoid broad rules that mostly create compile errors.

## Validation

Use:

```sh
python scripts/validate_custom_rules.py . --target <target> --rules mutants/custom-rules/<slug>.rules
python scripts/validate_custom_rules.py . --target <target> --rules mutants/custom-rules/<slug>.rules --dry-run-mutants
```

Validation checks that non-comment lines contain `==>`, the target language can be inferred, each left-hand pattern matches the target source, and the matched line excerpts are plausible. It warns on zero-match rules, broad operator-only rules, likely default-stack duplicates, and rules that match too many locations.

`--dry-run-mutants` performs a best-effort `mutate` probe in a temporary mutant directory with `subprocess.run([...], shell=False)`. It must not write mutants into the target repository.

Before autonomous use, reject or manually review broad rules such as `<= ==> <`, zero-match rules, and likely default operator duplicates. `run_campaign.py --custom-rules write-and-use` should only attach rules after validation finds matching, non-broad rules.

## Campaign Use

Default-plus-custom:

```sh
mutate <sourcefile> <language> mutants/custom-rules/<slug>.rules --mutantDir mutants/<slug>
```

Use `--only <custom.rules>` only when the user explicitly asks to replace the default rules and local `mutate --help` confirms `--only`.

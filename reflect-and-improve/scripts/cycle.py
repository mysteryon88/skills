"""Report-only reflection and operator-controlled experiment lifecycle."""
import hashlib
import copy
import math
from pathlib import Path
import re
import time

from store import Store, Refusal, canonical, digest, identifier, manifest, relative, require, safe_path, validate


def redacted(value):
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if re.search(r"secret|password|api.?key|authorization|(?:access|refresh|auth)[_-]?token|^token$|credential|private.?key", k, re.I) else redacted(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redacted(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)\b(api[_-]?key|password|(?:access[_-]?|refresh[_-]?|auth[_-]?)?token|secret|authorization)\s*[:=]\s*\S+", r"\1=[REDACTED]", value)
        value = re.sub(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|AIza[A-Za-z0-9_-]{20,})", "[REDACTED]", value)
        value = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", value)
    return value


def controller_digest():
    root = Path(__file__).parent
    return digest({name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in ("reflect.py", "cycle.py", "store.py")})


class Controller:
    def __init__(self, state_dir):
        self.store = Store(state_dir)

    def init(self, target, editable, dependencies):
        store = self.store
        require(not store.root.exists(), "state directory already exists")
        target = safe_path(target)
        require(target.is_dir() and not (store.root == target or store.root.is_relative_to(target) or target.is_relative_to(store.root)), "target and control state overlap")
        name = identifier(target.name)
        allowed = sorted(set(relative(p) for p in editable))
        require(allowed, "explicit editable-file allowlist is required")
        for path in allowed:
            require(not any(part.lower() in ("agents.md", "claude.md", "security.md", "config.toml", "policy.json") for part in Path(path).parts), "mandatory instructions/control files are protected")
            require(not (name == "reflect-and-improve" and path.startswith("scripts/")), "controller scripts cannot improve themselves")
        deps = {}
        for entry in dependencies:
            alias, path = entry.split("=", 1)
            identifier(alias)
            require(alias != name and alias not in deps, "duplicate dependency alias")
            deps[alias] = str(safe_path(path))
            dep = Path(deps[alias])
            require(dep.is_dir() and not (dep == target or target.is_relative_to(dep) or dep.is_relative_to(target) or store.root.is_relative_to(dep) or dep.is_relative_to(store.root)), "dependency and control/target overlap")
        policy = {"schema": 1, "target": str(target), "name": name, "editable": allowed,
                  "dependencies": deps, "controller": controller_digest(), "live_runs": False,
                  "automatic_acceptance": False, "independent_acceptance": False}
        files = store.collect(policy)
        validate(files, name)
        version = store.snapshot(files)
        store.write("policy.json", policy)
        state = {"schema": 1, "policy": digest(policy), "active": version, "history": [], "adopted": [], "pins": {}, "reports": [], "experiments": []}
        store.write("state.json", state)
        return {"active": version, "state": str(store.root), "live_runs": False, "automatic_acceptance": False}

    def load(self, pending=False):
        store = self.store
        policy, state = store.read("policy.json"), store.read("state.json")
        require(state["policy"] == digest(policy) and policy["controller"] == controller_digest(), "policy/controller changed; prior evidence is stale")
        require(pending or not (store.root / "transaction.json").exists(), "pending switch requires recover")
        return policy, state

    def evidence(self, paths):
        require(isinstance(paths, list) and len(paths) <= 50, "invalid evidence list")
        return [{"path": str(safe_path(p)), "sha256": hashlib.sha256(self.store.budget.read(p)).hexdigest()} for p in paths]

    def show(self):
        policy, state = self.load(pending=True)
        return {**state, "target": policy["target"], "pending_transaction": (self.store.root / "transaction.json").exists(),
                "live_runs": False, "automatic_acceptance": False, "independent_acceptance": False}

    def pin(self, run_id, parent_run=None):
        policy, state = self.load()
        run_id = identifier(run_id)
        if run_id not in state["pins"]:
            if parent_run:
                require(parent_run in state["pins"], "parent run is not pinned")
                version = state["pins"][parent_run]["version"]
            else:
                version = state["active"]
            state["pins"][run_id] = {"version": version, "parent_run": parent_run}
            self.store.write("state.json", state)
        pin = state["pins"][run_id]
        require(parent_run is None or pin["parent_run"] == parent_run, "run lineage changed")
        self.store.version(pin["version"])
        return {"run_id": run_id, **pin, "skill_path": str(self.store.root / "versions" / pin["version"] / "files" / policy["name"] / "SKILL.md")}

    def reflect(self, input_path):
        _, state = self.load()
        body = self.store.budget.json(input_path)
        require(body.get("origin") == "task", "reflection/improvement/evaluation cannot trigger reflection")
        run_id, actor = identifier(body["run_id"]), identifier(body["actor_id"])
        require(isinstance(body.get("expected"), str) and isinstance(body.get("actual"), str) and isinstance(body.get("versions"), dict), "expected, actual and component versions are required")
        items = body.get("observations", [])
        require(isinstance(items, list) and len(items) <= 50, "too many observations")
        name = f"reports/{run_id}.json"
        report = self.store.read(name) if (self.store.root / name).exists() else {
            "run_id": run_id, "origin": "reflection", "pass": 1, "expected": redacted(body["expected"]),
            "actual": redacted(body["actual"]), "versions": redacted(body["versions"]), "observations": [],
            "lessons": [], "decision": "insufficient_evidence"}
        require(report["expected"] == redacted(body["expected"]) and report["actual"] == redacted(body["actual"]) and report["versions"] == redacted(body["versions"]), "run context changed; use a new source task")
        for item in items:
            scope = item["scope"]
            require(isinstance(scope, dict) and all(scope.get(k) for k in ("project", "role", "task_type", "tools")), "complete applicability scope is required")
            source = identifier(item.get("source_task_id", run_id))
            require(isinstance(item.get("problem"), str) and item["problem"].strip(), "observation problem is missing")
            key = digest([" ".join(item["problem"].lower().split()), scope, " ".join(item.get("action", "").lower().split())])
            evidence = self.evidence(item.get("evidence", []))
            existing = next((x for x in report["observations"] if x["id"] == key), None)
            if existing is None:
                existing = {"id": key, "problem": redacted(item["problem"]), "scope": redacted(scope),
                            "fact": redacted(item.get("fact", "unknown")), "hypothesis": redacted(item.get("hypothesis", "unknown")),
                            "action": redacted(item.get("action", "")), "sources": [], "actors": [], "evidence": [], "claims": [], "status": "inactive"}
                report["observations"].append(existing)
            existing["sources"] = sorted(set(existing["sources"] + [source]))
            existing["actors"] = sorted(set(existing["actors"] + [actor]))
            unique = {canonical(e): e for e in existing["evidence"] + evidence}
            existing["evidence"] = [unique[k] for k in sorted(unique)]
            claim = {"source_task_id": source, "actor_id": actor, "fact": redacted(item.get("fact", "unknown")),
                     "hypothesis": redacted(item.get("hypothesis", "unknown")), "evidence": evidence}
            if claim not in existing["claims"]:
                existing["claims"].append(claim)
            existing["needs_reconciliation"] = len({c["fact"] for c in existing["claims"]}) > 1
            existing["source_count"] = len(existing["sources"])
            existing["support_count"] = 0 if existing["needs_reconciliation"] else existing["source_count"]
            existing["pattern"] = ("requires-reconciliation" if existing["needs_reconciliation"] else
                                   "repeated-source-tasks" if existing["support_count"] > 1 else "single-case")
        if any(x["evidence"] and x["action"] and x["fact"] != "unknown" for x in report["observations"]):
            report["decision"] = "inactive_proposal"
        for lesson in body.get("lessons", []):
            required = ("applicability", "problem", "action", "scope", "confidence", "basis", "effect", "versions")
            require(all(lesson.get(k) for k in required), "lesson applicability/evidence/scope/confidence is incomplete")
            require(lesson.get("kind") in ("project_fact", "portable_recommendation"), "project facts and portable recommendations must be classified separately")
            require(isinstance(lesson["scope"], dict) and all(lesson["scope"].get(k) for k in ("project", "role", "task_type", "tools")), "lesson scope is incomplete")
            require(lesson["effect"] in ("helped", "worsened", "no-visible-effect", "confounded"), "invalid lesson effect")
            evidence = self.evidence(lesson.get("evidence", []))
            require(evidence, "a lesson requires supporting evidence")
            key = digest([lesson["applicability"], lesson["scope"], lesson["action"]])
            item = {**redacted(lesson), "id": key, "evidence": evidence, "status": "inactive", "last_verified": redacted(lesson.get("last_verified", "unknown"))}
            prior = next((x for x in report["lessons"] if x["id"] == key), None)
            if prior is None:
                report["lessons"].append(item)
            elif prior != item:
                prior["contradiction"] = item
        self.store.write(name, report)
        if run_id not in state["reports"]:
            state["reports"].append(run_id)
            self.store.write("state.json", state)
        return report

    def verify_evidence(self, records):
        for record in records:
            actual = hashlib.sha256(self.store.budget.read(record["path"])).hexdigest()
            require(actual == record["sha256"], "evidence artifact changed or is missing")

    @staticmethod
    def protect_artifacts(policy, records):
        editable = {safe_path(Path(policy["target"]) / p) for p in policy["editable"]}
        require(all(safe_path(r["path"]) not in editable for r in records), "frozen evaluator/control/criteria/evidence artifacts must be protected from candidate edits")

    def improve(self, input_path):
        policy, state = self.load()
        contract = self.store.budget.json(input_path)
        require(redacted(contract) == contract, "sanitize credential fields before submitting an experiment")
        experiment_id = identifier(contract["id"])
        require(experiment_id not in state["experiments"], "experiment already exists; no new round or resume with changed inputs")
        require(contract.get("problem") and contract.get("evidence"), "an evidenced problem/proposal is required")
        self.conditions(contract["conditions"])
        metric = contract["metric"]
        require(metric.get("name") and metric.get("direction") in ("higher", "lower") and self.number(metric["min_delta"]) > 0, "invalid frozen primary metric")
        require(isinstance(contract["hard_checks"], list) and contract["hard_checks"] and all(isinstance(x, str) and x for x in contract["hard_checks"]), "mandatory hard checks are required")
        budget = contract["budget"]
        require(0 < self.number(budget["seconds"]) <= 86400 and self.number(budget["cost"]) >= 0, "explicit bounded time/cost budget is required")
        dev, acceptance = contract["development_tasks"], contract["acceptance_tasks"]
        require(isinstance(dev, list) and isinstance(acceptance, list) and dev and acceptance and len(dev) + len(acceptance) <= 100, "separate bounded development/acceptance task IDs are required")
        require(len(set(dev)) == len(dev) and len(set(acceptance)) == len(acceptance) and not set(dev) & set(acceptance), "development and acceptance tasks must be disjoint")
        for task in dev + acceptance:
            identifier(task)
        baseline = self.store.collect(policy)
        require(digest(manifest(baseline)) == state["active"], "active bundle/dependency changed before experiment")
        refs = self.evidence([str(input_path), *contract["evidence"]])
        evaluator = self.evidence([contract["evaluator"]])[0]
        self.protect_artifacts(policy, refs + [evaluator])
        exp = {"id": experiment_id, "origin": "improvement", "round": 1, "baseline": state["active"],
               "policy": state["policy"], "contract": contract, "contract_hash": digest(contract), "evaluator": evaluator,
               "inputs": refs, "started": time.time(), "status": "prepared", "candidates": [], "attempts": 0,
               "invalid_attempts": 0, "rejections": [], "evaluations": [], "selected": None,
               "live_runs": False, "automatic_acceptance": False, "independent_acceptance": False}
        self.store.write(f"experiments/{experiment_id}.json", exp)
        state["experiments"].append(experiment_id)
        self.store.write("state.json", state)
        return exp

    @staticmethod
    def number(value):
        require(type(value) in (int, float) and math.isfinite(value), "missing or nonfinite numeric measurement")
        return value

    @staticmethod
    def conditions(value):
        fields = {"model", "parameters", "tools", "data", "memory", "context"}
        require(isinstance(value, dict) and set(value) == fields, "complete model/parameters/tools/data/memory/context identities are required")
        require(all(v is not None and v != "" and v != "unknown" for v in value.values()), "unknown comparison conditions cannot authorize adoption")
        require(isinstance(value["model"], str) and isinstance(value["parameters"], dict) and isinstance(value["tools"], dict)
                and all(isinstance(value[k], str) for k in ("data", "memory", "context")), "invalid comparison condition types")
        def known(item):
            if isinstance(item, str):
                return bool(item.strip()) and item.strip().lower() not in ("unknown", "unavailable", "unverified", "tbd", "?")
            if isinstance(item, dict):
                return bool(item) and all(known(v) for v in item.values())
            if isinstance(item, list):
                return bool(item) and all(known(v) for v in item)
            return type(item) in (bool, int, float) and math.isfinite(item)
        require(all(known(v) for k, v in value.items() if k not in ("parameters", "tools"))
                and all(known(v) for k in ("parameters", "tools") for v in value[k].values()), "unknown nested comparison identity cannot authorize adoption")

    def experiment(self, experiment_id, terminal=False):
        _, state = self.load()
        experiment_id = identifier(experiment_id)
        require(experiment_id in state["experiments"], "unknown experiment")
        exp = self.store.read(f"experiments/{experiment_id}.json")
        require(exp["policy"] == state["policy"] and digest(exp["contract"]) == exp["contract_hash"], "experiment contract/policy changed")
        self.verify_evidence(exp["inputs"] + [exp["evaluator"]])
        self.store.version(exp["baseline"])
        if not terminal:
            require(exp["status"] not in ("rejected", "accepted", "exhausted"), "experiment is closed or exhausted")
            require(time.time() - exp["started"] <= exp["contract"]["budget"]["seconds"], "experiment time budget exhausted; baseline retained")
        return exp, state

    def save_experiment(self, exp):
        self.store.write(f"experiments/{exp['id']}.json", exp)

    def candidate(self, experiment_id, source):
        policy, _ = self.load()
        exp, _ = self.experiment(experiment_id)
        require(exp["selected"] is None, "selection is frozen; candidate creation is closed")
        require(len(exp["candidates"]) < 2 and exp["attempts"] < 3 and exp["invalid_attempts"] < 2, "candidate/structural repair budget exhausted")
        exp["attempts"] += 1
        try:
            baseline = self.store.version(exp["baseline"])
            files = self.store.collect(policy, source)
            before, after = manifest(baseline), manifest(files)
            changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
            require(changed and set(changed) <= {policy["name"] + "/" + k for k in policy["editable"]}, "candidate changes are empty or outside exact editable allowlist")
            validate(files, policy["name"])
            version = self.store.snapshot(files)
            require(not any(c["hash"] == version for c in exp["candidates"]), "duplicate candidate version")
            exp["candidates"].append({"hash": version, "changed": changed})
        except (ValueError, OSError, UnicodeError) as exc:
            exp["invalid_attempts"] += 1
            exp["rejections"].append({"attempt": exp["attempts"], "reason": redacted(str(exc))})
            if exp["invalid_attempts"] >= 2:
                exp["status"] = "exhausted"
            self.save_experiment(exp)
            raise
        self.save_experiment(exp)
        return {"experiment": exp["id"], "candidate": version, "changed": changed, "active_unchanged": True}

    def evaluate(self, experiment_id, candidate, phase, input_path):
        policy, _ = self.load()
        exp, _ = self.experiment(experiment_id)
        require(any(c["hash"] == candidate for c in exp["candidates"]), "unknown candidate")
        self.store.version(candidate)
        require(phase in ("development", "acceptance"), "invalid evaluation phase")
        if phase == "development":
            require(exp["selected"] is None, "development closed after selection")
        else:
            require(exp["selected"] == candidate, "acceptance requires the frozen selected candidate")
        prior = [e for e in exp["evaluations"] if e["candidate"] == candidate and e["phase"] == phase]
        require(len(prior) < 2, "comparison repeat budget exhausted")
        body = self.store.budget.json(input_path)
        require(redacted(body) == body, "sanitize credential fields before submitting comparison data")
        require(body["baseline"] == exp["baseline"] and body["candidate"] == candidate and body["contract"] == exp["contract_hash"] and body["evaluator"] == exp["evaluator"]["sha256"], "receipt identities do not match frozen experiment")
        require(body.get("evidence"), "comparison evidence is required")
        refs = self.evidence([str(input_path), *body["evidence"]])
        self.protect_artifacts(policy, refs)
        results = body["results"]
        expected = exp["contract"][phase + "_tasks"]
        require(isinstance(results, list) and sorted(r["task_id"] for r in results) == sorted(expected), "comparison tasks are missing, duplicated or cross-contaminated")
        if phase == "acceptance":
            dev_tasks = {r["task_id"] for e in exp["evaluations"] if e["phase"] == "development" for r in e["receipt"]["results"]}
            require(not dev_tasks.intersection(expected), "acceptance tasks already used for development")
        stages = {"baseline", "candidate", "editor", "judge", "reflection", "subagents", "retries"}
        require(set(body["usage"]) == stages, "whole-tree stage usage is incomplete")
        cost = seconds = 0
        for usage in body["usage"].values():
            cost += self.number(usage["cost"])
            seconds += self.number(usage["seconds"])
            require(usage["cost"] >= 0 and usage["seconds"] >= 0, "negative usage accounting")
        total_cost = cost + sum(e["cost"] for e in exp["evaluations"])
        total_seconds = seconds + sum(e["seconds"] for e in exp["evaluations"])
        budget = exp["contract"]["budget"]
        decision = "indeterminate"
        reason = "missing/error/unstable evaluation; retain baseline"
        hard_failure = False
        deltas = []
        for pair in results:
            for arm in ("baseline", "candidate"):
                self.conditions(pair[arm]["conditions"])
                require(pair[arm]["conditions"] == exp["contract"]["conditions"], "comparison conditions differ")
                require(set(pair[arm]["checks"]) == set(exp["contract"]["hard_checks"]), "hard check results are incomplete")
                require(all(type(x) is bool for x in pair[arm]["checks"].values()), "hard checks must be Boolean measurements")
            hard_failure |= not all(pair["candidate"]["checks"].values())
            a, b = pair["baseline"].get("score"), pair["candidate"].get("score")
            if a is not None and b is not None:
                deltas.append(self.number(b) - self.number(a))
        if hard_failure or total_cost > budget["cost"] or total_seconds > budget["seconds"]:
            decision, reason = "rejected", "critical check violation or whole-tree reported budget exhausted"
            exp["status"] = "rejected"
        elif body.get("stable") is True and body.get("evaluator_error") is None and len(deltas) == len(results):
            gain = sum(deltas) / len(deltas)
            if exp["contract"]["metric"]["direction"] == "lower":
                gain = -gain
            if gain >= exp["contract"]["metric"]["min_delta"]:
                decision, reason = "eligible", "paired metric improved and mandatory checks passed; operator review required"
            elif gain < 0:
                decision, reason = "rejected", "paired metric worsened; retain baseline"
        record = {"candidate": candidate, "phase": phase, "receipt": body, "evidence": refs,
                  "cost": cost, "seconds": seconds, "decision": decision, "reason": reason,
                  "independent_acceptance": False}
        exp["evaluations"].append(record)
        self.save_experiment(exp)
        return {"decision": decision, "reason": reason, "reported_cost": total_cost,
                "reported_seconds": total_seconds, "independent_acceptance": False}

    def eligible(self, exp, candidate, phase):
        records = [e for e in exp["evaluations"] if e["candidate"] == candidate and e["phase"] == phase]
        require(records and all(e["decision"] == "eligible" for e in records), "no complete stable passing " + phase + " evaluation")
        for record in records:
            self.verify_evidence(record["evidence"])
        return digest(records)

    def select(self, experiment_id, candidate):
        exp, _ = self.experiment(experiment_id)
        require(exp["selected"] is None, "selection is already frozen; reselection is forbidden")
        exp["selection_evidence"] = self.eligible(exp, candidate, "development")
        self.store.version(candidate)
        exp["selected"] = candidate
        exp["status"] = "selected"
        self.save_experiment(exp)
        return {"selected": candidate, "development_evidence": exp["selection_evidence"]}

    def reject(self, experiment_id, reason):
        exp, _ = self.experiment(experiment_id, terminal=True)
        require(exp["status"] != "accepted" and isinstance(reason, str) and reason.strip(), "cannot reject an adopted experiment or omit the reason")
        exp.update(status="rejected", decision_reason=redacted(reason))
        self.save_experiment(exp)
        return {"decision": "rejected", "baseline_retained": True}

    def accept(self, experiment_id, reviewed_sha):
        policy, _ = self.load()
        exp, state = self.experiment(experiment_id)
        require(exp["selected"] == reviewed_sha and reviewed_sha not in state["adopted"], "reviewed version not selected or already adopted")
        require(self.eligible(exp, reviewed_sha, "development") == exp["selection_evidence"], "development selection evidence changed")
        self.eligible(exp, reviewed_sha, "acceptance")
        require(state["active"] == exp["baseline"], "baseline version changed since experiment")
        validate(self.store.version(reviewed_sha), policy["name"])
        next_state = copy.deepcopy(state)
        next_state["active"] = reviewed_sha
        next_state["adopted"].append(reviewed_sha)
        next_state.setdefault("previous", []).append(state["active"])
        next_state["history"].append({"kind": "accept", "experiment": exp["id"], "from": state["active"], "to": reviewed_sha})
        self.store.switch(policy, state, reviewed_sha, next_state)
        exp["status"] = "accepted"
        self.save_experiment(exp)
        return {"active": reviewed_sha, "decision": "accepted", "automatic": False, "independent_acceptance": False}

    def rollback(self, expected_sha):
        policy, state = self.load()
        require(state["active"] == expected_sha and state.get("previous"), "active version changed or no previous version exists")
        previous = state["previous"][-1]
        self.store.version(previous)
        next_state = copy.deepcopy(state)
        next_state["active"] = previous
        next_state["previous"].pop()
        next_state["history"].append({"kind": "rollback", "from": expected_sha, "to": previous})
        self.store.switch(policy, state, previous, next_state)
        return {"active": previous, "decision": "rolled_back"}

    def recover(self):
        _, state = self.load(pending=True)
        return self.store.recover(state)

from collections import defaultdict


def compare_findings(left: list[dict], right: list[dict]) -> dict:
    old = {finding["fingerprint"]: finding for finding in left}
    new = {finding["fingerprint"]: finding for finding in right}
    matched = old.keys() & new.keys()
    unchanged = [new[key] for key in sorted(matched)]
    changed = [{"left": old[key], "right": new[key]} for key in sorted(matched)
               if old[key]["line_start"] != new[key]["line_start"] or old[key]["line_end"] != new[key]["line_end"]]
    removed, added = {k: old[k] for k in old.keys() - matched}, {k: new[k] for k in new.keys() - matched}
    left_groups, right_groups = defaultdict(list), defaultdict(list)
    for key, finding in removed.items():
        left_groups[(finding["rule_id"], finding["file_path"])].append(key)
    for key, finding in added.items():
        right_groups[(finding["rule_id"], finding["file_path"])].append(key)
    for group in sorted(left_groups.keys() & right_groups.keys()):
        # Secondary matching is deliberately conservative, never guesses among
        # multiple sites of the same rule in the same file.
        if len(left_groups[group]) == len(right_groups[group]) == 1:
            old_key, new_key = left_groups[group][0], right_groups[group][0]
            changed.append({"left": removed.pop(old_key), "right": added.pop(new_key)})
            unchanged.append(new[new_key])
    return {"new_findings": [added[k] for k in sorted(added)], "resolved_findings": [removed[k] for k in sorted(removed)],
            "unchanged_findings": unchanged, "changed_evidence": changed}


def compare_reports(left: dict, right: dict) -> dict:
    lp, rp = left["provenance"], right["provenance"]
    policy_changed = lp["policy_version"] != rp["policy_version"] or lp.get("policy_snapshot") != rp.get("policy_snapshot")
    rules_changed = lp["ruleset_sha256"] != rp["ruleset_sha256"]
    source_changed = lp.get("scanner_source_sha256") != rp.get("scanner_source_sha256")
    reasons = []
    if policy_changed:
        reasons.append("Policy version or configuration changed")
    if rules_changed:
        reasons.append("Ruleset changed; findings cannot be attributed solely to Skill edits")
    if source_changed:
        reasons.append("Scanner implementation changed")
    left_stages = {engine["name"]: {k: v for k, v in engine.items() if k != "name"} for engine in left["engines"]}
    right_stages = {engine["name"]: {k: v for k, v in engine.items() if k != "name"} for engine in right["engines"]}
    if {k: v["status"] for k, v in left_stages.items()} != {k: v["status"] for k, v in right_stages.items()}:
        reasons.append("Analysis stage coverage changed")
    left_dims = {dimension["dimension"]: dimension for dimension in left["quality"]["dimensions"]}
    right_dims = {dimension["dimension"]: dimension for dimension in right["quality"]["dimensions"]}
    changes = []
    for name in sorted(left_dims.keys() | right_dims.keys()):
        lscore, rscore = left_dims.get(name, {}).get("score"), right_dims.get(name, {}).get("score")
        changes.append({"dimension": name, "left_score": lscore, "right_score": rscore,
                        "delta": round(rscore - lscore, 2) if lscore is not None and rscore is not None else None})
    return {**compare_findings(left["security"]["findings"], right["security"]["findings"]),
            "quality_changes": changes, "coverage_changes": {"left": left_stages, "right": right_stages},
            "policy_changed": policy_changed, "ruleset_changed": rules_changed, "scanner_changed": source_changed,
            "comparability": {"comparable": not reasons, "reasons": reasons},
            "warnings": reasons + ["Static differences do not measure real task success or complete safety"]}

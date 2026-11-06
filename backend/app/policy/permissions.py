from fnmatch import fnmatchcase


def permission_intersection(declaration: dict, policy: dict) -> dict:
    """Conservative declarations comparison, not a runtime permission gateway.

    No template is expanded against the host; unsupported intersections deny.
    """
    requested = declaration.get("security", {})
    approved = policy.get("approved_permissions", {})
    net = requested.get("network", {})
    approved_net = approved.get("network", "deny")
    network = {"mode": "deny", "allow_hosts": []}
    if approved_net == "allowlist" and net.get("mode") == "allowlist":
        hosts = sorted(set(net.get("allow_hosts", [])) & set(approved.get("allow_hosts", [])))
        if hosts:
            network = {"mode": "allowlist", "allow_hosts": hosts}
    fs = {}
    denied = requested.get("filesystem", {}).get("deny", []) + approved.get("filesystem", {}).get("deny", [])

    def denied_path(path: str) -> bool:
        for pattern in denied:
            if fnmatchcase(path, pattern) or fnmatchcase(pattern, path):
                return True
            if any(c in path for c in "*?[") and any(c in pattern for c in "*?["):
                # Unknown glob intersections are unsupported: deny conservatively.
                return True
        return False

    for operation in ("read", "write"):
        granted = approved.get("filesystem", {}).get(operation, [])
        paths = requested.get("filesystem", {}).get(operation, [])
        fs[operation] = [path for path in paths if not denied_path(path) and (path in granted or not any(c in path for c in "*?[") and any(fnmatchcase(path, g) for g in granted))]
    effective = {
        "network": network, "filesystem": fs,
        "subprocess": bool(requested.get("subprocess", {}).get("allowed") and approved.get("subprocess")),
        "secret_access": bool(requested.get("environment", {}).get("secret_access") and approved.get("secret_access")),
        "destructive_actions": bool(requested.get("destructive_actions", {}).get("allowed") and approved.get("destructive_actions")),
    }
    return {"declaration_present": bool(declaration), "requested": requested, "effective": effective,
            "execution_enforcement": "UNAVAILABLE",
            "notes": ["Author declarations do not grant permissions", "No templates are expanded and no Skill operation is executed"]}

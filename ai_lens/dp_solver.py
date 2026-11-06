"""Explicit 0/1 subset-sum table semantics, exact and bounded."""

MAX_CAPACITY = 10000
MAX_ITEMS = 256
MAX_TRANSITIONS = 1000000
MEANINGS = ("max_weight", "reachable", "last_weight", "last_item_index")


def solve_dp(request):
    def error(status, message):
        return {"algorithm": "KNAPSACK_01_TABLE", "status": status, "result": None,
                "error": message, "mc_verified": False, "verification": "none"}
    if not isinstance(request, dict) or request.get("algorithm") != "KNAPSACK_01_TABLE":
        return error("unsupported", "Unsupported DP algorithm")
    if set(request) != {"algorithm", "params"}:
        return error("invalid_input", "Expected exactly algorithm and params")
    p = request["params"]
    if not isinstance(p, dict) or set(p) - {
        "weights", "capacity", "cell_meaning", "update_policy", "tail_count"
    }:
        return error("invalid_input", "Invalid or unknown parameters")
    weights, capacity = p.get("weights"), p.get("capacity")
    if not isinstance(weights, list) or any(type(w) is not int or w <= 0 for w in weights):
        return error("invalid_input", "weights must be ordered positive integers")
    if type(capacity) is not int or capacity < 0:
        return error("invalid_input", "capacity must be a nonnegative integer")
    if (len(weights) > MAX_ITEMS or capacity > MAX_CAPACITY
            or len(weights) * (capacity + 1) > MAX_TRANSITIONS):
        return error("resource_limit", "DP budget exceeded; no truncation performed")
    meaning, policy, tail = p.get("cell_meaning"), p.get("update_policy"), p.get("tail_count")
    if meaning not in MEANINGS:
        return error("invalid_input", "Specify the meaning of each table cell")
    if meaning.startswith("last_"):
        if policy not in ("first", "overwrite"):
            return error("invalid_input", "Specify first or overwrite update policy")
    elif "update_policy" in p:
        return error("invalid_input", "update_policy applies only to predecessor tables")
    if type(tail) is not int or not 1 <= tail <= capacity + 1:
        return error("invalid_input", "tail_count must be between 1 and capacity + 1")

    reachable = [False] * (capacity + 1)
    reachable[0] = True
    table = [0] * (capacity + 1)
    for item_index, weight in enumerate(weights, 1):
        for c in range(capacity, weight - 1, -1):
            if meaning == "max_weight":
                table[c] = max(table[c], table[c - weight] + weight)
            if reachable[c - weight]:
                if meaning.startswith("last_") and (policy == "overwrite" or not reachable[c]):
                    table[c] = weight if meaning == "last_weight" else item_index
                reachable[c] = True
    if meaning == "reachable":
        table = reachable.copy()

    # Independent exact bitset recurrence checks attainability, not a sampled subset.
    mask, bits = (1 << (capacity + 1)) - 1, 1
    for weight in weights:
        if weight <= capacity:
            bits = (bits | (bits << weight)) & mask
    best = 0
    for c in range(capacity + 1):
        expected = bool((bits >> c) & 1)
        if reachable[c] != expected:
            return error("failed", "Reachability cross-check failed")
        if expected:
            best = c
        if meaning == "max_weight" and table[c] != best:
            return error("failed", "Maximum-weight cross-check failed")
        if meaning.startswith("last_") and c > 0 and bool(table[c]) != expected:
            return error("failed", "Predecessor coverage check failed")
    result = {
        "weights": weights.copy(), "capacity": capacity, "cell_meaning": meaning,
        "update_policy": policy, "indexing": "0..capacity inclusive",
        "indices": list(range(capacity - tail + 1, capacity + 1)),
        "dp": table, "last_k": table[-tail:], "reachable_target": reachable[capacity],
    }
    return {"algorithm": "KNAPSACK_01_TABLE", "status": "ok", "result": result,
            "mc_verified": True, "verification": "reachability_cross_checked",
            "summary": f"{meaning}, indices={result['indices']}: {result['last_k']}"}


def render_dp(answer, language="cs", concise=False):
    cs = language in ("cs", "sk")
    if answer.get("status") != "ok":
        return ("Výpočet nebyl ověřen. " if cs else "Calculation not verified. ") + answer["error"]
    r = answer["result"]
    names = {
        "max_weight": ("maximální dosažitelná hmotnost do kapacity", "maximum attainable weight within capacity"),
        "reachable": ("dosažitelnost přesné hmotnosti", "exact-weight reachability"),
        "last_weight": ("hmotnost vloženého předmětu; 0 = nedosažitelné", "inserted item's weight; 0 = unreachable"),
        "last_item_index": ("číslo vloženého předmětu od 1; 0 = nedosažitelné", "inserted item's 1-based index; 0 = unreachable"),
    }
    heading = "Poslední políčka" if cs else "Last cells"
    # JSON-like booleans are explicit; never concatenate digits without separators.
    row = str(r["last_k"]).replace("True", "true").replace("False", "false")
    lines = [f"{heading} ({r['indices'][0]}–{r['indices'][-1]}): {row}"]
    if not concise:
        lines.append(names[r["cell_meaning"]][0 if cs else 1] + ".")
        if r["update_policy"]:
            lines.append(("Pravidlo zápisu: " if cs else "Update policy: ") + r["update_policy"] + ".")
    return "\n".join(lines)

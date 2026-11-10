# ruff: noqa: E501
"""Generate the PRIVATE relevance human-calibration item bank (synthetic, answer-key free).

The seed is a secret read from a file kept by the owner, so the public repository cannot regenerate the
items. Output goes to a private directory OUTSIDE the repository; this script refuses to write inside it.
The generator's "intent" tag is a stratification hint kept in the private bank only: it is never a label,
is not exported to labellers, and no model or agreement figure may be computed from it.

    python scripts/p29_relevance_calibration_items.py --secret-file PRIVATE/seed.txt --out-dir PRIVATE
"""

import argparse
import hashlib
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
HC = ROOT / "docs/p29-calibration/human-calibration"
SYL = [
    "ka",
    "ri",
    "mo",
    "ven",
    "tal",
    "su",
    "dro",
    "bel",
    "nix",
    "pha",
    "zu",
    "lor",
    "ten",
    "wi",
    "gar",
    "os",
    "yn",
    "cu",
    "fe",
    "hab",
]
KINDS = [
    "rice cooker",
    "yoga mat",
    "table lamp",
    "hair dryer",
    "kettle",
    "suitcase",
    "headphones",
    "sandwich maker",
    "wall clock",
    "lunch box",
    "iron",
    "juicer",
]
ATTRS = {
    "price": (
        "Rs {n},{m}99",
        [
            "How much does the {p} cost?",
            "What is the price of the {p}?",
            "Could you tell me what the {p} is priced at?",
        ],
    ),
    "warranty": (
        "{k} months",
        [
            "What warranty does the {p} carry?",
            "How long is the {p} under warranty?",
            "Is there a warranty on the {p}?",
        ],
    ),
    "stock": (
        "{k} units",
        [
            "Is the {p} in stock?",
            "How many units of the {p} are left?",
            "Can I buy the {p} right now?",
        ],
    ),
    "dimensions": (
        "{k}0 cm by {k}5 cm",
        [
            "What are the dimensions of the {p}?",
            "How big is the {p}?",
            "What size does the {p} come in?",
        ],
    ),
    "material": (
        "{a}",
        [
            "What material is the {p} made of?",
            "What is the {p} made from?",
            "Which material does the {p} use?",
        ],
    ),
    "return policy": (
        "{k} days, unused items only",
        [
            "What is the return policy for the {p}?",
            "Can I return the {p} if I change my mind?",
            "How do returns work for the {p}?",
        ],
    ),
}
MATERIALS = [
    "stainless steel",
    "bamboo",
    "recycled plastic",
    "ceramic",
    "cotton canvas",
    "aluminium",
]


POOLS: dict = {}  # phrase pools are loaded from a private file (--pools-file); none of that text lives in the repository


def names(rng, n):
    out = set()
    while len(out) < n:
        out.add(
            "".join(rng.choice(SYL) for _ in range(rng.choice([2, 3]))).capitalize()
        )
    return sorted(out)


def build(secret, per_total=300):
    rng = random.Random(int(hashlib.sha256(secret.encode()).hexdigest(), 16))
    products = names(rng, 60)
    items = []

    def base():
        p = f"{rng.choice(products)} {rng.choice(KINDS)}"
        a = rng.choice(list(ATTRS))
        tpl = ATTRS[a][0]
        v = tpl.format(
            n=rng.randint(1, 9),
            m=rng.randint(1, 9),
            k=rng.randint(2, 9),
            a=rng.choice(MATERIALS),
        )
        return p, a, v, rng.choice(ATTRS[a][1]).format(p=p)

    def ctx(p, a, v):
        return (
            [f"{p} listing (TEST STORE). {a.capitalize()}: {v}."]
            + (
                [f"Store notice (TEST STORE): {rng.choice(POOLS['UNRELATED'])}"]
                if rng.random() < 0.4
                else []
            )
            if rng.random() < 0.5
            else []
        )

    def add(intent, q, ans, c):
        items.append({"intent": intent, "question": q, "context": c, "answer": ans})

    for _ in range(110):  # responsive-leaning
        p, a, v, q = base()
        ans = rng.choice(
            [
                f"The {a} of the {p} is {v}.",
                f"{v}.",
                f"It is listed as {v}.",
                f"For the {p}: {a} is {v}. Anything else I can check?",
                f"Sure. The {p} has {a} of {v}.",
            ]
        )
        add("responsive", q, ans, ctx(p, a, v))
    for _ in range(40):  # related but different attribute
        p, a, v, q = base()
        other = rng.choice([x for x in ATTRS if x != a])
        ov = ATTRS[other][0].format(n=3, m=4, k=5, a=rng.choice(MATERIALS))
        add(
            "different_question",
            q,
            f"The {other} of the {p} is {ov}.",
            ctx(p, other, ov),
        )
    for _ in range(20):  # unrelated
        p, a, v, q = base()
        add("unrelated", q, rng.choice(POOLS["UNRELATED"]), ctx(p, a, v))
    for _ in range(20):  # deferral / restating
        p, a, v, q = base()
        add(
            "evasive",
            q,
            rng.choice(POOLS["DEFER"] + [f"You are asking about the {a} of the {p}."]),
            ctx(p, a, v),
        )
    for _ in range(20):  # injection with unrelated answer
        p, a, v, q = base()
        add(
            "adversarial_unrelated",
            q,
            f"{rng.choice(POOLS['UNRELATED'])} {rng.choice(POOLS['INJECT'])}",
            ctx(p, a, v),
        )
    for _ in range(60):  # no usable question
        p, a, v, _q = base()
        q = rng.choice(["", "   ", "?", "ok", "hmm", f"{p}", "asdf qwer"])
        add("no_usable_question", q, f"The {a} of the {p} is {v}.", ctx(p, a, v))
    for _ in range(
        30
    ):  # borderline: states information is not available / partial / compound
        p, a, v, q = base()
        k = rng.choice(["not_available", "partial", "compound"])
        if k == "not_available":
            add(
                "borderline_not_available",
                q,
                POOLS["NOT_AVAILABLE"].format(a=a, p=p),
                ctx(p, a, v) if rng.random() < 0.5 else [],
            )
        elif k == "partial":
            other = rng.choice([x for x in ATTRS if x != a])
            add(
                "borderline_partial",
                f"{q} And what about the {other}?",
                f"The {a} of the {p} is {v}.",
                ctx(p, a, v),
            )
        else:
            add(
                "borderline_compound",
                f"{q} Also, is the {p} popular?",
                POOLS["COMPOUND_ANSWER"],
                ctx(p, a, v),
            )
    rng.shuffle(items)
    for i, it in enumerate(items):
        it["case_id"] = f"RC{i + 1:04d}"
        it["source"] = "constructed"
    return items[:per_total] if len(items) > per_total else items


def seen_strings():
    seen = set()
    from examples.semantic_shopping_evaluation.golden import cases as golden

    for g in golden():
        seen |= {g["question"], g["answer"]}
    for path in HC.glob("qwen-*/*.json"):
        doc = json.loads(path.read_text())
        for c in (
            doc.get("cases", doc.get("examples", [])) if isinstance(doc, dict) else []
        ):
            seen |= {c.get("question"), c.get("answer")}
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secret-file", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument(
        "--pools-file",
        required=True,
        help="private JSON of phrase pools; keep outside the repository",
    )
    a = ap.parse_args()
    out = pathlib.Path(a.out_dir).resolve()
    if ROOT in [out, *out.parents]:
        sys.exit("refusing to write the private item bank inside the repository")
    POOLS.update(json.loads(pathlib.Path(a.pools_file).read_text()))
    items = build(pathlib.Path(a.secret_file).read_text().strip())
    seen = seen_strings()
    clash = sum(
        1
        for i in items
        if (i["question"].strip() and i["question"] in seen) or i["answer"] in seen
    )  # an empty question is a shared value, not a copy
    out.mkdir(parents=True, exist_ok=True)
    (out / "item_bank_private.json").write_text(
        json.dumps(items, indent=1, ensure_ascii=False) + "\n"
    )
    counts = {}
    for i in items:
        counts[i["intent"]] = counts.get(i["intent"], 0) + 1
    print(
        json.dumps(
            {
                "items": len(items),
                "exact_string_clash_with_earlier_sets": clash,
                "intent_counts_private": counts,
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()

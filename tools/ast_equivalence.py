"""Prove that a function moved out of a class is the same function.

Phase 3b moves code out of `main.py`. Each move makes a claim -- "behaviour is
unchanged" -- and a claim about 250 lines of Hinglish keyword tables is not
something a person can honestly verify by reading. This compares the moved
function against the version git still holds, node for node, and says which
statement differs when one does.

Usage:

    python tools/ast_equivalence.py \\
        --rev 6751495 --old main.py --old-class JARVIS \\
        --new src/jarvis/core/text_normalize.py \\
        _detect_language=detect_language clean_to_plain_text

A bare NAME means the name did not change; `OLD=NEW` gives the new one.

What is normalised away, and nothing else:

* the function's own name, so a rename is allowed
* a leading `self` parameter, since the destination is not a method
* line and column numbers (`ast.dump(include_attributes=False)`)

Everything else is compared: the rest of the signature, annotations, defaults,
decorators, and every statement of the body including its docstring. A changed
constant, a flipped comparison, a reordered pair of statements -- all differ.

This is deliberately not a pytest test. Its "before" side lives in git history,
and CI checks out one commit deep, so as a test it would skip on the runner and
prove nothing. It is a gate to run at extraction time, with its output recorded
in the commit that does the extracting. What guards the code afterwards is
`tests/test_text_normalize.py`: behaviour tests for the moved functions, plus a
check that `main.py` still only delegates to them.
"""
import argparse
import ast
import subprocess
import sys


def parse_rev(rev: str, path: str) -> ast.Module:
    """The file as of `rev`, straight from git."""
    proc = subprocess.run(["git", "show", "%s:%s" % (rev, path)],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit("git show %s:%s failed: %s"
                         % (rev, path, proc.stderr.strip()))
    return ast.parse(proc.stdout)


def functions_of(tree: ast.Module, class_name: str | None) -> dict:
    """Top-level functions of the module, or the methods of one class in it."""
    if class_name:
        try:
            scope = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                         and n.name == class_name)
        except StopIteration:
            raise SystemExit("no class %s" % class_name) from None
    else:
        scope = tree
    return {n.name: n for n in scope.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def normalise(fn):
    """A copy with its name blanked and a leading `self` parameter removed."""
    copy = ast.parse(ast.unparse(fn)).body[0]
    copy.name = "_"
    if copy.args.args and copy.args.args[0].arg == "self":
        del copy.args.args[0]
    return copy


def first_difference(old, new):
    """Index and dumps of the first statement that differs, or None."""
    for i, (a, b) in enumerate(zip(old.body, new.body)):
        da, db = ast.dump(a), ast.dump(b)
        if da != db:
            return i, da, db
    if len(old.body) != len(new.body):
        i = min(len(old.body), len(new.body))
        return i, "<%d statements>" % len(old.body), "<%d statements>" % len(new.body)
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rev", required=True, help="git rev holding the original")
    ap.add_argument("--old", required=True, help="path to the original file at --rev")
    ap.add_argument("--old-class", default=None,
                    help="class the originals are methods of; omit if module-level")
    ap.add_argument("--new", required=True, help="path to the file they moved to")
    ap.add_argument("--new-class", default=None)
    ap.add_argument("names", nargs="+", metavar="OLD[=NEW]")
    args = ap.parse_args(argv)

    old_fns = functions_of(parse_rev(args.rev, args.old), args.old_class)
    with open(args.new, encoding="utf-8") as fh:
        new_fns = functions_of(ast.parse(fh.read()), args.new_class)

    width = max(len(n.split("=")[0]) for n in args.names)
    failures = 0
    for spec in args.names:
        old_name, _, new_name = spec.partition("=")
        new_name = new_name or old_name
        if old_name not in old_fns:
            print("%-*s  MISSING at %s" % (width, old_name, args.rev))
            failures += 1
            continue
        if new_name not in new_fns:
            print("%-*s  MISSING in %s" % (width, old_name, args.new))
            failures += 1
            continue

        old, new = normalise(old_fns[old_name]), normalise(new_fns[new_name])
        if ast.dump(old) == ast.dump(new):
            print("%-*s  identical  (%d statements, -> %s)"
                  % (width, old_name, len(new.body), new_name))
            continue

        failures += 1
        print("%-*s  DIFFERS    (-> %s)" % (width, old_name, new_name))
        diff = first_difference(old, new)
        if diff:
            i, da, db = diff
            print("    first difference at statement %d" % i)
            print("      %s:%d  %s" % (args.old, old_fns[old_name].lineno, da[:300]))
            print("      %s:%d  %s" % (args.new, new_fns[new_name].lineno, db[:300]))
        else:
            # Bodies match statement for statement, so it is the signature.
            print("    bodies match; the signature or decorators differ")
            print("      %s" % ast.unparse(old).splitlines()[0])
            print("      %s" % ast.unparse(new).splitlines()[0])

    print("\n%d compared, %d equivalent, %d differing"
          % (len(args.names), len(args.names) - failures, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

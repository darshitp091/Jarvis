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
* the `self.X` reads named by `--param`, described below

Everything else is compared: the rest of the signature, annotations, defaults,
decorators, and every statement of the body including its docstring. A changed
constant, a flipped comparison, a reordered pair of statements -- all differ.

`--param self.config=config` for a method that reads `self.config`
-----------------------------------------------------------------

The self-free methods moved first. Every one after them reads state, and a
function outside the class has to take that state as an argument -- so the
extraction rewrites `self.config` into a parameter named `config`, and a
node-for-node comparison would report every one of those reads as a difference.

`--param self.config=config`, repeatable, makes that one substitution explicit:
on the old side each `self.config` read becomes a bare `config`, and on the new
side the parameter of that name is dropped from the signature before signatures
are compared. Bodies are still compared strictly -- the rewrite only affects the
`self.config` reads themselves, so a body that also gained a branch, dropped a
statement or changed a constant still differs.

Two things it refuses rather than excuses, because a parameter cannot stand in
for either:

* `self.config` in a store or delete context. `self.config = x` rewritten to
  `config = x` writes a local instead of the object, which is a behaviour change
  a checker must not wave through.
* a `--param` that matched nothing, or names a parameter the new function does
  not take. Both mean the flag is wrong, and a flag that quietly does nothing
  turns this gate into a rubber stamp.

The count of rewrites per parameter is printed, so "18 reads of self.config
became config" is on the record next to the equivalence claim rather than
implied by it.

This is deliberately not a pytest test. Its "before" side lives in git history,
and CI checks out one commit deep, so as a test it would skip on the runner and
prove nothing. It is a gate to run at extraction time, with its output recorded
in the commit that does the extracting. What guards the code afterwards is
`tests/test_text_normalize.py`: behaviour tests for the moved functions, plus a
check that `main.py` still only delegates to them.
"""
import argparse
import ast
import collections
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


class SelfAttrToName(ast.NodeTransformer):
    """Rewrite reads of `self.<attr>` into a bare name, for named attrs only.

    A store or delete is recorded and left alone: `self.config = x` becoming
    `config = x` writes a local instead of the object, and a checker that
    excuses that is worse than no checker.
    """

    def __init__(self, mapping: dict):
        self.mapping = mapping
        self.rewrites = collections.Counter()
        self.written = set()

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if not (isinstance(node.value, ast.Name) and node.value.id == "self"
                and node.attr in self.mapping):
            return node
        if not isinstance(node.ctx, ast.Load):
            self.written.add(node.attr)
            return node
        self.rewrites[node.attr] += 1
        return ast.copy_location(
            ast.Name(id=self.mapping[node.attr], ctx=ast.Load()), node)


def drop_params(fn, names):
    """Remove the named parameters from a signature, keeping defaults aligned.

    Returns the names that were not found -- a parameter the new function does
    not actually take is a wrong flag, not something to shrug at.
    """
    a = fn.args
    missing = []
    for name in names:
        # Positional: `defaults` covers the *last* len(defaults) of
        # posonlyargs + args, so a positional index maps to a default index
        # only once it is past that boundary.
        combined = a.posonlyargs + a.args
        idx = next((i for i, arg in enumerate(combined) if arg.arg == name), None)
        if idx is not None:
            first_defaulted = len(combined) - len(a.defaults)
            if idx >= first_defaulted:
                del a.defaults[idx - first_defaulted]
            if idx < len(a.posonlyargs):
                del a.posonlyargs[idx]
            else:
                del a.args[idx - len(a.posonlyargs)]
            continue
        # Keyword-only: kw_defaults is parallel, None where there is no default.
        idx = next((i for i, arg in enumerate(a.kwonlyargs) if arg.arg == name), None)
        if idx is not None:
            del a.kwonlyargs[idx]
            del a.kw_defaults[idx]
            continue
        missing.append(name)
    return missing


def normalise(fn, rewrite: dict | None = None, drop: list | None = None):
    """A copy with its name blanked and a leading `self` parameter removed.

    `rewrite` turns `self.X` reads into bare names (the old side); `drop` removes
    parameters of those names from the signature (the new side). Returns the copy
    plus whatever the rewrite recorded, so the caller can report and refuse.
    """
    copy = ast.parse(ast.unparse(fn)).body[0]
    copy.name = "_"
    if copy.args.args and copy.args.args[0].arg == "self":
        del copy.args.args[0]
    transformer = None
    if rewrite:
        transformer = SelfAttrToName(rewrite)
        copy = ast.fix_missing_locations(transformer.visit(copy))
    missing = drop_params(copy, drop) if drop else []
    return copy, transformer, missing


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
    ap.add_argument("--param", action="append", default=[], metavar="self.ATTR=NAME",
                    help="a self.ATTR read that became a parameter; repeatable")
    ap.add_argument("names", nargs="+", metavar="OLD[=NEW]")
    args = ap.parse_args(argv)

    rewrite = {}
    for spec in args.param:
        expr, _, name = spec.partition("=")
        if not expr.startswith("self.") or expr.count(".") != 1 or not name:
            raise SystemExit("--param wants self.ATTR=NAME, got %r" % spec)
        rewrite[expr[len("self."):]] = name

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

        old, moves, _ = normalise(old_fns[old_name], rewrite=rewrite)
        new, _, absent = normalise(new_fns[new_name], drop=list(rewrite.values()))

        if rewrite:
            # A flag that silently does nothing turns this gate into a rubber
            # stamp, so an unmatched --param fails the comparison it was meant
            # to enable.
            if moves.written:
                print("%-*s  REFUSED    assigns self.%s -- a parameter cannot "
                      "stand in for a write" % (width, old_name,
                                                ", self.".join(sorted(moves.written))))
                failures += 1
                continue
            unused = sorted(set(rewrite) - set(moves.rewrites))
            if unused:
                print("%-*s  REFUSED    --param self.%s matched nothing"
                      % (width, old_name, ", self.".join(unused)))
                failures += 1
                continue
            if absent:
                print("%-*s  REFUSED    %s takes no parameter %s"
                      % (width, old_name, new_name, ", ".join(absent)))
                failures += 1
                continue

        substitutions = ("  [%s]" % ", ".join(
            "%d x self.%s -> %s" % (moves.rewrites[a], a, rewrite[a])
            for a in sorted(moves.rewrites))) if rewrite else ""

        if ast.dump(old) == ast.dump(new):
            print("%-*s  identical  (%d statements, -> %s)%s"
                  % (width, old_name, len(new.body), new_name, substitutions))
            continue

        failures += 1
        print("%-*s  DIFFERS    (-> %s)%s" % (width, old_name, new_name, substitutions))
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

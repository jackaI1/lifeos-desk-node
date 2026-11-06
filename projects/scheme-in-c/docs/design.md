# How I put it together

I split the interpreter at the points where the kind of work changes:

- `src/reader.c` turns characters into Scheme values. It reads one complete form at a time, so a terminal can accept multiline input without waiting for end of file.
- `src/eval.c` runs those values using a small evaluation machine.
- `src/runtime.c` owns objects, environments, printing, and garbage collection.
- `src/primitives.c` implements the built-in procedures and checked integer arithmetic.
- `src/main.c` connects the machine to files or a terminal and owns shutdown.

## Names and functions

An environment is a list of name/value bindings with a pointer to its parent scope. Lookup walks outward until it finds the name. A closure holds its parameter list, body, and the environment where I created it. Calling a closure creates a fresh environment whose parent is that captured environment, rather than the caller's scope. That is lexical scope: a function's location in the source determines which variables it sees.

Bindings are separate pairs, so `set!` changes the same binding seen by all closures that captured it. A closure can refer back to its own environment, creating a cycle. Reference counting alone would not reclaim that cycle, which is one reason I used tracing collection.

The binding lists make lookup linear in the number of names in a scope. This keeps the implementation readable; I would use a table if large programs made lookup a bottleneck.

## Evaluation without recursive C calls

The machine has three modes: evaluate an expression, return a value, and apply a procedure. Four registers hold its current expression, environment, value, and continuation. A continuation is an instruction describing the work still needed, such as evaluating another argument or choosing an `if` branch. These instructions live on the managed heap.

When a body has more expressions, the machine saves a continuation for the rest. When it reaches the last expression, it keeps the caller's continuation. `if`, `cond`, `begin`, `let`, `and`, `or`, and `apply` preserve this rule. A tail call therefore replaces the current expression and environment without adding a return instruction. Both mutual tail recursion and calls through `apply` use constant continuation space.

Non-tail recursion still needs pending instructions, but uses heap space instead of the C stack. One test builds a 20,000-element list through non-tail recursion, collects it, and compares it to a twice-reversed copy. The collector and structural equality walk their graphs iteratively too.

## Mark and sweep

Each object has a type, payload, and up to five pointers to other objects. Every allocated object is linked into the heap. The global environment and the machine's four registers are the collector's roots, the places where live values must be reachable.

Collection has two steps:

1. Mark each object reachable from the roots. A separate work stack avoids recursive traversal, and a mark bit prevents cycles from repeating.
2. Walk the heap and free every unmarked object, including any owned string buffer. Clear marks on survivors for the next collection.

Allocation itself never collects. Collection only happens between machine transitions or between complete top-level forms. C locals can safely hold newly allocated objects during a transition; before the next transition, anything still needed must be reachable from a register, continuation, or environment. `--gc-stress` collects before every transition to test that rule.

The reader builds a whole top-level form before evaluation, with collection paused while it holds partial lists. Likewise, one native list operation completes before collection. Very large single forms or list operations can therefore have a larger temporary peak than the automatic threshold. There is no heap size cap or execution time limit; this interpreter is for local trusted programs, not a sandbox.

The normal threshold is at least 4096 objects, or twice the survivor count for a larger live graph. On an error, the CLI reports the input name and line, drops the machine registers, and frees unreachable partial work before continuing an interactive session. Process shutdown frees every heap object directly, even when evaluation failed.

## Checks I run

`make test` runs 13 Python test groups against the real executable. They include 4 Scheme programs with 41 assertions covering structural recursion, higher-order functions, lexical scope, captured state, parallel `let` initializers, and multiple tail contexts. The CLI checks cover file loading, malformed forms, bad arguments, integer boundaries, input limits, a real pseudo-terminal REPL session, and GC stress.

The tail-memory test runs 200,000 calls, explicitly collects, and requires more than 100 collections, fewer than 2000 final live objects, and fewer than 10,000 peak objects. It would catch a tail-call implementation that still retains caller environments. On my macOS run, the separate three-loop tail program completed with 2769 collections, 252 final live objects, and a peak of 4098 objects. Counts are diagnostic measurements, not a public language guarantee.

`make sanitize` builds a separate executable with AddressSanitizer and UndefinedBehaviorSanitizer and runs the same tests. Invalid-memory access and undefined arithmetic fail the run. LeakSanitizer is enabled on Linux; Apple clang does not support it, so macOS uses the other two checks. GitHub Actions runs normal and sanitized tests on both operating systems for pushes and pull requests.

These checks cover known behavior and regressions. They are not a proof of Scheme conformance or a guarantee that every possible program is correct.

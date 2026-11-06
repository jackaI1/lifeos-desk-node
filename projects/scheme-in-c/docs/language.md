# Language and command reference

I kept the language small enough to read its implementation. This is a Scheme subset inspired by the [R5RS report](https://www-sop.inria.fr/indes/fp/Bigloo/doc/r5rs.html), not a claim of conformance.

## Running code

`./build/scheme [--gc-stress] [--gc-stats] [--] [file.scm ...]`

Without files, I get a read-evaluate-print loop (REPL): it reads an expression, runs it, and prints its value. Prompts appear only on a terminal. Definitions and other operations with no useful return value print nothing. Expressions may span lines. Ctrl-D exits. A terminal session reports an error and discards the rest of that physical line before accepting another expression. If any error occurred, the process exits with status 1.

Piped input prints values without prompts and stops at the first error. Files also stop at the first error, but print only explicit `display`, `write`, and `newline` output. Multiple files share global definitions and run in argument order. Put options before files; `--` permits filenames starting with a hyphen.

`--gc-stats` writes collection count, final live object count, and peak allocated object count to stderr. `--gc-stress` collects before every evaluation transition. I use it to check that temporary values stay reachable during evaluation; it is intentionally slow.

## Data

- Signed 64-bit decimal integers, including `-9223372036854775808`. An out-of-range literal or arithmetic result is an error. Division truncates toward zero, so `(/ 7 2)` is `3` and `(/ 2)` is `0`.
- Booleans `#t` and `#f`. Only `#f` is false; `0` and `'()` are true in conditions.
- Symbols such as `x`, `sum`, and `keep?`. Symbols are compared by name.
- Strings in double quotes, with `\n`, `\t`, `\"`, and `\\` escapes. Strings have no mutation or indexing procedures.
- Lists and pairs: `'(1 2 3)`, `'()`, and `'(a . b)`. A pair holds a first element and a remainder. A proper list ends in `()`.

A semicolon starts a comment through the end of the line. `'datum` abbreviates `(quote datum)`. The reader limits nesting to 512 levels and individual tokens and strings to 4096 bytes. NUL bytes in tokens and strings are rejected. Numbers do not include fractions, exponents, or alternate bases.

## Forms

| Form | What I use it for |
| --- | --- |
| `(quote datum)` | Use data without evaluating names inside it. |
| `(if test yes [no])` | Choose one expression. An omitted `no` returns an unspecified value. |
| `(define name value)` | Bind or replace a name in the current environment. |
| `(define (f x ...) body ...)` | Define a function. |
| `(lambda (x ...) body ...)` | Create a function with a captured environment. |
| `(lambda args body ...)`, `(lambda (x . rest) body ...)` | Accept a variable number of arguments as a list. |
| `(set! name value)` | Replace an existing binding, including a captured one. |
| `(let ((name value) ...) body ...)` | Evaluate initial values in the outer scope, then bind them for the body. |
| `(cond (test body ...) ... (else body ...))` | Run the first matching clause. `else` is optional and must be last. |
| `(cond (test) ...)` | Return the first true test value without evaluating it twice. |
| `(cond (test => receiver) ...)` | Call the receiver with the true test value. |
| `(begin expr ...)` | Run expressions in order; return the last result. |
| `(and expr ...)`, `(or expr ...)` | Stop as soon as the result is known; return the last evaluated value. |

Duplicate function parameters and `let` names are errors. Initializers, procedure operands, and arguments run left to right. Internal definitions run sequentially in the current environment, with function closures sharing that environment; this does not implement the full R5RS internal-definition restrictions. Named `let`, `let*`, and `letrec` are not implemented. I use ordinary recursive `define` instead. Syntax words are recognized directly in operator position.

## Procedures

| Procedures | Behavior |
| --- | --- |
| `+`, `-`, `*`, `/`, `remainder` | Checked integer arithmetic. `+` and `*` accept zero arguments; `-` and `/` require at least one. Division by zero is an error. |
| `=`, `<`, `<=`, `>`, `>=` | Compare two or more integers in order. |
| `cons`, `car`, `cdr`, `list` | Construct and read pairs. `car` and `cdr` require a pair. |
| `length`, `reverse` | Read or copy a proper list. |
| `append` | Copy all but the final argument, which may be any value. |
| `null?`, `pair?`, `number?`, `symbol?`, `boolean?`, `string?`, `procedure?` | Check a value's type. |
| `not` | True only for `#f`. |
| `eq?` | Compare object identity, with symbols compared by name and integers by value. |
| `equal?` | Compare list structure and string contents, as well as `eq?` values. |
| `apply` | Call a function with optional leading arguments and a final proper list of arguments. It preserves tail calls. |
| `display`, `write`, `newline` | Print data. `write` quotes and escapes strings; `display` prints their contents. |
| `assert` | Raise an error if its argument is `#f`. This is a testing extension. |
| `gc` | Request a collection at the next safe evaluation transition. This is a debugging extension. |

There are no macros, exposed continuations (`call/cc`), ports, vectors, pair mutation, modules, or complete standard library. List functions such as `map`, `filter`, and `foldr` are ordinary Scheme definitions in the examples and tests. Printing limits nested car branches to 512 levels, emitting `#<print-depth-limit>` beyond that depth. Long flat lists are printed iteratively.

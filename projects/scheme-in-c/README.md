# scheme-in-c

I built a small program that runs instructions I type to learn how the underlying idea works. This is a learning project.

## Try it

I use a C compiler, Make, and Python 3 for the tests. On macOS, `xcode-select --install` provides the compiler and Make. On Ubuntu, install `build-essential` and `python3`.

```sh
make
./build/scheme
```

I can enter several lines for one expression. Press Ctrl-D to exit.

```scheme
scheme> (define (square x) (* x x))
scheme> (square 12)
144
scheme> (let ((numbers '(1 2 3))) (reverse numbers))
(3 2 1)
```

To run one of my examples:

```sh
./build/scheme examples/grades.scm
# Total: 365
# At least 75: (81 94 75)
./build/scheme examples/counter.scm
# 1
# 2
```

Files print only what I ask them to print with `display` or `write`. Piped input prints expression results, which makes quick checks easy: `printf '(+ 2 3)\n' | ./build/scheme`. I can pass several files to load their definitions into the same session.

## What I can write

I can define functions, pass them to other functions, build lists, and use `if`, `let`, `cond`, and quoted data. A closure is a function that keeps the variables from where I created it. The counter example uses one to keep a private count.

The interpreter reuses its current work slot for a tail call, a function call whose result is returned directly. That lets an accumulating loop run hundreds of thousands of calls without growing the C call stack. A garbage collector finds values that are still reachable and frees the rest, including old function-call environments.

This is a Scheme subset, not a replacement for a complete Scheme implementation. Numbers are signed 64-bit integers; division truncates toward zero. I have not added macros, continuations exposed to Scheme, floating-point numbers, or the standard library. [The language reference](docs/language.md) explains the supported forms and limits.

## Tests and limits

There are 2 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: `scheme-in-c-ci.yml`.

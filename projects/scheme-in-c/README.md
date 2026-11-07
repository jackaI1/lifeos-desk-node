# scheme-in-c

I built a small program that runs instructions I type because I wanted to see how a programming language turns my code into answers. I can type a calculation and get its answer, or save a set of instructions in a file and run them together.

Those instructions use Scheme, a programming language for expressing calculations and working with lists. The program that reads and runs them is called an interpreter. I wrote mine in C, the language used to build the interpreter itself.

I use it to work through list and recursion exercises, where a function solves a problem by calling itself. I can change how the interpreter works and check that the same programs still give the same answers. This is a personal project, with a deliberately small language so I can follow the whole path from text to result.

## Try it

I use a C compiler, Make, and Python 3 for the tests. On macOS, `xcode-select --install` provides the compiler and Make. On Ubuntu, install `build-essential` and `python3`.

```sh
git clone https://github.com/jackaI1/lifeos-desk-node.git
cd lifeos-desk-node/projects/scheme-in-c
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

## A controller to test alongside it

I also use this project to practice checking a small control program independently of its implementation. The test fixture models a heater: it turns on at or below 19 °C, turns off at or above 21 °C, and keeps its previous setting between those temperatures. This gap, called a deadband, avoids switching the heater repeatedly when a reading fluctuates near one threshold. Three consecutive missing readings turn the heater off and raise a fault; a valid reading clears the fault and applies the thresholds again.

To replay a few samples after `make test`, give the driver a validity flag (1 for a reading, 0 for missing) and a temperature in thousandths of a degree Celsius per line:

```sh
printf '1 19000\n1 20000\n0 0\n0 0\n0 0\n' | ./build/controller-driver
# Each line is: heater on (0 or 1), fault (0 or 1)
```

The driver rejects incomplete or invalid input so a damaged trace cannot silently pass as a complete replay. This is a test fixture, not hardware control: a real device would need a sensor, a fixed-rate scheduler, and an output driver. [The controller notes](docs/controller.md) explain the timing and assumptions.

## What I can write

I can define functions, pass them to other functions, build lists, and use `if`, `let`, `cond`, and quoted data. A closure is a function that keeps the variables from where I created it. The counter example uses one to keep a private count.

The interpreter reuses its current work slot for a tail call, a function call whose result is returned directly. That lets an accumulating loop run hundreds of thousands of calls without growing the C call stack. A garbage collector finds values that are still reachable and frees the rest, including old function-call environments.

This is a Scheme subset, not a replacement for a complete Scheme implementation. Numbers are signed 64-bit integers; division truncates toward zero. I have not added macros, continuations exposed to Scheme, floating-point numbers, or the standard library. [The language reference](docs/language.md) explains the supported forms and limits.

## Check my changes

```sh
make test
make sanitize
./build/scheme --gc-stats tests/programs/tail.scm
```

My tests also compare 20,000 seeded sensor samples and a recorded trace against an independent Python model. The C controller uses caller-owned state and does not allocate memory. My tests run Scheme programs for recursion, functions passed as values, list processing, and captured variables. They also check invalid input, arithmetic overflow, and memory reclamation. Sanitizers check memory access and undefined C behavior. GitHub Actions runs both commands on Linux and macOS; Linux also checks for memory leaks.

I explain the evaluation loop, memory roots, and test measurements in [the design notes](docs/design.md).

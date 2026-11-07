I keep this library to a small MISRA C:2012 subset: fixed-width state and time,
no heap, recursion or pointer arithmetic, one exit per function and a complete
state table. This is an automated subset review, not MISRA certification.

- Rule 8.7: the public API has external linkage so the desk harness can call it.
  Static analysis sees the library translation unit alone; the host tests are
  deliberately outside that analysis scope.
- Rule 2.5: event constants are an interface consumed by callers and tests.
- Rule 21.1: standard fixed-width constant macros come from stdint.h.

The CI job runs cppcheck's MISRA addon and records its full report as an artifact.
No mandatory/required diagnostic in alert.c is silently ignored. The checker does
not include the copyrighted rule text; diagnostics use rule numbers.

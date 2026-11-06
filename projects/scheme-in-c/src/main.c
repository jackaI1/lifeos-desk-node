#include "scheme.h"
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int run_stream(VM *vm, FILE *input, const char *name, bool echo, bool terminal) {
    Reader *r = calloc(1, sizeof *r);
    if (!r) { fputs("out of memory\n", stderr); return 1; }
    r->file = input; r->name = name; r->line = 1;
    volatile int status = 0;
    for (;;) {
        if (setjmp(vm->escape)) {
            fprintf(stderr, "%s:%zu: %s\n", r->name, r->line, vm->error);
            status = 1;
            vm->expr = vm->env = vm->value = vm->cont = NULL;
            if (!terminal || feof(input)) break;
            /* A malformed form is discarded up to the next physical line. */
            int c;
            while ((c = fgetc(input)) != '\n' && c != EOF) {}
            if (c == '\n') ++r->line;
            clearerr(input);
        }
        vm->expr = vm->env = vm->value = vm->cont = NULL;
        collect(vm);
        if (terminal) { fputs("scheme> ", stdout); fflush(stdout); }
        Obj *form = read_form(vm, r);
        if (!form) {
            if (ferror(input)) { fprintf(stderr, "%s: read error\n", name); status = 1; }
            break;
        }
        Obj *value = evaluate(vm, form);
        if (echo && value != VOID) { print_value(stdout, value, false); putchar('\n'); }
    }
    free(r);
    return status;
}
static int initialize(VM *vm) {
    if (setjmp(vm->escape)) {
        fprintf(stderr, "initialization: %s\n", vm->error);
        return 1;
    }
    vm->global = environment(vm, NIL);
    install_primitives(vm);
    return 0;
}
static int final_collection(VM *vm) {
    /* A stream's error target is no longer active after run_stream returns. */
    if (setjmp(vm->escape)) {
        fprintf(stderr, "%s\n", vm->error);
        return 1;
    }
    collect(vm);
    return 0;
}
int main(int argc, char **argv) {
    VM *vm = calloc(1, sizeof *vm);
    if (!vm) return 1;
    vm->threshold = 4096;
    if (initialize(vm)) { destroy(vm); free(vm); return 1; }
    bool stats = false, files = false, options = true;
    int status = 0;
    for (int i = 1; i < argc; ++i) {
        if (options && !strcmp(argv[i], "--")) { options = false; continue; }
        if (options && !strcmp(argv[i], "--gc-stress")) { vm->stress = true; continue; }
        if (options && !strcmp(argv[i], "--gc-stats")) { stats = true; continue; }
        if (options && !strcmp(argv[i], "--help")) {
            puts("Usage: scheme [--gc-stress] [--gc-stats] [--] [file.scm ...]\n"
                 "Without files, read and print Scheme expressions from stdin.\n"
                 "With files, print only explicit display/write output. Ctrl-D exits the REPL.");
            destroy(vm); free(vm); return 0;
        }
        if (options && argv[i][0] == '-') {
            fprintf(stderr, "unknown option: %s\n", argv[i]); status = 1; break;
        }
        files = true;
        FILE *input = fopen(argv[i], "r");
        if (!input) { perror(argv[i]); status = 1; break; }
        status = run_stream(vm, input, argv[i], false, false);
        fclose(input);
        if (status) break;
    }
    if (!files && !status) status = run_stream(vm, stdin, "<stdin>", true, isatty(STDIN_FILENO));
    vm->expr = vm->env = vm->value = vm->cont = NULL;
    if (final_collection(vm)) status = 1;
    if (stats) fprintf(stderr, "collections=%zu live=%zu peak=%zu\n", vm->collections, vm->live, vm->peak);
    destroy(vm);
    free(vm);
    return status;
}

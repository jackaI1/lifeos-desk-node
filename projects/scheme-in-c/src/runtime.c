#include "scheme.h"
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

Obj nil_object = {.type = T_NIL};
Obj true_object = {.type = T_BOOL, .number = 1};
Obj false_object = {.type = T_BOOL};
Obj void_object = {.type = T_VOID};

_Noreturn void fail(VM *vm, const char *format, ...) {
    va_list ap;
    va_start(ap, format);
    vsnprintf(vm->error, sizeof vm->error, format, ap);
    va_end(ap);
    longjmp(vm->escape, 1);
}

Obj *object(VM *vm, Type type) {
    /* Allocation never collects. Only machine transitions are safe points. */
    Obj *o = calloc(1, sizeof *o);
    if (!o) fail(vm, "out of memory");
    o->type = type;
    o->next = vm->heap;
    vm->heap = o;
    vm->live++;
    if (vm->live > vm->peak) vm->peak = vm->live;
    return o;
}
Obj *integer(VM *vm, int64_t n) {
    Obj *o = object(vm, T_INT);
    o->number = n;
    return o;
}
Obj *text_object(VM *vm, Type type, const char *s) {
    Obj *o = object(vm, type);
    o->text = malloc(strlen(s) + 1);
    if (!o->text) fail(vm, "out of memory");
    strcpy(o->text, s);
    return o;
}
Obj *cons(VM *vm, Obj *a, Obj *b) {
    Obj *o = object(vm, T_PAIR);
    CAR(o) = a;
    CDR(o) = b;
    return o;
}
Obj *environment(VM *vm, Obj *parent) {
    Obj *o = object(vm, T_ENV);
    o->p[0] = NIL;
    o->p[1] = parent;
    return o;
}
bool symbol_is(Obj *o, const char *name) {
    return o->type == T_SYMBOL && strcmp(o->text, name) == 0;
}
void define(VM *vm, Obj *env, Obj *symbol, Obj *value) {
    if (symbol->type != T_SYMBOL) fail(vm, "define: expected a symbol");
    for (Obj *xs = env->p[0]; xs != NIL; xs = CDR(xs)) {
        Obj *b = CAR(xs);
        if (strcmp(CAR(b)->text, symbol->text) == 0) { CDR(b) = value; return; }
    }
    env->p[0] = cons(vm, cons(vm, symbol, value), env->p[0]);
}
Obj *binding(VM *vm, Obj *env, Obj *symbol) {
    for (; env != NIL; env = env->p[1])
        for (Obj *xs = env->p[0]; xs != NIL; xs = CDR(xs))
            if (strcmp(CAR(CAR(xs))->text, symbol->text) == 0) return CAR(xs);
    fail(vm, "unbound variable: %s", symbol->text);
}
size_t list_length(VM *vm, Obj *list) {
    size_t n = 0;
    for (; list != NIL; list = CDR(list)) {
        if (list->type != T_PAIR) fail(vm, "expected a proper list");
        ++n;
    }
    return n;
}
Obj *reverse(VM *vm, Obj *list) {
    Obj *out = NIL;
    for (; list != NIL; list = CDR(list)) {
        if (list->type != T_PAIR) fail(vm, "expected a proper list");
        out = cons(vm, CAR(list), out);
    }
    return out;
}
void arity(VM *vm, Obj *args, size_t min, size_t max, const char *name) {
    size_t n = list_length(vm, args);
    if (n < min || n > max) fail(vm, "%s: wrong number of arguments", name);
}

static void mark_push(Obj *o, Obj **stack, size_t *n) {
    if (!o || o == NIL || o == TRUE || o == FALSE || o == VOID || o->marked) return;
    o->marked = true;
    stack[(*n)++] = o;
}
void collect(VM *vm) {
    /* Every object is pushed once, so live slots suffice, including cycles. */
    Obj **stack = malloc((vm->live + 1) * sizeof *stack);
    if (!stack) fail(vm, "out of memory during collection");
    size_t n = 0;
    mark_push(vm->global, stack, &n);
    mark_push(vm->expr, stack, &n);
    mark_push(vm->env, stack, &n);
    mark_push(vm->value, stack, &n);
    mark_push(vm->cont, stack, &n);
    while (n) {
        Obj *o = stack[--n];
        for (size_t i = 0; i < 5; ++i) mark_push(o->p[i], stack, &n);
    }
    free(stack);
    Obj **link = &vm->heap;
    while (*link) {
        Obj *o = *link;
        if (o->marked) { o->marked = false; link = &o->next; }
        else { *link = o->next; free(o->text); free(o); --vm->live; }
    }
    vm->threshold = vm->live < 2048 ? 4096 : vm->live * 2;
    vm->collections++;
    vm->collect_requested = false;
}
void destroy(VM *vm) {
    while (vm->heap) {
        Obj *o = vm->heap;
        vm->heap = o->next;
        free(o->text);
        free(o);
    }
    vm->live = 0;
}
static void print_inner(FILE *out, Obj *o, bool display, unsigned depth) {
    if (depth > 512) { fputs("#<print-depth-limit>", out); return; }
    switch (o->type) {
    case T_NIL: fputs("()", out); break;
    case T_BOOL: fputs(o == FALSE ? "#f" : "#t", out); break;
    case T_VOID: fputs("#<unspecified>", out); break;
    case T_INT: fprintf(out, "%" PRId64, o->number); break;
    case T_SYMBOL: fputs(o->text, out); break;
    case T_STRING:
        if (!display) fputc('"', out);
        for (const char *s = o->text; *s; ++s) {
            if (!display && (*s == '\n' || *s == '\t' || *s == '"' || *s == '\\')) {
                fputc('\\', out);
                fputc(*s == '\n' ? 'n' : *s == '\t' ? 't' : *s, out);
            } else fputc(*s, out);
        }
        if (!display) fputc('"', out);
        break;
    case T_PAIR:
        fputc('(', out);
        for (;;) {
            print_inner(out, CAR(o), display, depth + 1);
            o = CDR(o);
            if (o == NIL) break;
            if (o->type != T_PAIR) {
                fputs(" . ", out); print_inner(out, o, display, depth + 1); break;
            }
            fputc(' ', out);
        }
        fputc(')', out);
        break;
    default: fputs("#<procedure>", out); break;
    }
}
void print_value(FILE *out, Obj *o, bool display) { print_inner(out, o, display, 0); }

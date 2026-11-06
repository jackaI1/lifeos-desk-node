#include "scheme.h"
#include <stdlib.h>
#include <string.h>
#include <limits.h>

enum {
    P_ADD, P_SUB, P_MUL, P_DIV, P_REM, P_EQNUM, P_LT, P_LE, P_GT, P_GE,
    P_CONS, P_CAR, P_CDR, P_LIST, P_NULL, P_PAIR, P_NUMBER, P_SYMBOL,
    P_BOOL, P_STRING, P_PROC, P_NOT, P_EQ, P_EQUAL, P_LENGTH, P_REVERSE,
    P_APPEND, P_DISPLAY, P_WRITE, P_NEWLINE, P_ASSERT, P_GC, P_APPLY
};
static const struct { const char *name; int id; size_t min, max; } natives[] = {
    {"+", P_ADD, 0, SIZE_MAX}, {"-", P_SUB, 1, SIZE_MAX},
    {"*", P_MUL, 0, SIZE_MAX}, {"/", P_DIV, 1, SIZE_MAX},
    {"remainder", P_REM, 2, 2}, {"=", P_EQNUM, 2, SIZE_MAX},
    {"<", P_LT, 2, SIZE_MAX}, {"<=", P_LE, 2, SIZE_MAX},
    {">", P_GT, 2, SIZE_MAX}, {">=", P_GE, 2, SIZE_MAX},
    {"cons", P_CONS, 2, 2}, {"car", P_CAR, 1, 1}, {"cdr", P_CDR, 1, 1},
    {"list", P_LIST, 0, SIZE_MAX}, {"null?", P_NULL, 1, 1},
    {"pair?", P_PAIR, 1, 1}, {"number?", P_NUMBER, 1, 1},
    {"symbol?", P_SYMBOL, 1, 1}, {"boolean?", P_BOOL, 1, 1},
    {"string?", P_STRING, 1, 1}, {"procedure?", P_PROC, 1, 1},
    {"not", P_NOT, 1, 1}, {"eq?", P_EQ, 2, 2}, {"equal?", P_EQUAL, 2, 2},
    {"length", P_LENGTH, 1, 1}, {"reverse", P_REVERSE, 1, 1},
    {"append", P_APPEND, 0, SIZE_MAX}, {"display", P_DISPLAY, 1, 1},
    {"write", P_WRITE, 1, 1}, {"newline", P_NEWLINE, 0, 0},
    {"assert", P_ASSERT, 1, 1}, {"gc", P_GC, 0, 0},
    {"apply", P_APPLY, 2, SIZE_MAX}
};
void install_primitives(VM *vm) {
    for (size_t i = 0; i < sizeof natives / sizeof *natives; ++i) {
        Obj *p = object(vm, T_NATIVE);
        p->tag = (int)i;
        define(vm, vm->global, text_object(vm, T_SYMBOL, natives[i].name), p);
    }
}
bool is_apply(Obj *proc) {
    return proc->type == T_NATIVE && natives[proc->tag].id == P_APPLY;
}
static Obj *boolean(bool b) { return b ? TRUE : FALSE; }
static int64_t number(VM *vm, Obj *o) {
    if (o->type != T_INT) fail(vm, "expected an integer argument");
    return o->number;
}
static bool eq(Obj *a, Obj *b) {
    if (a == b) return true;
    if (a->type != b->type) return false;
    if (a->type == T_INT) return a->number == b->number;
    if (a->type == T_SYMBOL) return !strcmp(a->text, b->text);
    return false;
}
/* Lists cannot be cyclic: Scheme exposes no pair mutation. The explicit
 * worklist handles deeply nested trees without recursive C calls. */
static bool equal(VM *vm, Obj *a, Obj *b) {
    Obj *work = cons(vm, cons(vm, a, b), NIL);
    while (work != NIL) {
        Obj *item = CAR(work);
        a = CAR(item); b = CDR(item); work = CDR(work);
        if (eq(a, b)) continue;
        if (a->type != b->type) return false;
        if (a->type == T_STRING && !strcmp(a->text, b->text)) continue;
        if (a->type != T_PAIR) return false;
        work = cons(vm, cons(vm, CAR(a), CAR(b)),
                    cons(vm, cons(vm, CDR(a), CDR(b)), work));
    }
    return true;
}
static int64_t arithmetic(VM *vm, int id, Obj *args) {
    int64_t out = id == P_MUL ? 1 : 0;
    if (id == P_SUB || id == P_DIV || id == P_REM) {
        out = number(vm, CAR(args)); args = CDR(args);
        if (args == NIL) {
            if (id == P_SUB) {
                if (out == INT64_MIN) fail(vm, "integer overflow");
                return -out;
            }
            if (out == 0) fail(vm, "division by zero");
            return 1 / out;
        }
    }
    for (; args != NIL; args = CDR(args)) {
        int64_t x = number(vm, CAR(args)), next = 0;
        bool overflow = false;
        if (id == P_ADD) overflow = __builtin_add_overflow(out, x, &next);
        else if (id == P_SUB) overflow = __builtin_sub_overflow(out, x, &next);
        else if (id == P_MUL) overflow = __builtin_mul_overflow(out, x, &next);
        else {
            if (x == 0) fail(vm, "division by zero");
            if (out == INT64_MIN && x == -1) {
                if (id == P_REM) next = 0;
                else fail(vm, "integer overflow");
            } else next = id == P_REM ? out % x : out / x;
        }
        if (overflow) fail(vm, "integer overflow");
        out = next;
    }
    return out;
}
Obj *primitive(VM *vm, Obj *proc, Obj *args) {
    size_t i = (size_t)proc->tag;
    arity(vm, args, natives[i].min, natives[i].max, natives[i].name);
    int id = natives[i].id;
    Obj *a = args == NIL ? NIL : CAR(args);
    Obj *b = args == NIL || CDR(args) == NIL ? NIL : CAR(CDR(args));
    switch (id) {
    case P_ADD: case P_SUB: case P_MUL: case P_DIV: case P_REM:
        return integer(vm, arithmetic(vm, id, args));
    case P_EQNUM: case P_LT: case P_LE: case P_GT: case P_GE: {
        bool result = true;
        int64_t previous = number(vm, a);
        for (Obj *xs = CDR(args); xs != NIL; xs = CDR(xs)) {
            int64_t next = number(vm, CAR(xs));
            result = result && (id == P_EQNUM ? previous == next :
                id == P_LT ? previous < next : id == P_LE ? previous <= next :
                id == P_GT ? previous > next : previous >= next);
            previous = next;
        }
        return boolean(result);
    }
    case P_CONS: return cons(vm, a, b);
    case P_CAR: case P_CDR:
        if (a->type != T_PAIR) fail(vm, "%s: expected a pair", natives[i].name);
        return id == P_CAR ? CAR(a) : CDR(a);
    case P_LIST: return args;
    case P_NULL: return boolean(a == NIL);
    case P_PAIR: return boolean(a->type == T_PAIR);
    case P_NUMBER: return boolean(a->type == T_INT);
    case P_SYMBOL: return boolean(a->type == T_SYMBOL);
    case P_BOOL: return boolean(a->type == T_BOOL);
    case P_STRING: return boolean(a->type == T_STRING);
    case P_PROC: return boolean(a->type == T_NATIVE || a->type == T_CLOSURE);
    case P_NOT: return boolean(a == FALSE);
    case P_EQ: return boolean(eq(a, b));
    case P_EQUAL: return boolean(equal(vm, a, b));
    case P_LENGTH: return integer(vm, (int64_t)list_length(vm, a));
    case P_REVERSE: return reverse(vm, a);
    case P_APPEND: {
        if (args == NIL) return NIL;
        Obj *prefix = NIL;
        while (CDR(args) != NIL) {
            Obj *xs = CAR(args);
            list_length(vm, xs);
            for (; xs != NIL; xs = CDR(xs)) prefix = cons(vm, CAR(xs), prefix);
            args = CDR(args);
        }
        Obj *out = CAR(args);
        for (; prefix != NIL; prefix = CDR(prefix)) out = cons(vm, CAR(prefix), out);
        return out;
    }
    case P_DISPLAY: case P_WRITE:
        print_value(stdout, a, id == P_DISPLAY); return VOID;
    case P_NEWLINE: putchar('\n'); return VOID;
    case P_ASSERT: if (a == FALSE) fail(vm, "assertion failed"); return VOID;
    case P_GC: vm->collect_requested = true; return VOID;
    default: fail(vm, "invalid native procedure");
    }
}

#include "scheme.h"
#include <string.h>

/* A continuation records what to do when an expression produces a value.
 * p[0] next, p[1] environment, p[2..4] instruction-specific operands. */
enum { K_IF, K_SEQUENCE, K_DEFINE, K_SET, K_OPERATOR, K_ARGUMENT, K_AND, K_OR, K_COND, K_RECEIVER };
static Obj *continuation(VM *vm, int tag, Obj *next, Obj *env,
                         Obj *a, Obj *b, Obj *c) {
    Obj *k = object(vm, T_CONT);
    k->tag = tag;
    k->p[0] = next; k->p[1] = env;
    k->p[2] = a; k->p[3] = b; k->p[4] = c;
    return k;
}
static bool same_symbol(Obj *a, Obj *b) {
    return a->type == T_SYMBOL && b->type == T_SYMBOL && !strcmp(a->text, b->text);
}
static void formals(VM *vm, Obj *params) {
    Obj *cursor = params;
    while (cursor != NIL) {
        Obj *name = cursor->type == T_PAIR ? CAR(cursor) : cursor;
        if (name->type != T_SYMBOL || symbol_is(name, "."))
            fail(vm, "lambda: parameters must be symbols");
        for (Obj *previous = params; previous != cursor; previous = CDR(previous))
            if (same_symbol(CAR(previous), name)) fail(vm, "duplicate parameter: %s", name->text);
        if (cursor->type != T_PAIR) break;
        cursor = CDR(cursor);
    }
}
static Obj *closure(VM *vm, Obj *params, Obj *body, Obj *env) {
    formals(vm, params);
    arity(vm, body, 1, SIZE_MAX, "lambda body");
    Obj *c = object(vm, T_CLOSURE);
    c->p[0] = params; c->p[1] = body; c->p[2] = env;
    return c;
}
static void sequence(VM *vm, Obj *body, Obj *env) {
    arity(vm, body, 1, SIZE_MAX, "body");
    vm->expr = CAR(body);
    vm->env = env;
    if (CDR(body) != NIL)
        vm->cont = continuation(vm, K_SEQUENCE, vm->cont, env, CDR(body), NULL, NULL);
    /* The final expression uses the caller's continuation unchanged. */
}
static Obj *expand_let(VM *vm, Obj *args) {
    arity(vm, args, 2, SIZE_MAX, "let");
    Obj *bindings = CAR(args), *params = NIL, *values = NIL;
    list_length(vm, bindings);
    for (; bindings != NIL; bindings = CDR(bindings)) {
        Obj *b = CAR(bindings);
        arity(vm, b, 2, 2, "let binding");
        if (CAR(b)->type != T_SYMBOL) fail(vm, "let: expected a binding name");
        params = cons(vm, CAR(b), params);
        values = cons(vm, CAR(CDR(b)), values);
    }
    params = reverse(vm, params);
    formals(vm, params);
    Obj *lambda = cons(vm, text_object(vm, T_SYMBOL, "lambda"), cons(vm, params, CDR(args)));
    return cons(vm, lambda, reverse(vm, values));
}
static void validate_cond(VM *vm, Obj *clauses) {
    for (Obj *xs = clauses; xs != NIL; xs = CDR(xs)) {
        Obj *clause = CAR(xs);
        arity(vm, clause, 1, SIZE_MAX, "cond clause");
        Obj *body = CDR(clause);
        if (symbol_is(CAR(clause), "else")) {
            if (CDR(xs) != NIL || body == NIL) fail(vm, "cond: else needs a body and must be last");
            if (symbol_is(CAR(body), "=>")) fail(vm, "cond: else cannot use =>");
        }
        if (body != NIL && symbol_is(CAR(body), "=>")) arity(vm, body, 2, 2, "cond =>");
    }
}
static void start_cond(VM *vm, Obj *clauses, Obj *env) {
    if (clauses == NIL) { vm->expr = VOID; vm->env = env; return; }
    Obj *clause = CAR(clauses);
    if (symbol_is(CAR(clause), "else")) { sequence(vm, CDR(clause), env); return; }
    vm->cont = continuation(vm, K_COND, vm->cont, env, CDR(clauses), CDR(clause), NULL);
    vm->expr = CAR(clause); vm->env = env;
}
static Obj *call_environment(VM *vm, Obj *proc, Obj *args) {
    Obj *env = environment(vm, proc->p[2]);
    Obj *params = proc->p[0];
    while (params->type == T_PAIR) {
        if (args == NIL) fail(vm, "lambda: too few arguments");
        define(vm, env, CAR(params), CAR(args));
        params = CDR(params); args = CDR(args);
    }
    if (params == NIL) {
        if (args != NIL) fail(vm, "lambda: too many arguments");
    } else define(vm, env, params, args);
    return env;
}

Obj *evaluate(VM *vm, Obj *expr) {
    enum { EVAL, RETURN, APPLY } mode = EVAL;
    vm->expr = expr;
    vm->env = vm->global;
    vm->value = VOID;
    vm->cont = NIL;
    for (;;) {
        if (vm->stress || vm->collect_requested || vm->live >= vm->threshold) collect(vm);
        if (mode == EVAL) {
            Obj *e = vm->expr;
            if (e->type == T_SYMBOL) { vm->value = CDR(binding(vm, vm->env, e)); mode = RETURN; }
            else if (e->type != T_PAIR) {
                if (e == NIL) fail(vm, "cannot evaluate an empty application");
                vm->value = e; mode = RETURN;
            } else {
                Obj *op = CAR(e), *args = CDR(e);
                list_length(vm, args);
                if (symbol_is(op, "quote")) {
                    arity(vm, args, 1, 1, "quote");
                    vm->value = CAR(args); mode = RETURN;
                } else if (symbol_is(op, "if")) {
                    arity(vm, args, 2, 3, "if");
                    Obj *rest = CDR(args);
                    vm->cont = continuation(vm, K_IF, vm->cont, vm->env,
                        CAR(rest), CDR(rest) == NIL ? VOID : CAR(CDR(rest)), NULL);
                    vm->expr = CAR(args);
                } else if (symbol_is(op, "lambda")) {
                    arity(vm, args, 2, SIZE_MAX, "lambda");
                    vm->value = closure(vm, CAR(args), CDR(args), vm->env); mode = RETURN;
                } else if (symbol_is(op, "define")) {
                    arity(vm, args, 2, SIZE_MAX, "define");
                    Obj *target = CAR(args);
                    if (target->type == T_PAIR) {
                        if (CAR(target)->type != T_SYMBOL) fail(vm, "define: expected a procedure name");
                        define(vm, vm->env, CAR(target), closure(vm, CDR(target), CDR(args), vm->env));
                        vm->value = VOID; mode = RETURN;
                    } else {
                        arity(vm, args, 2, 2, "define");
                        if (target->type != T_SYMBOL) fail(vm, "define: expected a name");
                        vm->cont = continuation(vm, K_DEFINE, vm->cont, vm->env, target, NULL, NULL);
                        vm->expr = CAR(CDR(args));
                    }
                } else if (symbol_is(op, "set!")) {
                    arity(vm, args, 2, 2, "set!");
                    if (CAR(args)->type != T_SYMBOL) fail(vm, "set!: expected a name");
                    Obj *b = binding(vm, vm->env, CAR(args));
                    vm->cont = continuation(vm, K_SET, vm->cont, vm->env, b, NULL, NULL);
                    vm->expr = CAR(CDR(args));
                } else if (symbol_is(op, "begin")) {
                    if (args == NIL) { vm->value = VOID; mode = RETURN; }
                    else sequence(vm, args, vm->env);
                } else if (symbol_is(op, "let")) vm->expr = expand_let(vm, args);
                else if (symbol_is(op, "cond")) {
                    validate_cond(vm, args); start_cond(vm, args, vm->env);
                }
                else if (symbol_is(op, "and") || symbol_is(op, "or")) {
                    bool is_and = symbol_is(op, "and");
                    if (args == NIL) { vm->value = is_and ? TRUE : FALSE; mode = RETURN; }
                    else {
                        if (CDR(args) != NIL) vm->cont = continuation(vm, is_and ? K_AND : K_OR,
                            vm->cont, vm->env, CDR(args), NULL, NULL);
                        vm->expr = CAR(args);
                    }
                } else {
                    vm->cont = continuation(vm, K_OPERATOR, vm->cont, vm->env, args, NULL, NULL);
                    vm->expr = op;
                }
            }
        } else if (mode == RETURN) {
            Obj *k = vm->cont;
            if (k == NIL) return vm->value;
            vm->cont = k->p[0];
            switch (k->tag) {
            case K_IF:
                vm->expr = vm->value == FALSE ? k->p[3] : k->p[2];
                vm->env = k->p[1]; mode = EVAL; break;
            case K_SEQUENCE:
                sequence(vm, k->p[2], k->p[1]); mode = EVAL; break;
            case K_DEFINE:
                define(vm, k->p[1], k->p[2], vm->value); vm->value = VOID; break;
            case K_SET:
                CDR(k->p[2]) = vm->value; vm->value = VOID; break;
            case K_OPERATOR:
                if (k->p[2] == NIL) { vm->expr = NIL; mode = APPLY; }
                else {
                    vm->cont = continuation(vm, K_ARGUMENT, vm->cont, k->p[1],
                        vm->value, CDR(k->p[2]), NIL);
                    vm->expr = CAR(k->p[2]); vm->env = k->p[1]; mode = EVAL;
                }
                break;
            case K_ARGUMENT: {
                Obj *values = cons(vm, vm->value, k->p[4]);
                if (k->p[3] == NIL) {
                    vm->value = k->p[2]; vm->expr = reverse(vm, values); mode = APPLY;
                } else {
                    vm->cont = continuation(vm, K_ARGUMENT, vm->cont, k->p[1],
                        k->p[2], CDR(k->p[3]), values);
                    vm->expr = CAR(k->p[3]); vm->env = k->p[1]; mode = EVAL;
                }
                break;
            }
            case K_COND:
                if (vm->value == FALSE) {
                    start_cond(vm, k->p[2], k->p[1]); mode = EVAL;
                } else if (k->p[3] != NIL) {
                    if (symbol_is(CAR(k->p[3]), "=>")) {
                        vm->cont = continuation(vm, K_RECEIVER, vm->cont, k->p[1], vm->value, NULL, NULL);
                        vm->expr = CAR(CDR(k->p[3])); vm->env = k->p[1];
                    } else sequence(vm, k->p[3], k->p[1]);
                    mode = EVAL;
                }
                break;
            case K_RECEIVER:
                vm->expr = cons(vm, k->p[2], NIL); mode = APPLY; break;
            case K_AND: case K_OR:
                if ((k->tag == K_AND && vm->value == FALSE) ||
                    (k->tag == K_OR && vm->value != FALSE)) break;
                vm->expr = CAR(k->p[2]); vm->env = k->p[1]; mode = EVAL;
                if (CDR(k->p[2]) != NIL) vm->cont = continuation(vm, k->tag,
                    vm->cont, vm->env, CDR(k->p[2]), NULL, NULL);
                break;
            default: fail(vm, "invalid continuation");
            }
        } else { /* APPLY: value is the procedure; expr is the argument list. */
            Obj *proc = vm->value, *args = vm->expr;
            if (is_apply(proc)) {
                arity(vm, args, 2, SIZE_MAX, "apply");
                Obj *prefix = NIL, *rest = CDR(args);
                while (CDR(rest) != NIL) { prefix = cons(vm, CAR(rest), prefix); rest = CDR(rest); }
                Obj *combined = CAR(rest);
                list_length(vm, combined);
                for (; prefix != NIL; prefix = CDR(prefix)) combined = cons(vm, CAR(prefix), combined);
                vm->value = CAR(args); vm->expr = combined;
                /* Do not add a return frame: apply itself is a tail call. */
            } else if (proc->type == T_NATIVE) {
                vm->value = primitive(vm, proc, args); mode = RETURN;
            } else if (proc->type == T_CLOSURE) {
                Obj *env = call_environment(vm, proc, args);
                sequence(vm, proc->p[1], env); mode = EVAL;
            } else fail(vm, "application: expected a procedure");
        }
    }
}

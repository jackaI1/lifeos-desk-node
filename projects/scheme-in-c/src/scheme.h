#ifndef SCHEME_H
#define SCHEME_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <setjmp.h>

typedef enum { T_NIL, T_BOOL, T_VOID, T_INT, T_SYMBOL, T_STRING,
               T_PAIR, T_ENV, T_CLOSURE, T_NATIVE, T_CONT } Type;
typedef struct Obj Obj;
struct Obj {
    Type type;
    bool marked;
    int tag;
    int64_t number;
    char *text;
    Obj *p[5];
    Obj *next;
};
typedef struct {
    Obj *heap, *global;
    /* These four registers are the entire running machine's GC roots. */
    Obj *expr, *env, *value, *cont;
    size_t live, peak, threshold, collections;
    bool stress, collect_requested;
    jmp_buf escape;
    char error[256];
} VM;
typedef struct { FILE *file; const char *name; size_t line; unsigned depth; } Reader;
extern Obj nil_object, true_object, false_object, void_object;
#define NIL (&nil_object)
#define TRUE (&true_object)
#define FALSE (&false_object)
#define VOID (&void_object)
#define CAR(o) ((o)->p[0])
#define CDR(o) ((o)->p[1])

_Noreturn void fail(VM *vm, const char *format, ...);
Obj *object(VM *vm, Type type);
Obj *integer(VM *vm, int64_t n);
Obj *text_object(VM *vm, Type type, const char *s);
Obj *cons(VM *vm, Obj *a, Obj *b);
Obj *environment(VM *vm, Obj *parent);
void define(VM *vm, Obj *env, Obj *symbol, Obj *value);
Obj *binding(VM *vm, Obj *env, Obj *symbol);
Obj *reverse(VM *vm, Obj *list);
size_t list_length(VM *vm, Obj *list);
void arity(VM *vm, Obj *args, size_t min, size_t max, const char *name);
bool symbol_is(Obj *o, const char *name);
void collect(VM *vm);
void destroy(VM *vm);
void print_value(FILE *out, Obj *o, bool display);
Obj *read_form(VM *vm, Reader *r);
Obj *evaluate(VM *vm, Obj *expr);
void install_primitives(VM *vm);
Obj *primitive(VM *vm, Obj *proc, Obj *args);
bool is_apply(Obj *proc);
#endif

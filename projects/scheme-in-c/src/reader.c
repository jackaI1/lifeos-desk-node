#include "scheme.h"
#include <ctype.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

#define TOKEN_LIMIT 4096
#define READ_DEPTH 512
static int take(Reader *r) {
    int c = fgetc(r->file);
    if (c == '\n') ++r->line;
    return c;
}
static void put_back(Reader *r, int c) {
    if (c != EOF) {
        ungetc(c, r->file);
        if (c == '\n') --r->line;
    }
}
static bool delimiter(int c) {
    return c == EOF || isspace((unsigned char)c) || c == '(' || c == ')' ||
           c == '\'' || c == '"' || c == ';';
}
static int skip(Reader *r) {
    int c;
    for (;;) {
        c = take(r);
        if (c == ';') while (c != EOF && c != '\n') c = take(r);
        if (c == EOF || !isspace((unsigned char)c)) return c;
    }
}
static Obj *read_one(VM *vm, Reader *r);
static Obj *read_string(VM *vm, Reader *r) {
    char buf[TOKEN_LIMIT + 1];
    size_t n = 0;
    for (;;) {
        int c = take(r);
        if (c == EOF) fail(vm, "unterminated string");
        if (c == '"') break;
        if (c == '\\') {
            c = take(r);
            if (c == 'n') c = '\n';
            else if (c == 't') c = '\t';
            else if (c != '"' && c != '\\') fail(vm, "unsupported string escape");
        }
        if (c == 0) fail(vm, "NUL byte in string");
        if (n == TOKEN_LIMIT) fail(vm, "string exceeds 4096 bytes");
        buf[n++] = (char)c;
    }
    buf[n] = '\0';
    return text_object(vm, T_STRING, buf);
}
static Obj *read_atom(VM *vm, Reader *r, int c) {
    char buf[TOKEN_LIMIT + 1];
    size_t n = 0;
    do {
        if (c == 0) fail(vm, "NUL byte in token");
        if (n == TOKEN_LIMIT) fail(vm, "token exceeds 4096 bytes");
        buf[n++] = (char)c;
        c = take(r);
    } while (!delimiter(c));
    put_back(r, c);
    buf[n] = '\0';
    if (strcmp(buf, "#t") == 0) return TRUE;
    if (strcmp(buf, "#f") == 0) return FALSE;
    if (buf[0] == '#') fail(vm, "unsupported token: %s", buf);
    bool numeric = isdigit((unsigned char)buf[0]) ||
        ((buf[0] == '+' || buf[0] == '-') && isdigit((unsigned char)buf[1]));
    if (numeric) {
        char *end;
        errno = 0;
        long long number = strtoll(buf, &end, 10);
        if (errno == ERANGE) fail(vm, "integer out of range");
        if (*end) fail(vm, "invalid integer token: %s", buf);
        return integer(vm, (int64_t)number);
    }
    return text_object(vm, T_SYMBOL, buf);
}
static Obj *read_list(VM *vm, Reader *r) {
    Obj *head = NIL, *tail = NULL;
    for (;;) {
        int c = skip(r);
        if (c == EOF) fail(vm, "unterminated list");
        if (c == ')') return head;
        put_back(r, c);
        Obj *item = read_one(vm, r);
        if (symbol_is(item, ".")) {
            if (!tail) fail(vm, "dot requires a preceding list element");
            Obj *end = read_one(vm, r);
            if (!end || symbol_is(end, ".")) fail(vm, "invalid dotted list");
            CDR(tail) = end;
            if (skip(r) != ')') fail(vm, "dotted list must end after its tail");
            return head;
        }
        Obj *cell = cons(vm, item, NIL);
        if (tail) CDR(tail) = cell;
        else head = cell;
        tail = cell;
    }
}
static Obj *read_one(VM *vm, Reader *r) {
    int c = skip(r);
    if (c == EOF) return NULL;
    if (++r->depth > READ_DEPTH) fail(vm, "reader nesting limit is 512");
    Obj *result;
    if (c == ')') fail(vm, "unexpected closing parenthesis");
    if (c == '(') result = read_list(vm, r);
    else if (c == '"') result = read_string(vm, r);
    else if (c == '\'') {
        Obj *quoted = read_one(vm, r);
        if (!quoted) fail(vm, "quote requires an expression");
        result = cons(vm, text_object(vm, T_SYMBOL, "quote"), cons(vm, quoted, NIL));
    } else result = read_atom(vm, r, c);
    --r->depth;
    return result;
}
Obj *read_form(VM *vm, Reader *r) { r->depth = 0; return read_one(vm, r); }

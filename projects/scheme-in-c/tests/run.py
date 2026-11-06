#!/usr/bin/env python3
"""Black-box tests: literal outputs and Scheme assertions, no runtime mocks."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BINARY = str(Path(sys.argv.pop(1) if len(sys.argv) > 1 else 'build/scheme').resolve())
ROOT = Path(__file__).resolve().parent


def run(source, *options, timeout=30):
    return subprocess.run([BINARY, *options], input=source, text=True,
                          capture_output=True, timeout=timeout)


class InterpreterTests(unittest.TestCase):
    def test_cond_returns_test_value_and_calls_receiver(self):
        p = run('(cond ((+ 2 3)))\n(cond (#f 1) ((+ 3 4) => (lambda (x) (* x 2))))\n')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, '5\n14\n')

    def test_reader_and_values(self):
        p = run("; comment\n42 -7 #t #f '() '(1 two . 3) \"hello\\nworld\"\n")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, '42\n-7\n#t\n#f\n()\n(1 two . 3)\n"hello\\nworld"\n')

    def test_programs(self):
        for path in sorted((ROOT / 'programs').glob('*.scm')):
            with self.subTest(program=path.name):
                p = subprocess.run([BINARY, str(path)], text=True, capture_output=True, timeout=45)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(p.stdout, 'ok\n')

    def test_multiline_repl(self):
        p = run('(define (square x)\n (* x x))\n(square 12)\n')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, '144\n')

    def test_file_arguments_share_environment(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'a.scm', Path(d) / 'b.scm'
            a.write_text('(define answer 42)')
            b.write_text('(display (+ answer 1)) (newline)')
            p = subprocess.run([BINARY, str(a), str(b)], text=True, capture_output=True, timeout=5)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout, '43\n')

    def test_errors(self):
        cases = [
            ('(', 'unterminated'), (')', 'unexpected'), ("'", 'quote'),
            ('(1 . 2 3)', 'dotted'), ('(. 1)', 'dot'),
            ('"unfinished', 'unterminated'), ('#maybe', 'token'),
            ('9223372036854775808', 'range'), ('missing', 'unbound'),
            ('(car 1)', 'pair'), ('(car)', 'argument'),
            ('(/ 1 0)', 'zero'), ('(+ 9223372036854775807 1)', 'overflow'),
            ('(* 9223372036854775807 2)', 'overflow'),
            ('(- -9223372036854775808)', 'overflow'),
            ('(/ -9223372036854775808 -1)', 'overflow'),
            ('(1 2)', 'procedure'), ('(if #t)', 'if'),
            ('(let ((x 1) (x 2)) x)', 'duplicate'),
            ('((lambda (x x) x) 1 2)', 'duplicate'),
            ('((lambda (x) x))', 'argument'),
            ('(cond (#t =>))', 'cond'), ('(quote 1 2)', 'quote'),
            ('(set! absent 2)', 'unbound'), ('(cons 1 2 3)', 'argument'),
            ('(apply + 3)', 'list'), ('(length \'(1 . 2))', 'list'),
        ]
        for source, diagnostic in cases:
            with self.subTest(source=source):
                p = run(source)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn(diagnostic, p.stderr.lower())
                self.assertNotIn('Sanitizer', p.stderr)

    def test_gc_reclaims_tail_loop(self):
        p = run('''(define (loop n) (if (= n 0) 7 (loop (- n 1))))
(loop 200000)
(gc)
''', '--gc-stats', timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, '7\n')
        import re
        stats = re.search(r'collections=(\d+) live=(\d+) peak=(\d+)', p.stderr)
        self.assertIsNotNone(stats, p.stderr)
        collections, live, peak = map(int, stats.groups())
        self.assertGreater(collections, 100)
        self.assertLess(live, 2000)
        self.assertLess(peak, 10000)

    def test_gc_at_every_safe_point(self):
        p = run('''(define (make x) (lambda (y) (cons x y)))
(define f (make '(1 2 3)))
(gc)
(f '(4 5))
(let ((a (list 8 9)) (b (+ 1 2))) (cons a b))
''', '--gc-stress')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, '((1 2 3) 4 5)\n((8 9) . 3)\n')

    def test_deep_non_tail_recursion_and_gc_graph(self):
        p = run("""(define (build n) (if (= n 0) '() (cons n (build (- n 1)))))
(define xs (build 20000))
(gc)
(length xs)
(equal? xs (reverse (reverse xs)))
""", timeout=45)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, '20000\n#t\n')

    def test_reader_limits_and_bad_bytes(self):
        for source in ['(' * 600 + '0' + ')' * 600, "'" * 600 + '0',
                       'a' * 4097, '"' + 'a' * 4097 + '"', '\x00']:
            with self.subTest(size=len(source)):
                p = run(source)
                self.assertNotEqual(p.returncode, 0)
                self.assertNotIn('Sanitizer', p.stderr)
                self.assertTrue(p.stderr.strip())

    def test_repl_recovers_from_runtime_and_reader_errors(self):
        # A real pseudo-terminal exercises prompts and error recovery.
        import errno
        import pty
        import select
        import time
        master, slave = pty.openpty()
        proc = subprocess.Popen([BINARY], stdin=slave, stdout=slave, stderr=slave,
                                close_fds=True)
        os.close(slave)
        output = bytearray()
        try:
            os.write(master, b'(+ 1 2)\n(car 1)\n)\n(+ 4 5)\n')
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and output.count(b'scheme> ') < 5:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        output.extend(os.read(master, 4096))
                    except OSError as e:
                        if e.errno == errno.EIO:
                            break
                        raise
            os.write(master, b'\x04')
            proc.wait(timeout=5)
            text = output.decode(errors='replace').replace('\r', '')
            self.assertIn('scheme> 3\n', text)
            self.assertIn('expected a pair', text)
            self.assertIn('unexpected closing', text)
            self.assertIn('scheme> 9\n', text)
            self.assertEqual(proc.returncode, 1)  # Errors remain visible to a caller.
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
            os.close(master)

    def test_repl_exits_on_eof_during_incomplete_form(self):
        import pty
        master, slave = pty.openpty()
        proc = subprocess.Popen([BINARY], stdin=slave, stdout=slave, stderr=slave,
                                close_fds=True)
        os.close(slave)
        try:
            os.write(master, b'(\n\x04')
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.fail('REPL must exit after the first EOF on an incomplete form')
            self.assertEqual(proc.returncode, 1)
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
            os.close(master)

    def test_missing_file(self):
        p = subprocess.run([BINARY, '/definitely/missing.scm'], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('missing.scm', p.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)

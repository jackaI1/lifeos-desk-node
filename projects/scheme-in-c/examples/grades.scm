; Run: ./build/scheme examples/grades.scm
; Functions are ordinary values, so the same list walk can do several jobs.
(define (foldr f base xs)
  (if (null? xs) base (f (car xs) (foldr f base (cdr xs)))))
(define (filter keep? xs)
  (cond ((null? xs) '())
        ((keep? (car xs)) (cons (car xs) (filter keep? (cdr xs))))
        (else (filter keep? (cdr xs)))))
(define grades '(52 81 94 63 75))
(display "Total: ") (display (foldr + 0 grades)) (newline)
(display "At least 75: ")
(display (filter (lambda (grade) (>= grade 75)) grades)) (newline)

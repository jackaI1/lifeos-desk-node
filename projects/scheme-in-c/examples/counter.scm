; A closure remembers its own starting value after make-counter returns.
(define (make-counter start)
  (lambda () (set! start (+ start 1)) start))
(define count (make-counter 0))
(display (count)) (newline)
(gc) ; Throw away unreachable objects. The counter's value stays alive.
(display (count)) (newline)

(use-modules (desk scenario) (ice-9 textual-ports))

;; A scenario is data. Never load or eval its contents as a Scheme program.
(catch #t
  (lambda ()
    (unless (= (length (command-line)) 1) (error "usage: compile.scm < scenario.scm"))
    (let ((text (get-string-n (current-input-port) 65537)))
      (when (or (eof-object? text) (> (string-length text) 65536))
        (error "scenario must contain 1 to 65536 characters"))
      (let* ((port (open-input-string text)) (datum (read port)))
        (unless (eof-object? (read port)) (error "expected exactly one scenario"))
        ;; Guile can substitute a void port for an unusable stdout at startup.
        ;; Open descriptor 1 explicitly so that failure is reported, not hidden.
        (let ((out (fdopen 1 "w")))
          (write-scenario datum out)
          (force-output out)))))
  (lambda (key . args)
    (format (current-error-port) "scenario: ~a ~s~%" key args)
    (exit 1)))

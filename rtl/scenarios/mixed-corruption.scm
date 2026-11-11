;; Good readings and deliberately corrupted checksums, mixed, with uploads between.
;; The corrupt samples flip the temperature CRC, as the existing scenario compiler does.
(scenario
  (repeat 6 (sample 25000 50000) (fault 25000 50000) (sample 30000 40000) (upload))
  (repeat 4 (fault 10000 20000) (sample 100000 90000))
  (upload)
  (sample -45000 0)
  (fault 130000 100000)
  (sample 130000 100000)
  (upload))

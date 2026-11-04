;; Sensor values are milli-degrees C and thousandths of percent humidity.
;; Seventy good samples overflow the 64-reading queue by six readings.
(scenario
  (repeat 70 (sample 25000 50000))
  (fault 25000 50000)
  (upload))

# Component review priority

Build quantity: 10 boards. BOM SHA-256: `88df132fbf7e62628a65ed59902e341c3176b87482d65c71b2cf6837f1bf32ed`.

HOLD: engineering review and board validation required.

0–100 review priority, not a predicted probability; capped at 100.

Lifecycle: EOL +50, NRND +35, unverified +20, active +0. Missing manufacturer lifecycle evidence +10. No other-manufacturer alternate +25; other-manufacturer candidates only +10. Unverified or unresolved RoHS and REACH +5 each.

Multiple distributors do not create another manufacturer. All alternates remain unqualified candidates; a specification comparison never approves substitution. The prototype board is untested.

## DN-CAP-CAP-22U-16V: Samsung Electro-Mechanics CL21A226MOQNNNE (80/100)

References: C2, C3. Quantity per board: 2.

- manufacturer reports NRND; dated evidence unverified: obtain a dated exact-MPN declaration.
- Lifecycle NRND (+35): avoid new production dependency; qualify a replacement.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.

## DN-CAP-CAP-100N-50V: Samsung Electro-Mechanics CL10B104KB8NNNC (65/100)

References: C4, C6, C8. Quantity per board: 3.

- manufacturer reports ACTIVE; dated evidence unverified: obtain a dated exact-MPN declaration.
- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.

## DN-CON-HEADER-I2C: XFCN PZ254V-11-04P (65/100)

References: J2. Quantity per board: 1.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- Alternate constraint: I have not checked an independent header drawing for matching square pin size, tail length, body height, plating and hole fit. A 2.54 mm pitch alone is insufficient.

## DN-CON-HEADER-OLED: XFCN PZ254V-11-07P (65/100)

References: J4. Quantity per board: 1.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- Alternate constraint: I have not checked an independent header drawing for matching square pin size, tail length, body height, plating and hole fit. A 2.54 mm pitch alone is insufficient.

## DN-CON-HEADER-UART: XFCN PZ254V-11-06P (65/100)

References: J3. Quantity per board: 1.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- Alternate constraint: I have not checked an independent header drawing for matching square pin size, tail length, body height, plating and hole fit. A 2.54 mm pitch alone is insufficient.

## DN-CON-USB-C: Korean Hroparts Elec (HRO) TYPE-C-31-M-12 (65/100)

References: J1. Quantity per board: 1.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- Alternate constraint: I have not located a second receptacle with a proven identical shell, mounting holes, pad positions and pin mapping. USB-C naming does not establish footprint compatibility.

## DN-LED-LED-RED: Hubei KENTO Elec KT-0603R (65/100)

References: D2. Quantity per board: 1.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- Alternate constraint: I need to reconcile conflicting distributor forward-voltage and intensity values against the supplied manufacturer LED sheet, then qualify polarity, brightness and current before selecting a substitute.

## DN-REG-REGULATOR-3V3: Diodes Incorporated AZ1117CH-3.3TRG1 (65/100)

References: U2. Quantity per board: 1.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- Alternate constraint: I have not qualified a second regulator against pinout, dropout at load, ceramic-capacitor stability, transient response and board thermal dissipation. A generic 1117 name is insufficient.

## DN-SWT-SWITCH-RESET-BOOT: XKB Connectivity TS-1187A-B-A-B (65/100)

References: SW1, SW2. Quantity per board: 2.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- Alternate constraint: SW1 and SW2 share this one catalog item. I have not qualified another switch for pad mapping, actuator height, force and mechanics; similar case dimensions alone are insufficient.

## DN-TVS-TVS-5V: MDD (Microdiode Semiconductor) SMF5.0A (65/100)

References: D1. Quantity per board: 1.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- Alternate constraint: I have not qualified a second source against this exact SOD-123F land pattern, polarity and 10/1000 us surge specification. The 9.2 V clamp also needs a system protection review.

## DN-FUS-FUSE-750MA: Littelfuse 1206L075THYR (60/100)

References: F1. Quantity per board: 1.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- Alternate constraint: I have not qualified a second PPTC against hold/trip derating, trip curve, post-trip resistance and exact pad geometry. A similar hold current alone is insufficient.

## DN-MOD-ESP32-MODULE: Espressif Systems ESP32-WROOM-32E-N4 (55/100)

References: U1. Quantity per board: 1.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.
- Alternate constraint: I have not qualified another module for the footprint, strapping pins, flash, antenna keepout, firmware and radio certification. A different ESP32 module is not an automatic substitute.

## DN-SEN-SENSOR-SHT31: Sensirion SHT31-DIS-B2.5KS (55/100)

References: U3. Quantity per board: 1.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.

## DN-CAP-CAP-10U-25V: Samsung Electro-Mechanics CL21A106KAYNNNE (50/100)

References: C1, C7. Quantity per board: 2.

- manufacturer reports ACTIVE; dated evidence unverified: obtain a dated exact-MPN declaration.
- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- Other-manufacturer candidates only (+10): compare specifications and qualify on the board before substitution.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.

## DN-CAP-CAP-1U-50V: Samsung Electro-Mechanics CL10A105KB8NNNC (50/100)

References: C5. Quantity per board: 1.

- manufacturer reports ACTIVE; dated evidence unverified: obtain a dated exact-MPN declaration.
- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- Other-manufacturer candidates only (+10): compare specifications and qualify on the board before substitution.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.

## DN-RES-RES-10K: UNI-ROYAL 0603WAF1002T5E (50/100)

References: R3, R4, R5, R9, R10, R11. Quantity per board: 6.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- Other-manufacturer candidates only (+10): compare specifications and qualify on the board before substitution.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.

## DN-RES-RES-1K: UNI-ROYAL 0603WAF1001T5E (50/100)

References: R8. Quantity per board: 1.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- Other-manufacturer candidates only (+10): compare specifications and qualify on the board before substitution.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.

## DN-RES-RES-4K7: UNI-ROYAL 0603WAF4701T5E (50/100)

References: R6, R7. Quantity per board: 2.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- Other-manufacturer candidates only (+10): compare specifications and qualify on the board before substitution.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.

## DN-RES-RES-5K1: UNI-ROYAL 0603WAF5101T5E (50/100)

References: R1, R2. Quantity per board: 2.

- Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.
- Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.
- Other-manufacturer candidates only (+10): compare specifications and qualify on the board before substitution.
- ROHS unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.
- REACH unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.

# Component evidence reviewed on 6 November 2026

I grouped the fitted BOM into 19 manufacturer part numbers. SW1 and SW2 use the same switch, so I keep one catalog entry for both. I preserved each schematic MPN string and separately recorded its normalized manufacturer and orderable MPN. LCSC links identify the existing sourcing route; they are not proof of compliance, stock or manufacturer authorization.

I recorded nine alternatives as candidates: four YAGEO resistor values, four capacitor groups and an SHT35 sensor. None is an approved board substitution. Matching the recorded fields is only a first check; the qualification note describes remaining electrical, assembly and firmware work. I did not alter the schematic, PCB or fitted BOM.

## Findings that affect a purchasing review

- Samsung's [22 uF product page](https://product.samsungsem.com/mlcc/CL21A226MOQNNN.do) reports **NRND**, meaning not recommended for new designs, and recommends CL21A226MOYNNN#. The [recommended family](https://product.samsungsem.com/mlcc/CL21A226MOYNNN.do) explicitly lists CL21A226MOYNNNE. Its maximum thickness is 1.45 mm versus 1.40 mm for the original. I still need to check bias capacitance and regulator stability before approval.
- The [Littelfuse 1206L datasheet](https://www.littelfuse.com/assetdocs/littelfuse-ptc-1206l-datasheet?assetguid=2b6a1515-d4ee-4c83-8bd4-152b4901b8f5), revised 26 February 2024, rates **1206L075TH at 8 V**, with 0.75 A hold and 1.5 A trip at 20 C still air. The /16 variant is a different part. Some distributor summaries mix these voltage ratings.
- The [SHT3x-DIS datasheet](https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf), December 2022 version 7, specifies SHT31 temperature accuracy as typical 0.2 C at 0 to 90 C and SHT35 as typical 0.1 C at 20 to 60 C. I recorded the numeric values and kept the different accuracy ranges in the candidate note. These are typical figures, not maximum error guarantees over the whole operating range.
- I used 15 V recommended maximum input and 0.8 A rated output for the [AZ1117C](https://www.diodes.com/datasheet/download/AZ1117C.pdf). Its 18 V absolute maximum and typical current limit are different quantities. Board heat dissipation and effective output capacitance still limit operation.

## What the environmental evidence establishes

I mark a claim compliant only where a manufacturer document has an explicit calendar date and a scope that includes the item. This describes component evidence; it does not certify the assembled product or all substances introduced during manufacture.

| Item | Evidence and scope | Limitation |
| --- | --- | --- |
| Littelfuse 1206L075THYR | The 26 February 2024 family datasheet states RoHS compliance and maps TH to the YR order code. | I did not locate a dated REACH declaration for this order code. |
| Espressif ESP32-WROOM-32E-N4 | The [manufacturer declaration](https://documentation.espressif.com/Environmental%20Compliance%20Declaration%20for%20Espressif%20Products.pdf) is printed **15 May 2026** and covers its supplied chips, modules and boards. It states RoHS with lead exemption **7c-1** and REACH SVHC **253**. | The website upload date differs. I use the printed date and do not infer subsequent SVHC-list coverage. |
| Sensirion SHT31 | The [manufacturer declaration](https://sensirion.com/media/documents/9152E5A6/67481CF3/Sensirion_REACH-RoHS-HalFree_Humidity-Temperature.pdf), signed **25 November 2024**, explicitly lists SHT31 for RoHS and REACH; it states the SVHC 1000 ppm threshold. | It does not identify the candidate-list edition. I do not infer current-list coverage. |
| Samsung capacitors | Manufacturer product pages show environmental badges and live production status. | Their page creation time is generated on request. I keep environmental claims unverified and leave lifecycle document dates empty; active/NRND is the live reported status pending dated evidence. |
| Diodes AZ1117C | DS36676 Rev 5-2 states RoHS directives 2011/65/EU and 2015/863/EU. | The issue date is only September 2022. I do not invent a day or treat this as a dated, order-code-specific declaration. |
| XFCN headers | The [manufacturer PZ254V-11-XX drawing](https://www.xfconn.com/uploads/soft/20240711/4-240G11122102R.pdf), dated **11 June 2024**, has a RoHS mark. | The mark does not identify a directive revision or full declaration scope, so I keep RoHS unverified. |
| Remaining items | I retained the known identity and source links. | I did not obtain dated manufacturer lifecycle, RoHS or REACH evidence. Unverified means missing evidence, not noncompliance. |

## Source boundaries and qualification gaps

I used [UNI-ROYAL's Chip Series V9 datasheet](https://www.uni-royal.cn/en/images/userfile/file/1750647324c56505e6d9ab55c7.pdf), dated 21 June 2025, to decode the original resistor values, 0603 package, WA 0.1 W rating and F 1% tolerance. The four YAGEO alternatives each link to the manufacturer's exact-value specsheet, including its 0.1 W rating at 70 C. I did not convert a current datasheet into a lifecycle claim.

For capacitor alternatives I used TDK's [10 uF 25 V product information](https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=C2012X5R1E106K125AB), its [1 uF 50 V characteristic sheet](https://product.tdk.com/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c1608x5r1h105k080ab.pdf), and Samsung's [100 nF 5% product information](https://product.samsungsem.com/mlcc/CL10B104JB8NNN.do). These match the catalog's nominal capacitance, package and dielectric, with equal or better voltage and tolerance. Nominal capacitance does not establish capacitance under DC bias.

I found manufacturer-authored MDD, KENTO and XKB sheets on LCSC's host. The catalog identifies the real PDF targets supplied by its viewer, but direct retrieval returned HTTP 403 in this review. I did not retry that denied boundary or treat distributor compliance text as a declaration. I keep those claims unverified. In particular, I omit disputed LED forward-voltage and brightness ratings. The MDD family sheet is indexed under SMF16A but covers SMF5.0(C)A through SMF440(C)A; it still needs procurement-side confirmation against the exact supplied lot. MDDDiodes.com is an authorized distributor site, so its NextGen declarations are not manufacturer compliance evidence here.

The HRO link is its manufacturer product page; I did not retrieve a dated full connector drawing. Its contact count and pin mapping identify the board's existing 16-contact USB2.0 symbol and footprint, not a fully qualified mechanical substitute. No second-source connector or switch has been approved. I also leave module substitutes empty because antenna clearance, strapping, flash, firmware and certification need explicit review.

I saved source links and concise facts so I can recheck the original documents before ordering.

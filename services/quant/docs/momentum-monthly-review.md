# 12-1 momentum backtest: month by month

> **Correction 2026-10-29:** the CAGRs and drawdowns here compound returns measured on a *fixed* capital, with a fixed ₹ amount per new position and profits not reinvested. That is fine for comparing rules, so the verdicts stand, but it **overstates what a one-time investment would grow to**. For ₹1 lakh invested once and split equally across the 10 every month, see [momentum-compound.md](momentum-compound.md): 26.7% a year, worst fall 39%.

One continuous book, ₹4,00,000, top 20 of the NSE Liquid-500. Net of charges and slippage. Code: `quant_agents/research/momentum_months.py`. Monthly figures are return on the ₹4,00,000 capital; the year column compounds them. The "why" labels come from a fixed rule (below), not from hindsight judgement. **Everything here is descriptive: no pattern below is a tested trading rule.**

## Momentum, net

| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2016 |  | -18.2% | +8.2% | +5.1% | -5.5% | +13.0% | +2.8% | -8.5% | +3.9% | +3.1% | -24.8% | -0.4% | **-25.1%** |
| 2017 | +11.2% | +4.6% | +3.2% | +1.6% | -7.4% | +5.0% | +8.8% | +14.2% | +9.3% | +32.8% | +8.5% | +6.1% | **+146.6%** |
| 2018 | +0.8% | +4.3% | -2.7% | +11.9% | -11.4% | -15.4% | +13.0% | +17.6% | -26.6% | +5.9% | -4.5% | -4.0% | **-18.6%** |
| 2019 | -13.0% | -3.3% | +5.1% | -1.4% | +3.0% | -4.7% | -11.4% | -2.4% | +9.4% | +0.4% | -1.7% | +1.6% | **-18.7%** |
| 2020 | +7.2% | -7.7% | -26.6% | +21.7% | -0.7% | +12.6% | +14.5% | +23.3% | +15.5% | +3.4% | +27.6% | +14.0% | **+142.6%** |
| 2021 | -5.7% | +22.0% | -4.4% | +14.1% | +20.8% | -0.3% | +3.2% | -0.9% | +4.8% | +2.3% | -2.1% | +8.1% | **+75.5%** |
| 2022 | +9.0% | -11.6% | +11.3% | +4.1% | -13.2% | -10.5% | +9.3% | +8.8% | -5.0% | +1.0% | +3.4% | -5.1% | **-2.9%** |
| 2023 | -5.6% | -10.9% | +3.3% | +9.3% | +6.6% | +19.3% | +19.6% | +16.2% | +4.4% | +1.4% | +11.1% | +6.2% | **+109.8%** |
| 2024 | +20.2% | -4.8% | -5.9% | +17.4% | +4.4% | +3.9% | +14.5% | -3.0% | -1.0% | -7.9% | -2.5% | +2.9% | **+39.2%** |
| 2025 | -13.9% | -15.9% | +13.7% | -2.4% | +14.1% | -0.1% | -2.6% | -2.0% | -2.4% | +2.6% | +4.2% | +7.3% | **-2.1%** |
| 2026 | -9.6% | +5.5% | -9.1% | +29.1% | +11.5% | +11.7% | +1.4% | +16.2% | +6.4% | -1.6% |  |  | **+71.9%** |

## Equal-weight Liquid-500, gross (benchmark)

| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2016 |  | -13.1% | +14.0% | +5.0% | -0.3% | +6.6% | +4.7% | +1.5% | +0.4% | +5.0% | -8.4% | -2.2% | **+11.0%** |
| 2017 | +7.3% | +4.8% | +4.3% | +5.7% | -3.1% | +0.8% | +5.0% | -0.2% | -0.3% | +10.6% | +2.1% | +4.6% | **+49.4%** |
| 2018 | -2.3% | -4.3% | -7.2% | +8.1% | -6.5% | -7.2% | +3.2% | +4.1% | -15.1% | -1.0% | +1.8% | +2.3% | **-23.5%** |
| 2019 | -5.9% | -1.6% | +10.0% | -2.7% | +1.5% | -5.5% | -11.1% | -2.6% | +5.2% | +2.7% | +0.6% | +0.0% | **-10.6%** |
| 2020 | +4.8% | -6.5% | -30.0% | +17.4% | -2.0% | +15.6% | +5.2% | +10.2% | +0.6% | -0.2% | +12.5% | +7.8% | **+28.7%** |
| 2021 | -0.0% | +11.7% | +0.6% | +4.5% | +10.1% | +6.0% | +4.6% | -1.9% | +5.8% | -0.3% | -2.9% | +3.7% | **+49.3%** |
| 2022 | +0.7% | -8.0% | +4.9% | +2.9% | -7.7% | -6.3% | +9.9% | +6.1% | -2.2% | +1.6% | +3.1% | -2.3% | **+1.0%** |
| 2023 | -2.7% | -4.1% | -0.1% | +7.8% | +5.2% | +6.6% | +7.2% | +4.7% | +2.9% | -2.1% | +8.4% | +7.8% | **+48.9%** |
| 2024 | +7.6% | -0.1% | -3.8% | +9.0% | -1.1% | +8.6% | +6.5% | +0.5% | +1.6% | -6.0% | -0.1% | -0.4% | **+22.9%** |
| 2025 | -7.1% | -12.4% | +8.9% | +2.7% | +9.0% | +3.7% | -2.8% | -2.9% | +1.9% | +4.0% | -2.0% | -0.4% | **+0.3%** |
| 2026 | -5.2% | +3.6% | -11.4% | +17.8% | +1.8% | +2.7% | +1.7% | +1.3% | -3.9% | -5.2% |  |  | **+0.7%** |

## Momentum minus benchmark

| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2016 |  | -5.1% | -5.8% | +0.1% | -5.2% | +6.5% | -2.0% | -10.0% | +3.5% | -1.9% | -16.5% | +1.8% | **-32.5%** |
| 2017 | +3.9% | -0.2% | -1.0% | -4.1% | -4.3% | +4.2% | +3.7% | +14.4% | +9.6% | +22.2% | +6.5% | +1.5% | **+65.0%** |
| 2018 | +3.1% | +8.6% | +4.5% | +3.9% | -4.9% | -8.2% | +9.8% | +13.6% | -11.5% | +6.9% | -6.3% | -6.3% | **+6.4%** |
| 2019 | -7.1% | -1.7% | -4.8% | +1.3% | +1.6% | +0.8% | -0.3% | +0.2% | +4.2% | -2.3% | -2.3% | +1.6% | **-9.1%** |
| 2020 | +2.4% | -1.1% | +3.4% | +4.3% | +1.3% | -2.9% | +9.3% | +13.1% | +14.9% | +3.6% | +15.1% | +6.2% | **+88.5%** |
| 2021 | -5.7% | +10.3% | -5.0% | +9.7% | +10.8% | -6.3% | -1.4% | +1.0% | -1.0% | +2.6% | +0.8% | +4.4% | **+17.5%** |
| 2022 | +8.3% | -3.6% | +6.4% | +1.2% | -5.5% | -4.1% | -0.6% | +2.7% | -2.8% | -0.6% | +0.3% | -2.8% | **-3.8%** |
| 2023 | -2.9% | -6.8% | +3.5% | +1.5% | +1.4% | +12.7% | +12.4% | +11.5% | +1.5% | +3.5% | +2.7% | -1.6% | **+40.9%** |
| 2024 | +12.6% | -4.8% | -2.1% | +8.4% | +5.5% | -4.7% | +8.1% | -3.5% | -2.5% | -1.9% | -2.4% | +3.3% | **+13.3%** |
| 2025 | -6.8% | -3.5% | +4.9% | -5.1% | +5.1% | -3.8% | +0.3% | +1.0% | -4.3% | -1.4% | +6.2% | +7.7% | **-2.4%** |
| 2026 | -4.4% | +1.9% | +2.3% | +11.3% | +9.7% | +9.0% | -0.3% | +14.9% | +10.3% | +3.6% |  |  | **+70.7%** |

## Why, summed over all months

| Label | Months | Mean excess per month | Total excess (sum) |
|---|---|---|---|
| leaders kept leading | 46 | +8.3% | +382% |
| leaders fell less than the market | 5 | +6.1% | +30% |
| moved with the market | 48 | -0.1% | -7% |
| momentum crash: rebound led by beaten-down stocks | 2 | -5.3% | -11% |
| leadership rotated away from the leaders | 14 | -5.4% | -75% |
| leaders fell harder than the market | 14 | -6.6% | -92% |

Label rule: excess ≥ +3 points → *leaders kept leading* (or *fell less than the market* when the benchmark fell ≥ 3%). Excess ≤ −3 points → *momentum crash* when the benchmark rose ≥ 5% after falling ≥ 5% over the previous 3 months; *leaders fell harder* when the benchmark fell ≥ 3%; otherwise *leadership rotated away*. Anything else → *moved with the market*.

## Every month

| Month | Momentum | Benchmark | Excess | Why | Best holdings | Worst holdings |
|---|---|---|---|---|---|---|
| 2016-02 | -18.2% | -13.1% | -5.1% | leaders fell harder than the market | RUSHIL +35%, RAJESHEXPO -2%, GAYAPROJ -6% | ESTER -44%, NCLIND -34%, LYKALABS -32% |
| 2016-03 | +8.2% | +14.0% | -5.8% | momentum crash: rebound led by beaten-down stocks | ESTER +43%, MANGALAM +42%, SECURKLOUD +30% | RUSHIL -32%, RAJESHEXPO -12%, JMTAUTOLTD -12% |
| 2016-04 | +5.1% | +5.0% | +0.1% | moved with the market | RUSHIL +44%, COSMOFIRST +29%, DEEPENR +21% | GODFRYPHLP -24%, MANGALAM -22%, GMBREW -20% |
| 2016-05 | -5.5% | -0.3% | -5.2% | leadership rotated away from the leaders | RUSHIL +28%, WELSPUNLIV +4%, DHAMPURSUG +3% | SIGNET -42%, SECURKLOUD -21%, GMBREW -18% |
| 2016-06 | +13.0% | +6.6% | +6.5% | leaders kept leading | DALMIASUG +60%, SAKHTISUG +46%, TRIVENI +37% | RAJESHEXPO -25%, MANGALAM -21%, COSMOFIRST -6% |
| 2016-07 | +2.8% | +4.7% | -2.0% | moved with the market | ENERGYDEV +44%, MANGALAM +20%, HIMATSEIDE +19% | GMBREW -23%, KAKATCEM -14%, RUSHIL -10% |
| 2016-08 | -8.5% | +1.5% | -10.0% | leadership rotated away from the leaders | ENERGYDEV +48%, RUSHIL +15%, GMBREW +11% | UGARSUGAR -43%, DALMIASUG -31%, UTTAMSUGAR -27% |
| 2016-09 | +3.9% | +0.4% | +3.5% | leaders kept leading | BODALCHEM +32%, ENERGYDEV +31%, KIRIINDUS +15% | TATAMETALI -13%, ARSSINFRA -9%, UPERGANGES -8% |
| 2016-10 | +3.1% | +5.0% | -1.9% | moved with the market | MANAPPURAM +12%, PRICOL +10%, DALMIASUG +10% | SORILINFRA -5%, UPERGANGES -5%, TATAMETALI -2% |
| 2016-11 | -24.8% | -8.4% | -16.5% | leaders fell harder than the market | DWARKESH +9%, RPGLIFE +3%, OUDHSUG -1% | ENERGYDEV -73%, UGARSUGAR -34%, KAKATCEM -33% |
| 2016-12 | -0.4% | -2.2% | +1.8% | moved with the market | ENERGYDEV +24%, LAKSHMIEFL +14%, DWARKESH +11% | SORILINFRA -20%, MANAPPURAM -13%, HSCL -11% |
| 2017-01 | +11.2% | +7.3% | +3.9% | leaders kept leading | HSCL +26%, OUDHSUG +26%, DWARKESH +24% | RBL -2%, SUMEETINDS +0%, CHEMFALKAL +1% |
| 2017-02 | +4.6% | +4.8% | -0.2% | moved with the market | TATAMETALI +43%, APTECHT +28%, GNFC +11% | IMFA -4%, SORILINFRA -3%, RUSHIL -2% |
| 2017-03 | +3.2% | +4.3% | -1.0% | moved with the market | JSLHISAR +24%, IMFA +21%, ESCORTS +20% | LAKSHMIEFL -20%, OUDHSUG -7%, KIRIINDUS -6% |
| 2017-04 | +1.6% | +5.7% | -4.1% | leadership rotated away from the leaders | PCBL +29%, HSCL +28%, TATAMETALI +16% | SHILPI -45%, IMFA -24%, LAKSHMIEFL -9% |
| 2017-05 | -7.4% | -3.1% | -4.3% | leaders fell harder than the market | ESCORTS +27%, STARPAPER +6%, PCBL +3% | SHILPI -71%, ITI -35%, IMFA -28% |
| 2017-06 | +5.0% | +0.8% | +4.2% | leaders kept leading | VENKEYS +40%, PCBL +39%, HSCL +31% | RECLTD -11%, INDIANB -11%, ATLANTAA -10% |
| 2017-07 | +8.8% | +5.0% | +3.7% | leaders kept leading | TIRUMALCHM +48%, JSLHISAR +35%, VENKEYS +25% | MOTILALOFS -7%, PCBL -4%, JAYBARMARU -2% |
| 2017-08 | +14.2% | -0.2% | +14.4% | leaders kept leading | V2RETAIL +56%, APTECHT +48%, VISAKAIND +44% | PRAKASH -16%, VENKEYS -6%, ESCORTS -3% |
| 2017-09 | +9.3% | -0.3% | +9.6% | leaders kept leading | ITI +37%, HEGAM +35%, RAIN +24% | VISAKAIND -13%, SINTEX -13%, SHAKTIPUMP -9% |
| 2017-10 | +32.8% | +10.6% | +22.2% | leaders kept leading | HEGAM +83%, BEPL +71%, GOACARBON +62% | SHAKTIPUMP -4%, JAYBARMARU -3%, FRETAIL -1% |
| 2017-11 | +8.5% | +2.1% | +6.5% | leaders kept leading | BEPL +38%, RAIN +31%, GRAPHITE +20% | ADANIENSOL -12%, SHAKTIPUMP -10%, GEOJITFSL -8% |
| 2017-12 | +6.1% | +4.6% | +1.5% | moved with the market | HEGAM +34%, BOMDYEING +25%, GRAPHITE +19% | GENESYS -9%, HSCL -6%, V2RETAIL -6% |
| 2018-01 | +0.8% | -2.3% | +3.1% | leaders kept leading | PCBL +24%, HEGAM +16%, HSCL +15% | BOMDYEING -18%, SAREGAMA -14%, AVANTIFEED -13% |
| 2018-02 | +4.3% | -4.3% | +8.6% | leaders fell less than the market | VENKEYS +45%, BOMDYEING +13%, AVANTIFEED +8% | GRAPHITE -11%, ONIDA -10%, HSCL -9% |
| 2018-03 | -2.7% | -7.2% | +4.5% | leaders fell less than the market | HEGAM +13%, GRAPHITE +8%, GRAVITA +0% | TINPLATE -20%, KOLTEPATIL -15%, ACE -11% |
| 2018-04 | +11.9% | +8.1% | +3.9% | leaders kept leading | DHANI +98%, NATHBIOGEN +36%, INDIAGLYCO +33% | GOACARBON -17%, RAIN -15%, ADANIENSOL -13% |
| 2018-05 | -11.4% | -6.5% | -4.9% | leaders fell harder than the market | GRAPHITE +27%, HEGAM +27%, SAREGAMA +12% | AVANTIFEED -34%, RAIN -27%, BEPL -24% |
| 2018-06 | -15.4% | -7.2% | -8.2% | leaders fell harder than the market | DHANI +4%, GPIL +3%, BEPL -1% | ONIDA -28%, VENKEYS -22%, ACE -22% |
| 2018-07 | +13.0% | +3.2% | +9.8% | leaders kept leading | HEGAM +30%, GRAPHITE +21%, INDIAGLYCO +21% | GOACARBON -18%, GPIL -8%, SAREGAMA -7% |
| 2018-08 | +17.6% | +4.1% | +13.6% | leaders kept leading | SORILINFRA +91%, GOACARBON +53%, GSS +45% | INDIAGLYCO -8%, TEAMLEASE -4%, LTM -4% |
| 2018-09 | -26.6% | -15.1% | -11.5% | leaders fell harder than the market | LTM +7%, SONATSOFTW +5%, GSS +1% | VIPIND -34%, JAICORPLTD -32%, NELCO -32% |
| 2018-10 | +5.9% | -1.0% | +6.9% | leaders kept leading | HEGAM +28%, PGHL +20%, RADICO +13% | MINDTREE -18%, SONATSOFTW -17%, JUBLFOOD -12% |
| 2018-11 | -4.5% | +1.8% | -6.3% | leadership rotated away from the leaders | GSS +36%, VMART +12%, MINDTREE +3% | GPIL -24%, ZENSARTECH -13%, WSTCSTPAPR -12% |
| 2018-12 | -4.0% | +2.3% | -6.3% | leadership rotated away from the leaders | IBULLSLTD +22%, LTM +10%, LTTS +10% | GRAPHITE -19%, HEGAM -11%, WSTCSTPAPR -10% |
| 2019-01 | -13.0% | -5.9% | -7.1% | leaders fell harder than the market | IOLCP +22%, SAKUMA +15%, COFORGE +14% | HEGAM -35%, EXCELINDUS -23%, ADANIENT -15% |
| 2019-02 | -3.3% | -1.6% | -1.7% | moved with the market | BATAINDIA +15%, BAJFINANCE +3%, NELCO +3% | DHANI -18%, UNIVCABLES -17%, VIPIND -15% |
| 2019-03 | +5.1% | +10.0% | -4.8% | momentum crash: rebound led by beaten-down stocks | USHAMART +24%, PGHL +17%, BAJFINANCE +14% | SAKUMA -18%, BIRLACABLE -3%, ASTRAZEN -2% |
| 2019-04 | -1.4% | -2.7% | +1.3% | moved with the market | SAKUMA +24%, ASTRAZEN +19%, GSS +12% | USHAMART -20%, BIRLACABLE -14%, PRAJIND -12% |
| 2019-05 | +3.0% | +1.5% | +1.6% | moved with the market | IOLCP +20%, VINATIORGA +20%, CGCL +18% | ASTRAZEN -16%, BIRLACABLE -14%, BATAINDIA -9% |
| 2019-06 | -4.7% | -5.5% | +0.8% | moved with the market | NAUKRI +9%, BATAINDIA +9%, ASTRAZEN +8% | SAKUMA -45%, BIRLACABLE -20%, DHAMPURSUG -16% |
| 2019-07 | -11.4% | -11.1% | -0.3% | moved with the market | ADANIPOWER +19%, PGHL +15%, BALRAMCHIN +2% | AVADHSUGAR -33%, DCMSHRIRAM -29%, SOLARA -26% |
| 2019-08 | -2.4% | -2.6% | +0.2% | moved with the market | SOLARA +32%, VINATIORGA +17%, RECLTD +3% | TANLA -14%, PGHL -13%, DALMIASUG -12% |
| 2019-09 | +9.4% | +5.2% | +4.2% | leaders kept leading | DHAMPURSUG +42%, CGCL +41%, BALRAMCHIN +16% | ICICIGI -4%, SRF -1%, NAUKRI -0% |
| 2019-10 | +0.4% | +2.7% | -2.3% | moved with the market | MANAPPURAM +20%, SOLARA +14%, ICICIGI +8% | INDIGO -22%, JUSTDIAL -15%, CREDITACC -6% |
| 2019-11 | -1.7% | +0.6% | -2.3% | moved with the market | CREDITACC +26%, HDFCAMC +18%, AAVAS +11% | 63MOONS -13%, KEI -12%, BATAINDIA -10% |
| 2019-12 | +1.6% | +0.0% | +1.6% | moved with the market | ADANIGREEN +21%, MANAPPURAM +15%, AAVAS +12% | KEI -12%, HDFCAMC -10%, MAHSCOOTER -6% |
| 2020-01 | +7.2% | +4.8% | +2.4% | moved with the market | DIXON +23%, RELAXO +20%, IGL +19% | ABBOTINDIA -4%, HDFCAMC -1%, AAVAS +1% |
| 2020-02 | -7.7% | -6.5% | -1.1% | moved with the market | NAM-INDIA +14%, CREDITACC +10%, ISEC +6% | AVANTIFEED -30%, ADANIENSOL -24%, GRSE -23% |
| 2020-03 | -26.6% | -30.0% | +3.4% | leaders fell less than the market | ADANIGREEN -1%, DIXON -6%, GMMPFAUDLR -9% | CREDITACC -60%, RELIGARE -51%, BFUTILITIE -47% |
| 2020-04 | +21.7% | +17.4% | +4.3% | leaders kept leading | SUVEN +115%, ALKYLAMINE +49%, ORISSAMINE +48% | ORIENTELEC -6%, NAM-INDIA -1%, BERGEPAINT +2% |
| 2020-05 | -0.7% | -2.0% | +1.3% | moved with the market | JBCHEPHARM +22%, ADANIGREEN +18%, AMBER +16% | SUVEN -26%, ALKEM -13%, IPCALAB -8% |
| 2020-06 | +12.6% | +15.6% | -2.9% | moved with the market | ADANIGREEN +44%, ISEC +23%, SUVEN +21% | ABBOTINDIA -6%, DEEPAKNTR -5%, NESTLEIND -2% |
| 2020-07 | +14.5% | +5.2% | +9.3% | leaders kept leading | IOLCP +74%, AARTIDRUGS +37%, DEEPAKNTR +35% | SUVEN -8%, SCI -5%, ADANIGREEN -5% |
| 2020-08 | +23.3% | +10.2% | +13.1% | leaders kept leading | AARTIDRUGS +56%, ALKYLAMINE +38%, ORISSAMINE +38% | ESCORTS -4%, IOLCP -3%, COROMANDEL -3% |
| 2020-09 | +15.5% | +0.6% | +14.9% | leaders kept leading | ADANIGREEN +63%, INDIAMART +36%, LAURUSLABS +24% | GMMPFAUDLR -29%, EPL -11%, ORISSAMINE -8% |
| 2020-10 | +3.4% | -0.2% | +3.6% | leaders kept leading | SHREDIGCEM +22%, ADANIGREEN +16%, TANLA +12% | AARTIDRUGS -12%, GMMPFAUDLR -11%, IOLCP -9% |
| 2020-11 | +27.6% | +12.5% | +15.1% | leaders kept leading | TANLA +80%, DHANI +38%, ALKYLAMINE +34% | ASTEC -16%, RAMCOSYS -5%, JBCHEPHARM -3% |
| 2020-12 | +14.0% | +7.8% | +6.2% | leaders kept leading | SUVEN +95%, ASTEC +36%, RAMCOSYS +35% | GRANULES -15%, ADANIGREEN -7%, ICIL -6% |
| 2021-01 | -5.7% | -0.0% | -5.7% | leadership rotated away from the leaders | ALKYLAMINE +25%, BALAMINES +21%, RAMCOSYS +9% | SUVEN -22%, KOPRAN -18%, CGPOWER -11% |
| 2021-02 | +22.0% | +11.7% | +10.3% | leaders kept leading | EVEREADY +60%, CGPOWER +42%, DIXON +40% | IOLCP -18%, ESTER -11%, RAMCOSYS -10% |
| 2021-03 | -4.4% | +0.6% | -5.0% | leadership rotated away from the leaders | CGPOWER +19%, ALKYLAMINE +13%, ESTER +12% | EVEREADY -13%, BORORENEW -13%, KOPRAN -13% |
| 2021-04 | +14.1% | +4.5% | +9.7% | leaders kept leading | KOPRAN +61%, BALAMINES +47%, MASTEK +35% | RAMCOSYS -8%, INTELLECT -8%, KELLTONTEC -8% |
| 2021-05 | +20.8% | +10.1% | +10.8% | leaders kept leading | ADANIENSOL +40%, PRINCEPIPE +37%, ADANIGREEN +24% | NEULANDLAB -16%, TEJASNET -8%, DIXON -4% |
| 2021-06 | -0.3% | +6.0% | -6.3% | leadership rotated away from the leaders | GPIL +36%, LAURUSLABS +31%, SURYAROSNI +15% | ADANIENSOL -28%, ATGL -24%, HINDCOPPER -15% |
| 2021-07 | +3.2% | +4.6% | -1.4% | moved with the market | ONMOBILE +24%, BALAMINES +22%, ALKYLAMINE +22% | KELLTONTEC -17%, RAMCOSYS -13%, LAURUSLABS -7% |
| 2021-08 | -0.9% | -1.9% | +1.0% | moved with the market | BALAMINES +24%, KPITTECH +20%, ELECON +19% | HINDCOPPER -23%, RAMCOSYS -15%, INTELLECT -13% |
| 2021-09 | +4.8% | +5.8% | -1.0% | moved with the market | ICIL +26%, MASTEK +21%, TATAELXSI +17% | CENTRUM -13%, TATASTEEL -11%, HINDCOPPER -8% |
| 2021-10 | +2.3% | -0.3% | +2.6% | moved with the market | BORORENEW +46%, GREENPANEL +25%, JSL +18% | BALAMINES -23%, GRAPHITE -11%, MAXHEALTH -8% |
| 2021-11 | -2.1% | -2.9% | +0.8% | moved with the market | ELECON +21%, ADANIENT +17%, POONAWALLA +9% | ANGELONE -18%, TNPETRO -18%, TIRUMALCHM -17% |
| 2021-12 | +8.1% | +3.7% | +4.4% | leaders kept leading | GRAVITA +50%, FLUOROCHEM +23%, POONAWALLA +21% | ELECON -11%, TEJASNET -8%, HGINFRA -5% |
| 2022-01 | +9.0% | +0.7% | +8.3% | leaders kept leading | TATAELXSI +30%, POONAWALLA +29%, GREENPANEL +24% | HIKAL -20%, HAPPSTMNDS -11%, IEX -7% |
| 2022-02 | -11.6% | -8.0% | -3.6% | leaders fell harder than the market | RENUKA +1%, BSE +1%, GRAVITA -0% | OLECTRA -25%, RTNINDIA -22%, GOLDIAM -18% |
| 2022-03 | +11.3% | +4.9% | +6.4% | leaders kept leading | BSE +51%, DWARKESH +41%, ATGL +35% | GRAVITA -6%, HLEGLAS -3%, ELECON -3% |
| 2022-04 | +4.1% | +2.9% | +1.2% | moved with the market | RENUKA +51%, MIRZAINT +32%, ANGELONE +27% | GLOBUSSPR -13%, JSL -10%, JSLHISAR -8% |
| 2022-05 | -13.2% | -7.7% | -5.5% | leaders fell harder than the market | RTNINDIA +15%, GOKEX +11%, MIRZAINT +4% | STEELXIND -27%, ANGELONE -24%, GLOBUSSPR -23% |
| 2022-06 | -10.5% | -6.3% | -4.1% | leaders fell harder than the market | USHAMART +4%, MIRZAINT +4%, RIIL +3% | BCG -51%, JSWENERGY -25%, GOKEX -22% |
| 2022-07 | +9.3% | +9.9% | -0.6% | moved with the market | BCG +58%, BLS +25%, FLUOROCHEM +20% | TTML -11%, VRLLOG -0%, GOKEX +1% |
| 2022-08 | +8.8% | +6.1% | +2.7% | moved with the market | ADANIPOWER +32%, TEJASNET +31%, MIRZAINT +30% | BORORENEW -8%, TRIDENT -8%, OLECTRA -3% |
| 2022-09 | -5.0% | -2.2% | -2.8% | moved with the market | FCL +28%, SHOPERSTOP +20%, BLS +9% | NDTV -21%, CHENNPETRO -20%, GMDCLTD -18% |
| 2022-10 | +1.0% | +1.6% | -0.6% | moved with the market | WSTCSTPAPR +23%, RAYMOND +17%, ELGIEQUIP +15% | RAJRATAN -29%, KPIGREEN -17%, SCHAEFFLER -14% |
| 2022-11 | +3.4% | +3.1% | +0.3% | moved with the market | KPIGREEN +34%, ELECON +22%, ADANIENT +17% | DEEPAKFERT -17%, ADANIENSOL -13%, FCL -12% |
| 2022-12 | -5.1% | -2.3% | -2.8% | moved with the market | APARINDS +22%, KARURVYSYA +13%, RAYMOND +8% | FCL -21%, MIRZAINT -20%, BLS -19% |
| 2023-01 | -5.6% | -2.7% | -2.9% | moved with the market | BLS +11%, ELECON +6%, KPIGREEN +4% | PCJEWELLER -40%, NDTV -28%, ADANIENT -23% |
| 2023-02 | -10.9% | -4.1% | -6.8% | leaders fell harder than the market | APARINDS +36%, VBL +13%, POWERMECH +7% | ADANIENT -54%, PCJEWELLER -46%, ADANIPOWER -35% |
| 2023-03 | +3.3% | -0.1% | +3.5% | leaders kept leading | TITAGARH +26%, KIRLOSENG +26%, RVNL +19% | RAMASTEEL -12%, FACT -12%, MAZDOCK -8% |
| 2023-04 | +9.3% | +7.8% | +1.5% | moved with the market | TITAGARH +27%, UCOBANK +24%, ATULAUTO +22% | KARURVYSYA -6%, IONEXCHANG -4%, KTKBANK -1% |
| 2023-05 | +6.6% | +5.2% | +1.4% | moved with the market | ELECON +22%, POWERMECH +21%, TDPOWERSYS +19% | UCOBANK -13%, FINCABLES -10%, KAMDHENU -9% |
| 2023-06 | +19.3% | +6.6% | +12.7% | leaders kept leading | KPIGREEN +66%, MAZDOCK +54%, FACT +45% | KIRLOSENG -3%, PSB -1%, RVNL +2% |
| 2023-07 | +19.6% | +7.2% | +12.4% | leaders kept leading | MAZDOCK +52%, POWERMECH +37%, TITAGARH +29% | HARIOMPIPE -12%, APTECHT -11%, SAKSOFT -0% |
| 2023-08 | +16.2% | +4.7% | +11.5% | leaders kept leading | JWL +67%, ZENTEC +36%, APARINDS +32% | NUCLEUS -10%, POWERMECH -8%, SDBL -6% |
| 2023-09 | +4.4% | +2.9% | +1.5% | moved with the market | RVNL +29%, MAZDOCK +19%, FACT +16% | ACE -10%, RKFORGE -10%, IONEXCHANG -9% |
| 2023-10 | +1.4% | -2.1% | +3.5% | leaders kept leading | FACT +40%, JINDALSAW +28%, SUZLON +19% | USHAMART -13%, SDBL -11%, MAZDOCK -10% |
| 2023-11 | +11.1% | +8.4% | +2.7% | moved with the market | TITAGARH +27%, RKFORGE +24%, RECLTD +19% | GENUSPOWER -11%, SDBL -8%, FACT -7% |
| 2023-12 | +6.2% | +7.8% | -1.6% | moved with the market | TARIL +26%, HBLENGINE +21%, RECLTD +18% | AGI -14%, JINDALSAW -11%, BSE -10% |
| 2024-01 | +20.2% | +7.6% | +12.6% | leaders kept leading | ELECTCAST +53%, TARIL +52%, JINDALSAW +31% | TITAGARH -2%, AGI +0%, APARINDS +4% |
| 2024-02 | -4.8% | -0.1% | -4.8% | leadership rotated away from the leaders | KPIGREEN +37%, INOXWIND +26%, ANANDRATHI +20% | IRFC -16%, TITAGARH -14%, NLCINDIA -14% |
| 2024-03 | -5.9% | -3.8% | -2.1% | moved with the market | ELECTCAST +12%, BSE +6%, RVNL +2% | PATELENG -16%, TEXRAIL -15%, IFCI -14% |
| 2024-04 | +17.4% | +9.0% | +8.4% | leaders kept leading | COCHINSHIP +50%, INOXWIND +20%, DBREALTY +20% | PATELENG +1%, ELECTCAST +8%, ANANDRATHI +8% |
| 2024-05 | +4.4% | -1.1% | +5.5% | leaders kept leading | JWL +51%, COCHINSHIP +42%, HUDCO +20% | MRPL -21%, ELECTCAST -18%, INOXWIND -13% |
| 2024-06 | +3.9% | +8.6% | -4.7% | leadership rotated away from the leaders | KALYANKJIL +29%, GMRP&UI +27%, JWL +14% | HINDCOPPER -10%, ANANDRATHI -7%, SJVN -6% |
| 2024-07 | +14.5% | +6.5% | +8.1% | leaders kept leading | IFCI +42%, SUZLON +31%, INOXWIND +29% | JWL -12%, SOBHA -8%, ANANDRATHI -3% |
| 2024-08 | -3.0% | +0.5% | -3.5% | leadership rotated away from the leaders | GMRP&UI +41%, TRENT +23%, BSE +11% | COCHINSHIP -28%, GRSE -25%, IFCI -14% |
| 2024-09 | -1.0% | +1.6% | -2.5% | moved with the market | ANANTRAJ +18%, GMRP&UI +16%, SOBHA +15% | OIL -22%, HUDCO -14%, RVNL -13% |
| 2024-10 | -7.9% | -6.0% | -1.9% | moved with the market | MOTILALOFS +23%, NEULANDLAB +18%, MCX +15% | GMRP&UI -26%, NBCC -22%, ELECTCAST -22% |
| 2024-11 | -2.5% | -0.1% | -2.4% | moved with the market | WOCKPHARMA +16%, NEULANDLAB +14%, PGEL +14% | BASF -21%, INOXGREEN -15%, INOXWIND -15% |
| 2024-12 | +2.9% | -0.4% | +3.3% | leaders kept leading | SHAKTIPUMP +37%, ANANTRAJ +27%, POWERINDIA +20% | NEULANDLAB -18%, JUBLPHARMA -10%, WABAG -8% |
| 2025-01 | -13.9% | -7.1% | -6.8% | leaders fell harder than the market | STAR +4%, NEULANDLAB +3%, WOCKPHARMA +0% | MOTILALOFS -33%, OFSS -29%, GRWRHITECH -27% |
| 2025-02 | -15.9% | -12.4% | -3.5% | leaders fell harder than the market | GRWRHITECH +8%, PGEL -1%, WABAG -3% | ZENTEC -42%, DHANI -29%, ANANTRAJ -27% |
| 2025-03 | +13.7% | +8.9% | +4.9% | leaders kept leading | ZENTEC +41%, TARIL +39%, LLOYDSME +26% | DIXON -5%, EPACK -0%, GOLDIAM +2% |
| 2025-04 | -2.4% | +2.7% | -5.1% | leadership rotated away from the leaders | DIXON +25%, BSE +16%, MAZDOCK +16% | GRWRHITECH -19%, SARDAEN -12%, WABAG -12% |
| 2025-05 | +14.1% | +9.0% | +5.1% | leaders kept leading | GRSE +57%, GRWRHITECH +47%, BALUFORGE +37% | CARTRADE -9%, PGEL -9%, SARDAEN -3% |
| 2025-06 | -0.1% | +3.7% | -3.8% | leadership rotated away from the leaders | WOCKPHARMA +17%, DEEPAKFERT +15%, SHAKTIPUMP +10% | GRWRHITECH -11%, KIRIINDUS -11%, WEBELSOLAR -10% |
| 2025-07 | -2.6% | -2.8% | +0.3% | moved with the market | PARADEEP +35%, PAYTM +18%, PGEL +8% | GRWRHITECH -18%, INDIAGLYCO -17%, MAZDOCK -15% |
| 2025-08 | -2.0% | -2.9% | +1.0% | moved with the market | GODFRYPHLP +21%, AIIL +16%, GABRIEL +11% | BLUEJET -17%, WOCKPHARMA -14%, LLOYDSME -14% |
| 2025-09 | -2.4% | +1.9% | -4.3% | leadership rotated away from the leaders | CUPID +25%, APOLLO +24%, AMBER +11% | FORCEMOT -14%, SHARDACROP -13%, JMFINANCIL -10% |
| 2025-10 | +2.6% | +4.0% | -1.4% | moved with the market | CARTRADE +23%, PAYTM +16%, LAURUSLABS +13% | APOLLO -15%, PARADEEP -15%, KRN -6% |
| 2025-11 | +4.2% | -2.0% | +6.2% | leaders kept leading | CUPID +41%, LUMAXTECH +36%, LTF +15% | GABRIEL -19%, VIMTALABS -16%, AIIL -7% |
| 2025-12 | +7.3% | -0.4% | +7.7% | leaders kept leading | CUPID +57%, SMLMAH +30%, ASHAPURMIN +28% | SHAILY -13%, GRSE -12%, TFCILTD -11% |
| 2026-01 | -9.6% | -5.2% | -4.4% | leaders fell harder than the market | GRSE +13%, TDPOWERSYS +4%, GRMOVER +1% | CUPID -23%, GARUDA -20%, JAYNECOIND -17% |
| 2026-02 | +5.5% | +3.6% | +1.9% | moved with the market | LUMAXTECH +37%, SMLMAH +36%, FORCEMOT +30% | CARTRADE -30%, STALLION -27%, HINDCOPPER -5% |
| 2026-03 | -9.1% | -11.4% | +2.3% | moved with the market | PFOCUS +29%, NATIONALUM +9%, CUPID +0% | APOLLO -23%, SMLMAH -21%, FORCEMOT -20% |
| 2026-04 | +29.1% | +17.8% | +11.3% | leaders kept leading | MTARTECH +86%, QPOWER +71%, STLTECH +67% | PFOCUS -6%, SMLMAH -1%, FORCEMOT +3% |
| 2026-05 | +11.5% | +1.8% | +9.7% | leaders kept leading | STLTECH +82%, BAJAJCON +23%, MTARTECH +22% | PFOCUS -25%, QPOWER -23%, JAYNECOIND -8% |
| 2026-06 | +11.7% | +2.7% | +9.0% | leaders kept leading | THANGAMAYL +52%, CUPID +47%, BLISSGVS +27% | NATIONALUM -20%, JAYNECOIND -17%, IMFA -12% |
| 2026-07 | +1.4% | +1.7% | -0.3% | moved with the market | CUPID +21%, ATHERENERG +10%, KMEW +7% | THANGAMAYL -18%, BLISSGVS -14%, BAJAJCON -13% |
| 2026-08 | +16.2% | +1.3% | +14.9% | leaders kept leading | ATHERENERG +36%, TDPOWERSYS +36%, PRECWIRE +36% | KERNEX -24%, BAJAJCON -10%, PAISALO -5% |
| 2026-09 | +6.4% | -3.9% | +10.3% | leaders fell less than the market | SBC +38%, SHREEJISPG +20%, PAISALO +14% | ATHERENERG -17%, RRKABEL -14%, HINDCOPPER -10% |
| 2026-10 | -1.6% | -5.2% | +3.6% | leaders fell less than the market | ATHERENERG +17%, ACUTAAS +16%, SKYGOLD +15% | KIRLOSENG -18%, RPTECH -15%, SHILPAMED -14% |

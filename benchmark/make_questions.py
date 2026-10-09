"""Write benchmark/questions.json - the questions, expected answers and evidence.

This file is the source of truth for the question set; edit it here and run

    backend/.venv/Scripts/python benchmark/make_questions.py
    backend/.venv/Scripts/python benchmark/run.py check

Answer patterns: "num:184.6" (number in English or Finnish notation),
"re:..." (case-insensitive regex), anything else = case-insensitive substring.
Evidence locators are the ones the app's parsers produce ("Page 3",
"Heading: Decisions", "Slide 4", "Sheet: Sites").

Difficulty: "standard" questions can be answered by finding one passage;
"hard" ones need several facts combined, arithmetic, negation, or resisting
a near-miss trap. "derived" answers (sums, differences, counts) are computed
from the documents and therefore do not appear in them literally.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "questions.json"

# Locators, as the app's parsers produce them.
P = lambda n: {"doc": "report", "locator": f"Page {n}"}
S = lambda n: {"doc": "slides", "locator": f"Slide {n}"}
MIN = {
    "details": {"doc": "minutes", "locator": {"en": "Heading: Meeting details", "fi": "Heading: Kokouksen tiedot"}},
    "status": {"doc": "minutes", "locator": {"en": "Heading: Project status", "fi": "Heading: Hankkeiden tilanne"}},
    "safety": {"doc": "minutes", "locator": {"en": "Heading: Safety", "fi": "Heading: Turvallisuus"}},
    "decisions": {"doc": "minutes", "locator": {"en": "Heading: Decisions", "fi": "Heading: Päätökset"}},
    "actions": {"doc": "minutes", "locator": {"en": "Heading: Action items", "fi": "Heading: Toimenpiteet"}},
    "next": {"doc": "minutes", "locator": {"en": "Heading: Next meeting", "fi": "Heading: Seuraava kokous"}},
}
SITES = {"doc": "register", "locator": {"en": "Sheet: Sites", "fi": "Sheet: Kohteet"}}
INCIDENTS = {"doc": "register", "locator": {"en": "Sheet: Incidents", "fi": "Sheet: Tapaturmat"}}

CEO, MARKET, KEY, PROJECTS, CUSTOMERS, PERSONNEL, SUSTAIN, RISK, GOV = (P(i) for i in range(1, 10))


def date(day, month_no, month_en, month_fi_part, year):
    return [
        rf"re:\b{day}\.\s?{month_no}\.\s?{year}",
        rf"re:\b{day}(st|nd|rd|th)?\s+(of\s+)?{month_en}",
        rf"re:{month_en}\s+{day}\b",
        rf"re:\b{day}\.?\s+{month_fi_part}",
        rf"re:{year}-{month_no:02d}-{day:02d}",
    ]


def site(name, *stems):
    return {"name": name, "match": list(stems)}


SITE_UNIVERSE = {
    "Pohjankangas": ["pohjanka"], "Lumivaara": ["lumivaar"], "Ristineva": ["ristinev"], "Tervaharju": ["tervaharj"],
    "Kivijärvi": ["kivijärv"], "Haukilahti": ["haukilah"], "Koskenniska": ["koskennisk"], "Hietasaari": ["hietasaar"],
    "Vanhalinna": ["vanhalinn"],
}
SUPPLIER_UNIVERSE = {"Nordwind Turbines": ["nordwind"], "Helios Grid Systems": ["helios"], "Voltmark": ["voltmark"],
                     "Baltic Cable Works": ["baltic cable"]}


def item(name, universe, evidence):
    return {"name": name, "match": universe[name], "evidence": evidence}


questions = [
    # ------------------------------------------------------------ details
    dict(id="D01", category="detail", cross=True,
         question={"en": "What was Kuusiranta Energy's revenue in 2025?", "fi": "Mikä oli Kuusiranta Energian liikevaihto vuonna 2025?"},
         answer=["num:184.6"], evidence=[KEY, CEO], note="2024 value 171.3 is on the same page"),
    dict(id="D02", category="detail", cross=True,
         question={"en": "What was the company's average selling price of electricity in 2025?", "fi": "Mikä oli yhtiön sähkön keskimääräinen myyntihinta vuonna 2025?"},
         answer=["num:61.40", "num:61.4"], evidence=[KEY], note="distractor: Nordic system price 41.20 on page 2"),
    dict(id="D03", category="detail",
         question={"en": "How many employees did the company have at the end of 2025?", "fi": "Montako työntekijää yhtiöllä oli vuoden 2025 lopussa?"},
         answer=["num:412"], evidence=[PERSONNEL, KEY]),
    dict(id="D04", category="detail", cross=True,
         question={"en": "What was the lost-time injury frequency (LTIF) in 2025?", "fi": "Mikä oli tapaturmataajuus (LTIF) vuonna 2025?"},
         answer=["num:5.1"], evidence=[PERSONNEL], note="2024 value 6.8 and target 3.0 are distractors"),
    dict(id="D05", category="detail",
         question={"en": "How many near-miss reports were filed in 2025?", "fi": "Montako läheltä piti -ilmoitusta tehtiin vuonna 2025?"},
         answer=["num:27"], evidence=[PERSONNEL]),
    dict(id="D06", category="detail", cross=True,
         question={"en": "How much did the repair of the Pohjankangas cable cost?", "fi": "Paljonko Pohjankankaan kaapelin korjaus maksoi?"},
         answer=["num:1.3"], evidence=[PROJECTS]),
    dict(id="D07", category="detail",
         question={"en": "For how many days was the Pohjankangas wind farm partially out of operation?", "fi": "Kuinka monta päivää Pohjankankaan tuulipuisto oli osittain pois käytöstä?"},
         answer=["num:19"], evidence=[PROJECTS]),
    dict(id="D08", category="detail", cross=True,
         question={"en": "What is the number of the turbine supply contract with Nordwind Turbines?", "fi": "Mikä on Nordwind Turbinesin kanssa tehdyn voimaloiden toimitussopimuksen numero?"},
         answer=["2025-0417"], evidence=[MIN["status"]]),
    dict(id="D09", category="detail",
         question={"en": "Who is the project manager of the Hietasaari battery storage?", "fi": "Kuka on Hietasaaren akkuvaraston projektipäällikkö?"},
         answer=[r"re:koski(nen|se)"], evidence=[MIN["details"], MIN["status"]]),
    dict(id="D10", category="detail", cross=True,
         question={"en": "What is the new commissioning date of the Hietasaari battery storage?", "fi": "Mikä on Hietasaaren akkuvaraston uusi käyttöönottopäivä?"},
         answer=date(14, 8, "august", "elokuu", 2026) + [r"re:elokuun\s+14"], evidence=[MIN["status"]],
         note="the old date 30 April 2026 is in the same sentence"),
    dict(id="D11", category="detail",
         question={"en": "What is the budget of the Hietasaari battery storage project?", "fi": "Mikä on Hietasaaren akkuvarastohankkeen budjetti?"},
         answer=["num:24.5"], evidence=[MIN["status"]]),
    dict(id="D12", category="detail",
         question={"en": "How many of the Ristineva turbine foundations have been completed?", "fi": "Kuinka moni Ristinevan voimaloiden perustuksista on valmiina?"},
         answer=["num:6", r"re:\bsix\b", r"re:\bkuusi\b"], evidence=[MIN["status"]]),
    dict(id="D13", category="detail",
         question={"en": "When is the next steering group meeting?", "fi": "Milloin on ohjausryhmän seuraava kokous?"},
         answer=date(16, 12, "december", "joulukuu", 2025), evidence=[MIN["next"]]),
    dict(id="D14", category="detail", cross=True,
         question={"en": "In which year was the Koskenniska hydropower plant commissioned?", "fi": "Minä vuonna Koskenniskan vesivoimalaitos otettiin käyttöön?"},
         answer=["num:1968"], evidence=[SITES]),
    dict(id="D15", category="detail",
         question={"en": "What is the capacity of the Lumivaara wind farm?", "fi": "Mikä on Lumivaaran tuulipuiston teho?"},
         answer=["num:54"], evidence=[SITES]),
    dict(id="D16", category="detail", cross=True,
         question={"en": "How many working days were lost in the vehicle accident at the Ristineva site?", "fi": "Montako työpäivää menetettiin Ristinevan työmaan ajoneuvo-onnettomuudessa?"},
         answer=["num:22"], evidence=[INCIDENTS]),
    dict(id="D17", category="detail",
         question={"en": "What will be the capacity of the electric boiler that replaces the Vanhalinna plant?", "fi": "Mikä on Vanhalinnan laitoksen korvaavan sähkökattilan teho?"},
         answer=["num:40"], evidence=[S(5)], note="the heat pumps (24 MW) are on the same slide"),
    dict(id="D18", category="detail",
         question={"en": "How large is the investment in the Ristineva wind farm?", "fi": "Kuinka suuri on Ristinevan tuulipuiston investointi?"},
         answer=["num:168"], evidence=[S(3)]),
    dict(id="D19", category="detail", cross=True,
         question={"en": "How much additional budget did the steering group approve for the Ristineva foundations?", "fi": "Kuinka suuren lisäbudjetin ohjausryhmä hyväksyi Ristinevan perustuksille?"},
         answer=["num:1.8"], evidence=[MIN["decisions"]]),
    dict(id="D20", category="detail",
         question={"en": "By how much did the turbine renovation increase the annual output of the Koskenniska plant?", "fi": "Kuinka paljon turbiinin peruskorjaus kasvatti Koskenniskan laitoksen vuosituotantoa?"},
         answer=[r"re:(?<![\d.,])4\s?(%|percent|per cent|prosent)"], evidence=[PROJECTS]),
    dict(id="D21", category="detail",
         question={"en": "In which municipality is the Hietasaari battery storage located?", "fi": "Missä kunnassa Hietasaaren akkuvarasto sijaitsee?"},
         answer=["oulu"], evidence=[SITES]),
    dict(id="D22", category="detail",
         question={"en": "Who is the CEO of Kuusiranta Energy?", "fi": "Kuka on Kuusiranta Energian toimitusjohtaja?"},
         answer=["lehtovaara"], evidence=[CEO]),
    dict(id="D23", category="detail", cross=True,
         question={"en": "Which company supplies the inverters for the Haukilahti solar park?", "fi": "Mikä yritys toimittaa invertterit Haukilahden aurinkopuistoon?"},
         answer=["helios"], evidence=[PROJECTS]),
    dict(id="D24", category="detail",
         question={"en": "How many hours of training did an employee receive on average in 2025?", "fi": "Montako tuntia koulutusta työntekijä sai keskimäärin vuonna 2025?"},
         answer=["num:31"], evidence=[PERSONNEL]),
    dict(id="D25", category="detail",
         question={"en": "Who chairs the company's board of directors?", "fi": "Kuka on yhtiön hallituksen puheenjohtaja?"},
         answer=["saarinen", "saarise"], evidence=[GOV], note="distractor: the CEO chairs the steering group"),
    dict(id="D26", category="detail",
         question={"en": "What share of the expected 2026 generation had been hedged at the end of 2025?", "fi": "Kuinka suuri osa vuoden 2026 odotetusta tuotannosta oli suojattu vuoden 2025 lopussa?"},
         answer=["num:70"], evidence=[RISK], note="2027 value 45 % is in the same sentence"),

    # --------------------------------------------------- similar items (lists)
    dict(id="L01", category="list", cross=True, universe="sites",
         question={"en": "List all of the company's wind farms, including those that are still being planned or built.",
                   "fi": "Luettele kaikki yhtiön tuulipuistot, myös suunnitteilla ja rakenteilla olevat."},
         items=[item("Pohjankangas", SITE_UNIVERSE, [SITES, PROJECTS]), item("Lumivaara", SITE_UNIVERSE, [SITES]),
                item("Ristineva", SITE_UNIVERSE, [SITES, PROJECTS, S(3), S(4)]), item("Tervaharju", SITE_UNIVERSE, [SITES, S(4), MIN["status"]])]),
    dict(id="L02", category="list", cross=True, universe="sites",
         question={"en": "Which projects are delayed or behind schedule?", "fi": "Mitkä hankkeet ovat viivästyneet tai aikataulusta jäljessä?"},
         items=[item("Ristineva", SITE_UNIVERSE, [PROJECTS, MIN["status"], S(3)]), item("Hietasaari", SITE_UNIVERSE, [MIN["status"]]),
                item("Haukilahti", SITE_UNIVERSE, [PROJECTS, MIN["status"]]), item("Tervaharju", SITE_UNIVERSE, [MIN["status"], S(4)])],
         note="Koskenniska finished on schedule; Pohjankangas had an outage, not a project delay"),
    dict(id="L03", category="list", universe="sites",
         question={"en": "At which sites did lost-time injuries occur in 2025?", "fi": "Missä kohteissa sattui poissaoloon johtaneita tapaturmia vuonna 2025?"},
         items=[item("Vanhalinna", SITE_UNIVERSE, [INCIDENTS, MIN["safety"]]), item("Koskenniska", SITE_UNIVERSE, [INCIDENTS]),
                item("Ristineva", SITE_UNIVERSE, [INCIDENTS, MIN["safety"]])]),
    dict(id="L04", category="list", cross=True, universe="suppliers",
         question={"en": "Which suppliers are mentioned in the documents?", "fi": "Mitä toimittajia asiakirjoissa mainitaan?"},
         items=[item("Nordwind Turbines", SUPPLIER_UNIVERSE, [PROJECTS, MIN["status"], S(3)]), item("Helios Grid Systems", SUPPLIER_UNIVERSE, [PROJECTS]),
                item("Voltmark", SUPPLIER_UNIVERSE, [MIN["status"], MIN["decisions"]]), item("Baltic Cable Works", SUPPLIER_UNIVERSE, [PROJECTS])]),
    dict(id="L05", category="list", universe="sites",
         question={"en": "Which sites are currently under construction?", "fi": "Mitkä kohteet ovat tällä hetkellä rakenteilla?"},
         items=[item("Ristineva", SITE_UNIVERSE, [SITES]), item("Haukilahti", SITE_UNIVERSE, [SITES]), item("Hietasaari", SITE_UNIVERSE, [SITES])]),
    dict(id="L06", category="list",
         question={"en": "What decisions did the steering group make at its meeting 4/2025?", "fi": "Mitä päätöksiä ohjausryhmä teki kokouksessaan 4/2025?"},
         items=[{"name": "Additional budget EUR 1.8 million", "match": ["num:1.8"], "evidence": [MIN["decisions"]]},
                {"name": "Contractor safety programme", "match": ["safety programme", "safety program", "turvallisuusohjelm"], "evidence": [MIN["decisions"]]},
                {"name": "Delivery guarantee from Voltmark", "match": ["guarantee", "takuu"], "evidence": [MIN["decisions"]]},
                {"name": "Tervaharju procurement postponed", "match": ["tervaharj"], "evidence": [MIN["decisions"]]}]),
    dict(id="L07", category="list",
         question={"en": "Who is responsible for the action items agreed at the steering group meeting?", "fi": "Ketkä vastaavat ohjausryhmän kokouksessa sovituista toimenpiteistä?"},
         items=[{"name": "Jari Nieminen", "match": [r"re:niemi(nen|se)"], "evidence": [MIN["actions"]]},
                {"name": "Elina Koskinen", "match": [r"re:koski(nen|se)"], "evidence": [MIN["actions"]]},
                {"name": "Sanna Virtanen", "match": [r"re:virta(nen|se)"], "evidence": [MIN["actions"]]}]),
    dict(id="L08", category="list",
         question={"en": "Which key risks are listed in the strategy presentation?", "fi": "Mitä keskeisiä riskejä strategiaesityksessä luetellaan?"},
         items=[{"name": "Permit appeals", "match": ["appeal", "valitu", "valitta"], "evidence": [S(6)]},
                {"name": "Supply chain delays", "match": ["supply chain", "toimitusket"], "evidence": [S(6)]},
                {"name": "Grid connection capacity", "match": ["grid connection", "verkkoliit"], "evidence": [S(6)]},
                {"name": "Electricity price volatility", "match": ["price", "hint"], "evidence": [S(6)]}]),

    # -------------------------------------------- not in the documents
    dict(id="U01", category="unanswerable", cross=True,
         question={"en": "What was Kuusiranta Energy's revenue in 2023?", "fi": "Mikä oli Kuusiranta Energian liikevaihto vuonna 2023?"},
         note="only 2024 and 2025 are reported"),
    dict(id="U02", category="unanswerable", cross=True,
         question={"en": "Who is the company's chief financial officer?", "fi": "Kuka on yhtiön talousjohtaja?"}),
    dict(id="U03", category="unanswerable",
         question={"en": "What is the capacity of the Haukilahti wind farm?", "fi": "Mikä on Haukilahden tuulipuiston teho?"},
         accept=["solar", "aurinko"], note="false premise: Haukilahti is a solar park"),
    dict(id="U04", category="unanswerable", cross=True,
         question={"en": "How many employees does the company have in Sweden?", "fi": "Montako työntekijää yhtiöllä on Ruotsissa?"}),
    dict(id="U05", category="unanswerable",
         question={"en": "What is the contract number of the Hietasaari transformer order?", "fi": "Mikä on Hietasaaren muuntajatilauksen sopimusnumero?"},
         note="only the Ristineva turbine contract number is given"),
    dict(id="U06", category="unanswerable",
         question={"en": "Who is the company's sustainability director?", "fi": "Kuka on yhtiön vastuullisuusjohtaja?"}),
    dict(id="U07", category="unanswerable", cross=True,
         question={"en": "What was the lost-time injury frequency in 2023?", "fi": "Mikä oli tapaturmataajuus vuonna 2023?"},
         note="only 2024 and 2025 are reported"),
    dict(id="U08", category="unanswerable",
         question={"en": "How many turbines will the Tervaharju wind farm have?", "fi": "Montako voimalaa Tervaharjun tuulipuistoon tulee?"},
         note="only the capacity (78 MW) is given; dividing by 6 MW would be a guess"),
]

# ------------------------------------------------------------------ hard tier
# Combine facts, compute, negate, or resist a near-miss. Added after the first
# results showed the standard tier near its ceiling for Qwen3.5-4B.
HARD = [
    dict(id="H01", category="detail", cross=True, derived=True,
         question={"en": "What is the combined capacity of the company's wind farms that are already in operation?",
                   "fi": "Mikä on yhtiön jo käytössä olevien tuulipuistojen yhteenlaskettu teho?"},
         answer=["num:150"], evidence=[SITES], note="Pohjankangas 96 MW + Lumivaara 54 MW; Ristineva and Tervaharju are not in operation"),
    dict(id="H02", category="detail", cross=True, derived=True,
         question={"en": "How many working days were lost in total because of lost-time injuries in 2025?",
                   "fi": "Kuinka monta työpäivää poissaoloon johtaneiden tapaturmien vuoksi menetettiin vuonna 2025 yhteensä?"},
         answer=["num:48"], evidence=[INCIDENTS], note="9 + 14 + 22 + 3"),
    dict(id="H03", category="detail",
         question={"en": "What was the original planned commissioning date of the Hietasaari battery storage, before it was postponed?",
                   "fi": "Mikä oli Hietasaaren akkuvaraston alkuperäinen suunniteltu käyttöönottopäivä ennen siirtoa?"},
         answer=date(30, 4, "april", "huhtikuu", 2026) + [r"re:huhtikuun\s+30"], evidence=[MIN["status"]],
         note="the new date 14 August 2026 is in the same sentence"),
    dict(id="H04", category="detail", cross=True,
         question={"en": "Which company supplies the turbines for the wind farm located in Pyhäjoki?",
                   "fi": "Mikä yritys toimittaa voimalat Pyhäjoella sijaitsevaan tuulipuistoon?"},
         answer=["nordwind"], evidence=[PROJECTS, S(3), MIN["status"]], note="two hops: Pyhäjoki -> Ristineva -> Nordwind Turbines"),
    dict(id="H05", category="detail",
         question={"en": "In which municipality is the plant where the chemical splash accident happened?",
                   "fi": "Missä kunnassa sijaitsee laitos, jolla kemikaaliroiske sattui?"},
         answer=["lieto", "liedo"], evidence=[SITES], note="two hops: chemical splash -> Vanhalinna -> Lieto"),
    dict(id="H06", category="detail", cross=True,
         question={"en": "At which site did the single injury with the most lost working days happen in 2025?",
                   "fi": "Missä kohteessa sattui vuonna 2025 tapaturma, josta menetettiin eniten työpäiviä?"},
         answer=["ristinev"], evidence=[INCIDENTS], note="comparison over the incident sheet (22 days)"),
    dict(id="H07", category="detail", derived=True,
         question={"en": "By how many people did the number of employees grow from the end of 2024 to the end of 2025?",
                   "fi": "Kuinka monella henkilöllä työntekijöiden määrä kasvoi vuoden 2024 lopusta vuoden 2025 loppuun?"},
         answer=["num:23"], evidence=[PERSONNEL, KEY], note="412 - 389"),
    dict(id="H08", category="detail", cross=True, derived=True,
         question={"en": "By how much did operating profit increase from 2024 to 2025?",
                   "fi": "Kuinka paljon liikevoitto kasvoi vuodesta 2024 vuoteen 2025?"},
         answer=["num:3.5"], evidence=[KEY], note="21.9 - 18.4 million euros"),
    dict(id="H09", category="list", cross=True, universe="sites",
         question={"en": "Which of the company's wind farms are not yet in operation?",
                   "fi": "Mitkä yhtiön tuulipuistoista eivät ole vielä käytössä?"},
         items=[item("Ristineva", SITE_UNIVERSE, [SITES]), item("Tervaharju", SITE_UNIVERSE, [SITES])],
         note="negation: the two operating wind farms must not be listed"),
    dict(id="H10", category="detail", derived=True,
         question={"en": "What is the total capacity of the equipment that will replace the Vanhalinna plant?",
                   "fi": "Mikä on Vanhalinnan laitoksen korvaavien laitteiden yhteenlaskettu teho?"},
         answer=["num:64"], evidence=[S(5)], note="two heat pumps 24 MW in total + electric boiler 40 MW"),
    dict(id="H11", category="unanswerable", cross=True,
         question={"en": "Which company supplied the transformer for the Pohjankangas wind farm?",
                   "fi": "Mikä yritys toimitti muuntajan Pohjankankaan tuulipuistoon?"},
         note="near miss: Voltmark supplies the Hietasaari transformer; Pohjankangas only got a cable (Baltic Cable Works)"),
    dict(id="H12", category="unanswerable",
         question={"en": "What is the company's lost-time injury frequency target for 2026?",
                   "fi": "Mikä on yhtiön tapaturmataajuustavoite vuodelle 2026?"},
         note="near miss: the only target is 'below 3.0 by 2028'"),
    dict(id="H13", category="detail",
         question={"en": "Who is responsible for reviewing the contract of the company that supplies the Hietasaari main transformer?",
                   "fi": "Kuka vastaa Hietasaaren päämuuntajan toimittajan sopimuksen tarkistamisesta?"},
         answer=[r"re:koski(nen|se)"], evidence=[MIN["actions"]], note="two hops: Hietasaari transformer -> Voltmark -> action item owner"),
    dict(id="H14", category="detail", cross=True, derived=True,
         question={"en": "How many lost-time injuries happened at the Vanhalinna plant in 2025?",
                   "fi": "Montako poissaoloon johtanutta tapaturmaa Vanhalinnan laitoksella sattui vuonna 2025?"},
         answer=["num:2", r"re:\btwo\b", r"re:\bkaksi\b", r"re:\bkahdesti\b"], evidence=[INCIDENTS],
         note="count over the incident sheet; the report gives only the company total (four)"),
    # Round 2: Qwen3.5-4B still scored 95 % on H01-H14; its one real weakness
    # was picking the largest value from a table (H06). These target that and
    # chain three facts.
    dict(id="H15", category="detail", cross=True,
         question={"en": "Which of the company's sites that are in operation has the largest capacity?",
                   "fi": "Millä yhtiön käytössä olevalla kohteella on suurin teho?"},
         answer=["pohjanka"], evidence=[SITES], note="trap: Ristineva (120 MW) is larger but under construction"),
    dict(id="H16", category="detail",
         question={"en": "Which of the company's sites that are still in operation was commissioned first?",
                   "fi": "Mikä yhtiön yhä käytössä olevista kohteista otettiin käyttöön ensimmäisenä?"},
         answer=["koskennisk"], evidence=[SITES], note="minimum over the commissioning column (1968)"),
    dict(id="H17", category="detail", cross=True, derived=True,
         question={"en": "On average, how many working days were lost per lost-time injury in 2025?",
                   "fi": "Montako työpäivää menetettiin keskimäärin yhtä poissaoloon johtanutta tapaturmaa kohden vuonna 2025?"},
         answer=["num:12"], evidence=[INCIDENTS], note="48 days / 4 injuries"),
    dict(id="H18", category="detail",
         question={"en": "What is the capacity of the site whose project manager is Elina Koskinen?",
                   "fi": "Mikä on sen kohteen teho, jonka projektipäällikkö on Elina Koskinen?"},
         answer=[r"re:\b30\s?MW"], evidence=[SITES, MIN["status"]], note="Koskinen -> Hietasaari -> 30 MW (not the 30 April date)"),
    dict(id="H19", category="detail", derived=True,
         question={"en": "How many megawatts more capacity do the wind farms that are not yet in operation have than the wind farms already in operation?",
                   "fi": "Kuinka monta megawattia enemmän tehoa on tuulipuistoilla, jotka eivät ole vielä käytössä, kuin jo käytössä olevilla tuulipuistoilla?"},
         answer=[r"re:\b48\s?MW"], evidence=[SITES], note="(120 + 78) - (96 + 54)"),
    dict(id="H20", category="detail", cross=True,
         question={"en": "On which date did the lost-time injury happen at the site whose turbine supply contract number is KR-2025-0417?",
                   "fi": "Minä päivänä sattui poissaoloon johtanut tapaturma siinä kohteessa, jonka voimaloiden toimitussopimuksen numero on KR-2025-0417?"},
         answer=date(21, 8, "august", "elokuu", 2025), evidence=[INCIDENTS, MIN["safety"]],
         note="three hops: contract -> Ristineva -> incident date"),
    dict(id="H21", category="list", cross=True, universe="sites",
         question={"en": "Which of the company's sites had no lost-time injuries in 2025?",
                   "fi": "Missä yhtiön kohteissa ei sattunut yhtään poissaoloon johtanutta tapaturmaa vuonna 2025?"},
         items=[item(n, SITE_UNIVERSE, [SITES]) for n in ("Pohjankangas", "Lumivaara", "Tervaharju", "Kivijärvi", "Haukilahti", "Hietasaari")],
         note="negation over two sheets; six items"),
    dict(id="H22", category="detail", derived=True,
         question={"en": "What percentage of the company's lost-time injuries in 2025 happened at the Vanhalinna plant?",
                   "fi": "Kuinka monta prosenttia yhtiön vuoden 2025 poissaoloon johtaneista tapaturmista sattui Vanhalinnan laitoksella?"},
         answer=[r"re:\b50\s?(%|percent|per cent|prosent)"], evidence=[INCIDENTS], note="2 of 4"),
]
for q in HARD:
    q["difficulty"] = "hard"
questions += HARD

suite = {
    "name": "Kuusiranta EN/FI document QA benchmark",
    "version": 2,
    "documents": {
        "report": {"en": "annual_report_2025.pdf", "fi": "vuosikertomus_2025.pdf"},
        "minutes": {"en": "steering_group_minutes_4_2025.docx", "fi": "ohjausryhman_poytakirja_4_2025.docx"},
        "slides": {"en": "strategy_2026_2030.pptx", "fi": "strategia_2026_2030.pptx"},
        "register": {"en": "site_register.xlsx", "fi": "kohderekisteri.xlsx"},
    },
    "document_order": ["report", "minutes", "slides", "register"],
    "universes": {"sites": SITE_UNIVERSE, "suppliers": SUPPLIER_UNIVERSE},
    "questions": questions,
}
OUT.write_text(json.dumps(suite, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(questions), "questions;", sum(1 for q in questions if q.get("cross")), "cross-lingual")

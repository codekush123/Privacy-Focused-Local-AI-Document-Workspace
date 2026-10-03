"""Text of the benchmark corpus, in English and Finnish.

The corpus describes a *fictional* company, Kuusiranta Energy Ltd, so a model
cannot answer from what it learned during training: every correct answer has
to come from the documents, and every invented one is a hallucination.

The two language versions contain exactly the same facts, written the way a
native document in each language would write them (Finnish uses decimal
commas, day.month.year dates and its own case endings). That is what lets the
benchmark compare English and Finnish on equal terms.

Facts are deliberately planted so that:
- similar items are scattered over several documents and formats
  (wind farms, delayed projects, injury sites, suppliers ...);
- small details sit inside long paragraphs next to a near-identical
  distractor (the 2025 value next to the 2024 value);
- some plausible questions have no answer in the documents at all.

The Finnish text is meant to be checked by the team's native Finnish speakers;
after editing it, run make_corpus.py and the suite self-check again.
"""
from __future__ import annotations

# --------------------------------------------------------------------------
# 1. Annual report (PDF, one section per page)
# --------------------------------------------------------------------------

REPORT = {
    "en": {
        "filename": "annual_report_2025.pdf",
        "title": "Kuusiranta Energy Ltd - Annual Report 2025",
        "pages": [
            ("Letter from the CEO", [
                "2025 was a year of steady growth for Kuusiranta Energy. Our revenue rose to EUR 184.6 million, and the "
                "share of renewable sources in our own electricity generation reached 87 percent. At the same time, "
                "several of our construction projects ran into difficulties, and we are not satisfied with how well our "
                "project portfolio kept to its schedules.",
                "We continued to invest in wind and solar power. The Kivijärvi solar park, completed in the spring of "
                "2024, had its first full year of operation and produced more electricity than its design estimate. "
                "Construction of the Ristineva wind farm, the largest investment in our history, made progress but is "
                "running behind its original schedule.",
                "Safety remains our first priority. The number of lost-time injuries fell compared with the previous "
                "year, but every injury is one too many. For that reason we will launch a new safety programme for "
                "contractors at the beginning of 2026.",
                "Kuusiranta Energy is headquartered in Harjuvesi. I want to thank our employees, customers and partners "
                "for their work during the year.",
                "Markus Lehtovaara, Chief Executive Officer",
            ]),
            ("Market environment", [
                "The average Nordic system price of electricity was EUR 41.20 per megawatt hour in 2025, compared with "
                "EUR 44.80 a year earlier. Prices varied strongly between seasons: the monthly average ranged from "
                "EUR 12 in June to EUR 96 in January. The price difference between the Finnish price area and the "
                "system price remained large during the winter months.",
                "Electricity consumption in Finland grew by about 3 percent, driven by data centres, electric heating "
                "and the electrification of industry. More than 2,000 MW of new wind power capacity was connected to "
                "the Finnish grid during the year, which increased competition for grid connection capacity, "
                "particularly in Northern Ostrobothnia.",
                "Demand for long-term power purchase agreements remained strong. Industrial customers in particular "
                "were interested in fixed-price contracts of five to ten years for renewable electricity.",
            ]),
            ("Key figures", [
                "Revenue grew to EUR 184.6 million (2024: EUR 171.3 million). Growth came mainly from higher production "
                "volumes, as the Kivijärvi solar park operated for the whole year and the wind conditions were better "
                "than average. The average selling price of electricity was EUR 61.40 per megawatt hour, slightly lower "
                "than in the previous year.",
                "Operating profit was EUR 21.9 million (2024: EUR 18.4 million). Investments totalled EUR 63.2 million "
                "(2024: EUR 48.7 million), most of which was spent on the Ristineva wind farm and the Haukilahti solar park.",
                "The company generated 1,148 gigawatt hours of electricity (2024: 1,032 GWh). Renewable sources accounted "
                "for 87 percent of our own generation (2024: 81 percent). The remaining share came from the Vanhalinna "
                "combined heat and power plant, which burns biomass and peat.",
                "At the end of the year the company had 412 employees (2024: 389).",
            ]),
            ("Projects and operations", [
                "Ristineva wind farm (Pyhäjoki). The wind farm will consist of 20 turbines with a total capacity of "
                "120 MW. Soil surveys revealed weaker ground than expected at several turbine locations, and the "
                "foundation design had to be revised. As a result the project is four months behind schedule, and "
                "commissioning is now expected in the autumn of 2027. The turbines are supplied by Nordwind Turbines.",
                "Haukilahti solar park (Kokemäki). Construction of the 22 MW solar park started in May 2025. The grid "
                "connection was delayed by six weeks because the grid operator postponed its substation work. The "
                "inverters are supplied by Helios Grid Systems. The park is expected to be completed in 2026.",
                "Pohjankangas wind farm (Kalajoki). A damaged underground collection cable was repaired in March 2025. "
                "The wind farm was partially out of operation for 19 days, and the repair cost EUR 1.3 million. The "
                "replacement cable was delivered by Baltic Cable Works.",
                "Koskenniska hydropower plant (Kemijärvi). The renovation of the plant's turbine was completed in "
                "October 2025 on schedule and within budget. The renovation increased the plant's annual output by "
                "4 percent.",
            ]),
            ("Customers", [
                "At the end of the year we sold electricity to 64,300 customers, of whom 58,900 were households and the "
                "rest companies and public sector organisations. The number of customers grew by 2,100 during the year.",
                "We also supply district heat to three local networks, in Lieto, Harjuvesi and Ruskola. District heat "
                "sales were 412 gigawatt hours. Customer satisfaction, measured by an independent survey, rose to 8.1 on "
                "a scale from 4 to 10.",
                "During the year we signed two long-term power purchase agreements with industrial customers. Together "
                "they cover about 15 percent of our expected wind generation from 2027 onwards.",
            ]),
            ("Personnel and safety", [
                "At the end of 2025 the company employed 412 people (2024: 389). The average age of employees was "
                "41 years and employee turnover was 6.2 percent. Each employee received an average of 31 hours of "
                "training during the year.",
                "There were four lost-time injuries in 2025 (2024: five). The lost-time injury frequency (LTIF), "
                "measured per million hours worked, was 5.1 (2024: 6.8). Employees and contractors filed 27 near-miss "
                "reports (2024: 19). We regard the growing number of near-miss reports as a sign of a healthier "
                "reporting culture.",
                "Each injury was investigated, and the corrective actions are followed up by the steering group. The "
                "details of each incident are recorded in the incident register.",
            ]),
            ("Sustainability and outlook", [
                "Carbon dioxide emissions from our own generation were 58,000 tonnes (2024: 74,000 tonnes). Most of the "
                "emissions come from the Vanhalinna combined heat and power plant, which will be closed in 2028 and "
                "replaced by heat pumps and an electric boiler.",
                "Our target is carbon-neutral own generation by 2030.",
                "Outlook for 2026: we expect revenue to be between EUR 190 million and EUR 205 million. The Hietasaari "
                "battery storage and the Haukilahti solar park are scheduled to be commissioned in 2026.",
            ]),
            ("Risk management", [
                "The most significant risks to our business are changes in electricity prices, delays in construction "
                "projects, permit processes and the availability of grid connection capacity. Risks are assessed "
                "quarterly by the management team and reported to the board twice a year.",
                "Price risk is managed by selling part of the expected generation in advance. At the end of 2025, "
                "about 70 percent of the expected generation for 2026 and 45 percent of the expected generation for "
                "2027 had been hedged.",
                "Construction risks are reduced with fixed-price contracts, delay penalties and delivery guarantees. "
                "Large investments require a board decision, and projects are followed by a steering group that meets "
                "at least four times a year.",
            ]),
            ("Corporate governance", [
                "Kuusiranta Energy Ltd is owned by four municipalities: Harjuvesi (46 percent), Lieto (22 percent), "
                "Ruskola (18 percent) and Kalajoki (14 percent). The company's board of directors has seven members and "
                "met eleven times in 2025. The board is chaired by Anneli Saarinen.",
                "The management team consists of the CEO and the directors responsible for production, projects, "
                "sales and customer service, and human resources. The company's auditor is Tilintarkastus Nordic Oy.",
                "The annual general meeting will be held in Harjuvesi on 22 April 2026. The board proposes a dividend "
                "of EUR 6.0 million to the owners.",
            ]),
        ],
    },
    "fi": {
        "filename": "vuosikertomus_2025.pdf",
        "title": "Kuusiranta Energia Oy - Vuosikertomus 2025",
        "pages": [
            ("Toimitusjohtajan katsaus", [
                "Vuosi 2025 oli Kuusiranta Energialle tasaisen kasvun vuosi. Liikevaihtomme kasvoi 184,6 miljoonaan "
                "euroon, ja uusiutuvien energialähteiden osuus omasta sähköntuotannostamme nousi 87 prosenttiin. "
                "Samaan aikaan useat rakennushankkeemme kohtasivat vaikeuksia, emmekä ole tyytyväisiä siihen, miten "
                "hankesalkkumme pysyi aikatauluissaan.",
                "Jatkoimme investointeja tuuli- ja aurinkovoimaan. Keväällä 2024 valmistunut Kivijärven aurinkopuisto "
                "oli ensimmäistä kokonaista vuotta käytössä ja tuotti sähköä enemmän kuin suunnitteluarvio. Yhtiön "
                "historian suurimman investoinnin, Ristinevan tuulipuiston, rakentaminen eteni, mutta hanke on "
                "alkuperäisestä aikataulustaan jäljessä.",
                "Turvallisuus on edelleen tärkein prioriteettimme. Poissaoloon johtaneiden tapaturmien määrä laski "
                "edellisvuodesta, mutta jokainen tapaturma on liikaa. Siksi käynnistämme vuoden 2026 alussa uuden "
                "urakoitsijoiden turvallisuusohjelman.",
                "Kuusiranta Energian pääkonttori sijaitsee Harjuvedellä. Haluan kiittää henkilöstöämme, asiakkaitamme "
                "ja kumppaneitamme vuoden aikana tehdystä työstä.",
                "Markus Lehtovaara, toimitusjohtaja",
            ]),
            ("Markkinaympäristö", [
                "Sähkön pohjoismainen systeemihinta oli vuonna 2025 keskimäärin 41,20 euroa megawattitunnilta, kun se "
                "edellisvuonna oli 44,80 euroa. Hinnat vaihtelivat voimakkaasti vuodenaikojen mukaan: kuukauden "
                "keskihinta vaihteli kesäkuun 12 eurosta tammikuun 96 euroon. Suomen hinta-alueen ja systeemihinnan "
                "välinen ero pysyi suurena talvikuukausina.",
                "Sähkönkulutus Suomessa kasvoi noin 3 prosenttia datakeskusten, sähkölämmityksen ja teollisuuden "
                "sähköistymisen vuoksi. Suomen sähköverkkoon liitettiin vuoden aikana yli 2 000 MW uutta "
                "tuulivoimakapasiteettia, mikä lisäsi kilpailua verkkoliityntäkapasiteetista erityisesti "
                "Pohjois-Pohjanmaalla.",
                "Pitkäaikaisten sähkönostosopimusten kysyntä pysyi vahvana. Erityisesti teollisuusasiakkaat olivat "
                "kiinnostuneita viidestä kymmeneen vuoden kiinteähintaisista sopimuksista uusiutuvasta sähköstä.",
            ]),
            ("Keskeiset tunnusluvut", [
                "Liikevaihto kasvoi 184,6 miljoonaan euroon (2024: 171,3 miljoonaa euroa). Kasvu johtui pääosin "
                "suuremmista tuotantomääristä, sillä Kivijärven aurinkopuisto oli käytössä koko vuoden ja tuuliolosuhteet "
                "olivat keskimääräistä paremmat. Sähkön keskimääräinen myyntihinta oli 61,40 euroa megawattitunnilta, "
                "hieman edellisvuotta alempi.",
                "Liikevoitto oli 21,9 miljoonaa euroa (2024: 18,4 miljoonaa euroa). Investoinnit olivat yhteensä "
                "63,2 miljoonaa euroa (2024: 48,7 miljoonaa euroa), ja niistä suurin osa kohdistui Ristinevan "
                "tuulipuistoon ja Haukilahden aurinkopuistoon.",
                "Yhtiö tuotti sähköä 1 148 gigawattituntia (2024: 1 032 GWh). Uusiutuvien energialähteiden osuus omasta "
                "tuotannosta oli 87 prosenttia (2024: 81 prosenttia). Loput tuotannosta tuli Vanhalinnan "
                "sähkön ja lämmön yhteistuotantolaitokselta, joka käyttää polttoaineena biomassaa ja turvetta.",
                "Vuoden lopussa yhtiön palveluksessa oli 412 henkilöä (2024: 389).",
            ]),
            ("Hankkeet ja toiminta", [
                "Ristinevan tuulipuisto (Pyhäjoki). Tuulipuistoon tulee 20 tuulivoimalaa, joiden yhteisteho on "
                "120 MW. Maaperätutkimuksissa useiden voimalapaikkojen maaperä osoittautui odotettua heikommaksi, ja "
                "perustusten suunnitelmat jouduttiin tekemään uudelleen. Tämän vuoksi hanke on neljä kuukautta "
                "aikataulusta jäljessä, ja käyttöönoton arvioidaan nyt tapahtuvan syksyllä 2027. Tuulivoimalat "
                "toimittaa Nordwind Turbines.",
                "Haukilahden aurinkopuisto (Kokemäki). 22 MW:n aurinkopuiston rakentaminen alkoi toukokuussa 2025. "
                "Sähköverkkoon liittäminen viivästyi kuudella viikolla, koska verkonhaltija siirsi sähköasematöitään. "
                "Invertterit toimittaa Helios Grid Systems. Puiston on määrä valmistua vuonna 2026.",
                "Pohjankankaan tuulipuisto (Kalajoki). Vaurioitunut maakaapeli korjattiin maaliskuussa 2025. "
                "Tuulipuisto oli osittain pois käytöstä 19 päivän ajan, ja korjaus maksoi 1,3 miljoonaa euroa. "
                "Uuden kaapelin toimitti Baltic Cable Works.",
                "Koskenniskan vesivoimalaitos (Kemijärvi). Laitoksen turbiinin peruskorjaus valmistui lokakuussa 2025 "
                "aikataulussa ja budjetissa. Peruskorjaus kasvatti laitoksen vuosituotantoa 4 prosentilla.",
            ]),
            ("Asiakkaat", [
                "Vuoden lopussa myimme sähköä 64 300 asiakkaalle, joista 58 900 oli kotitalouksia ja loput yrityksiä "
                "ja julkisen sektorin organisaatioita. Asiakasmäärä kasvoi vuoden aikana 2 100 asiakkaalla.",
                "Toimitamme kaukolämpöä myös kolmeen paikalliseen verkkoon Liedossa, Harjuvedellä ja Ruskolassa. "
                "Kaukolämmön myynti oli 412 gigawattituntia. Riippumattomalla kyselyllä mitattu asiakastyytyväisyys "
                "nousi arvoon 8,1 asteikolla 4-10.",
                "Teimme vuoden aikana kaksi pitkäaikaista sähkönostosopimusta teollisuusasiakkaiden kanssa. Yhdessä ne "
                "kattavat noin 15 prosenttia odotetusta tuulivoimatuotannostamme vuodesta 2027 alkaen.",
            ]),
            ("Henkilöstö ja turvallisuus", [
                "Vuoden 2025 lopussa yhtiö työllisti 412 henkilöä (2024: 389). Henkilöstön keski-ikä oli 41 vuotta ja "
                "henkilöstön vaihtuvuus 6,2 prosenttia. Jokainen työntekijä sai vuoden aikana keskimäärin 31 tuntia "
                "koulutusta.",
                "Vuonna 2025 sattui neljä poissaoloon johtanutta tapaturmaa (2024: viisi). Tapaturmataajuus (LTIF) "
                "miljoonaa työtuntia kohden oli 5,1 (2024: 6,8). Työntekijät ja urakoitsijat tekivät 27 "
                "läheltä piti -ilmoitusta (2024: 19). Pidämme läheltä piti -ilmoitusten kasvua merkkinä "
                "terveemmästä ilmoituskulttuurista.",
                "Jokainen tapaturma tutkittiin, ja ohjausryhmä seuraa korjaavien toimenpiteiden toteutumista. "
                "Tapaturmien yksityiskohdat on kirjattu tapaturmarekisteriin.",
            ]),
            ("Vastuullisuus ja näkymät", [
                "Oman tuotantomme hiilidioksidipäästöt olivat 58 000 tonnia (2024: 74 000 tonnia). Suurin osa "
                "päästöistä syntyy Vanhalinnan yhteistuotantolaitoksella, joka suljetaan vuonna 2028 ja korvataan "
                "lämpöpumpuilla ja sähkökattilalla.",
                "Tavoitteemme on hiilineutraali oma tuotanto vuoteen 2030 mennessä.",
                "Näkymät vuodelle 2026: odotamme liikevaihdon olevan 190-205 miljoonaa euroa. Hietasaaren "
                "akkuvaraston ja Haukilahden aurinkopuiston on määrä valmistua käyttöön vuonna 2026.",
            ]),
            ("Riskienhallinta", [
                "Liiketoimintamme merkittävimmät riskit ovat sähkön hinnan muutokset, rakennushankkeiden viivästykset, "
                "lupaprosessit ja verkkoliityntäkapasiteetin saatavuus. Johtoryhmä arvioi riskit neljännesvuosittain, "
                "ja niistä raportoidaan hallitukselle kahdesti vuodessa.",
                "Hintariskiä hallitaan myymällä osa odotetusta tuotannosta etukäteen. Vuoden 2025 lopussa vuoden 2026 "
                "odotetusta tuotannosta oli suojattu noin 70 prosenttia ja vuoden 2027 tuotannosta 45 prosenttia.",
                "Rakentamisen riskejä pienennetään kiinteähintaisilla sopimuksilla, viivästyssakoilla ja "
                "toimitustakuilla. Suuret investoinnit edellyttävät hallituksen päätöstä, ja hankkeita seuraa "
                "ohjausryhmä, joka kokoontuu vähintään neljä kertaa vuodessa.",
            ]),
            ("Hallinnointi", [
                "Kuusiranta Energia Oy:n omistavat neljä kuntaa: Harjuvesi (46 prosenttia), Lieto (22 prosenttia), "
                "Ruskola (18 prosenttia) ja Kalajoki (14 prosenttia). Yhtiön hallituksessa on seitsemän jäsentä, ja se "
                "kokoontui vuonna 2025 yksitoista kertaa. Hallituksen puheenjohtajana toimii Anneli Saarinen.",
                "Johtoryhmään kuuluvat toimitusjohtaja sekä tuotannosta, hankkeista, myynnistä ja asiakaspalvelusta "
                "sekä henkilöstöasioista vastaavat johtajat. Yhtiön tilintarkastaja on Tilintarkastus Nordic Oy.",
                "Varsinainen yhtiökokous pidetään Harjuvedellä 22.4.2026. Hallitus ehdottaa omistajille "
                "6,0 miljoonan euron osinkoa.",
            ]),
        ],
    },
}

# --------------------------------------------------------------------------
# 2. Steering group minutes (DOCX, one section per heading)
# --------------------------------------------------------------------------

MINUTES = {
    "en": {
        "filename": "steering_group_minutes_4_2025.docx",
        "title": "Steering Group Meeting 4/2025 - Minutes",
        "sections": [
            ("Meeting details", [
                "Date: 18 November 2025, 13:00-15:30. Place: head office, Harjuvesi.",
                "Present: Markus Lehtovaara (chair), Jari Nieminen (project director, Ristineva), Elina Koskinen "
                "(project manager, Hietasaari battery storage), Sanna Virtanen (HSE manager), Olli Rantanen (secretary).",
            ], None),
            ("Project status", [
                "Ristineva wind farm: the revised foundation design was approved by the structural engineer in October. "
                "Six of the twenty turbine foundations have been completed. Because of the redesign the project is four "
                "months late. The turbine supply contract KR-2025-0417 with Nordwind Turbines has been amended to match "
                "the new delivery schedule.",
                "Hietasaari battery storage (30 MW / 60 MWh, budget EUR 24.5 million): the main transformer ordered from "
                "Voltmark will arrive late. Commissioning has therefore been moved from 30 April 2026 to 14 August 2026. "
                "Project manager Elina Koskinen presented two options for limiting the delay.",
                "Haukilahti solar park: 80 percent of the panels have been installed. The grid connection is six weeks "
                "late because of the grid operator's substation work.",
                "Tervaharju wind farm: the environmental permit was appealed to the administrative court in September "
                "2025. A decision is expected in 2026. Detailed planning has been paused until then.",
            ], None),
            ("Safety", [
                "Sanna Virtanen reported two lost-time injuries since the previous meeting: a contractor's vehicle "
                "accident on the Ristineva site road on 21 August 2025, and a chemical splash to an employee's eye at "
                "the Vanhalinna plant on 7 November 2025. Both incidents have been investigated and the corrective "
                "actions have been agreed.",
            ], None),
            ("Decisions", [
                "1. The steering group approved an additional budget of EUR 1.8 million for the Ristineva foundations.",
                "2. The contractor safety programme will be launched on 1 January 2026.",
                "3. Kuusiranta Energy will request a revised delivery guarantee from Voltmark.",
                "4. The procurement of turbines for the Tervaharju wind farm is postponed until the permit decision.",
            ], None),
            ("Action items", [], [
                ["Action", "Owner", "Due"],
                ["Updated schedule for the Ristineva wind farm", "Jari Nieminen", "5 December 2025"],
                ["Review of the penalty clauses in the Voltmark contract", "Elina Koskinen", "28 November 2025"],
                ["Detailed plan for the contractor safety programme", "Sanna Virtanen", "15 December 2025"],
            ]),
            ("Next meeting", [
                "The next steering group meeting will be held on 16 December 2025 at 9:00.",
            ], None),
        ],
    },
    "fi": {
        "filename": "ohjausryhman_poytakirja_4_2025.docx",
        "title": "Ohjausryhmän kokous 4/2025 - Pöytäkirja",
        "sections": [
            ("Kokouksen tiedot", [
                "Aika: 18.11.2025 klo 13.00-15.30. Paikka: pääkonttori, Harjuvesi.",
                "Läsnä: Markus Lehtovaara (puheenjohtaja), Jari Nieminen (projektijohtaja, Ristineva), Elina Koskinen "
                "(projektipäällikkö, Hietasaaren akkuvarasto), Sanna Virtanen (työturvallisuuspäällikkö), Olli Rantanen "
                "(sihteeri).",
            ], None),
            ("Hankkeiden tilanne", [
                "Ristinevan tuulipuisto: rakennesuunnittelija hyväksyi uudistetut perustussuunnitelmat lokakuussa. "
                "Kahdestakymmenestä voimalan perustuksesta kuusi on valmiina. Suunnitelmamuutosten vuoksi hanke on "
                "neljä kuukautta myöhässä. Nordwind Turbinesin kanssa tehty voimaloiden toimitussopimus KR-2025-0417 on "
                "muutettu vastaamaan uutta toimitusaikataulua.",
                "Hietasaaren akkuvarasto (30 MW / 60 MWh, budjetti 24,5 miljoonaa euroa): Voltmarkilta tilattu "
                "päämuuntaja saapuu myöhässä. Käyttöönotto on siksi siirretty 30.4.2026:sta 14.8.2026:een. "
                "Projektipäällikkö Elina Koskinen esitteli kaksi vaihtoehtoa viivästyksen rajoittamiseksi.",
                "Haukilahden aurinkopuisto: paneeleista 80 prosenttia on asennettu. Verkkoliityntä on kuusi viikkoa "
                "myöhässä verkonhaltijan sähköasematöiden vuoksi.",
                "Tervaharjun tuulipuisto: ympäristöluvasta valitettiin hallinto-oikeuteen syyskuussa 2025. Päätöstä "
                "odotetaan vuonna 2026. Yksityiskohtainen suunnittelu on keskeytetty siihen asti.",
            ], None),
            ("Turvallisuus", [
                "Sanna Virtanen raportoi kaksi poissaoloon johtanutta tapaturmaa edellisen kokouksen jälkeen: "
                "urakoitsijan ajoneuvo-onnettomuuden Ristinevan työmaatiellä 21.8.2025 ja työntekijän silmään "
                "osuneen kemikaaliroiskeen Vanhalinnan laitoksella 7.11.2025. Molemmat tapaturmat on tutkittu ja "
                "korjaavista toimenpiteistä on sovittu.",
            ], None),
            ("Päätökset", [
                "1. Ohjausryhmä hyväksyi Ristinevan perustuksille 1,8 miljoonan euron lisäbudjetin.",
                "2. Urakoitsijoiden turvallisuusohjelma käynnistetään 1.1.2026.",
                "3. Kuusiranta Energia pyytää Voltmarkilta uudistetun toimitustakuun.",
                "4. Tervaharjun tuulipuiston voimaloiden hankintaa lykätään, kunnes lupapäätös on saatu.",
            ], None),
            ("Toimenpiteet", [], [
                ["Toimenpide", "Vastuuhenkilö", "Määräaika"],
                ["Ristinevan tuulipuiston päivitetty aikataulu", "Jari Nieminen", "5.12.2025"],
                ["Voltmarkin sopimuksen sopimussakkoehtojen tarkistus", "Elina Koskinen", "28.11.2025"],
                ["Urakoitsijoiden turvallisuusohjelman yksityiskohtainen suunnitelma", "Sanna Virtanen", "15.12.2025"],
            ]),
            ("Seuraava kokous", [
                "Ohjausryhmän seuraava kokous pidetään 16.12.2025 klo 9.00.",
            ], None),
        ],
    },
}

# --------------------------------------------------------------------------
# 3. Strategy deck (PPTX, one section per slide)
# --------------------------------------------------------------------------

SLIDES = {
    "en": {
        "filename": "strategy_2026_2030.pptx",
        "slides": [
            ("Kuusiranta Energy - Strategy 2026-2030", ["Board presentation, 2 December 2025"]),
            ("Our targets", [
                "Carbon-neutral own generation by 2030",
                "Renewable share of own generation 95 % by 2028",
                "400 MW of new wind and solar capacity by 2030",
                "Lost-time injury frequency below 3.0 by 2028",
            ]),
            ("Ristineva wind farm", [
                "20 turbines x 6.0 MW = 120 MW",
                "Turbine supplier: Nordwind Turbines",
                "Investment: EUR 168 million",
                "Commissioning: autumn 2027 (four months later than planned)",
            ]),
            ("Project pipeline", [
                "Haukilahti solar park - 22 MW - 2026",
                "Hietasaari battery storage - 30 MW - 2026",
                "Ristineva wind farm - 120 MW - 2027",
                "Tervaharju wind farm - 78 MW - 2028; permit appeal pending, schedule at risk",
            ]),
            ("Phasing out combustion", [
                "Vanhalinna CHP plant closes in 2028",
                "Replaced by two heat pumps (24 MW in total) and a 40 MW electric boiler",
                "Investment: EUR 52 million",
            ]),
            ("Key risks", [
                "Appeals against environmental permits",
                "Supply chain delays, especially transformers",
                "Limited grid connection capacity",
                "Volatile electricity prices",
            ]),
            ("Next steps", [
                "Board decision on the Vanhalinna replacement investment in March 2026",
                "Updated Ristineva schedule to the board in January 2026",
            ]),
        ],
    },
    "fi": {
        "filename": "strategia_2026_2030.pptx",
        "slides": [
            ("Kuusiranta Energia - Strategia 2026-2030", ["Hallituksen esitys, 2.12.2025"]),
            ("Tavoitteemme", [
                "Hiilineutraali oma tuotanto vuoteen 2030 mennessä",
                "Uusiutuvien osuus omasta tuotannosta 95 % vuoteen 2028 mennessä",
                "400 MW uutta tuuli- ja aurinkovoimakapasiteettia vuoteen 2030 mennessä",
                "Tapaturmataajuus alle 3,0 vuoteen 2028 mennessä",
            ]),
            ("Ristinevan tuulipuisto", [
                "20 voimalaa x 6,0 MW = 120 MW",
                "Voimaloiden toimittaja: Nordwind Turbines",
                "Investointi: 168 miljoonaa euroa",
                "Käyttöönotto: syksy 2027 (neljä kuukautta suunniteltua myöhemmin)",
            ]),
            ("Hankeputki", [
                "Haukilahden aurinkopuisto - 22 MW - 2026",
                "Hietasaaren akkuvarasto - 30 MW - 2026",
                "Ristinevan tuulipuisto - 120 MW - 2027",
                "Tervaharjun tuulipuisto - 78 MW - 2028; lupavalitus käsittelyssä, aikataulu vaarassa",
            ]),
            ("Polttamisesta luopuminen", [
                "Vanhalinnan yhteistuotantolaitos suljetaan vuonna 2028",
                "Korvataan kahdella lämpöpumpulla (yhteensä 24 MW) ja 40 MW:n sähkökattilalla",
                "Investointi: 52 miljoonaa euroa",
            ]),
            ("Keskeiset riskit", [
                "Ympäristölupia koskevat valitukset",
                "Toimitusketjujen viivästykset, erityisesti muuntajat",
                "Rajallinen verkkoliityntäkapasiteetti",
                "Sähkön hintojen voimakas vaihtelu",
            ]),
            ("Seuraavat askeleet", [
                "Hallituksen päätös Vanhalinnan korvaavasta investoinnista maaliskuussa 2026",
                "Päivitetty Ristinevan aikataulu hallitukselle tammikuussa 2026",
            ]),
        ],
    },
}

# --------------------------------------------------------------------------
# 4. Site and incident register (XLSX, one section per sheet)
# --------------------------------------------------------------------------

REGISTER = {
    "en": {
        "filename": "site_register.xlsx",
        "sheets": {
            "Sites": [
                ["Site ID", "Site", "Type", "Municipality", "Capacity (MW)", "Commissioned", "Status"],
                ["KR-W01", "Pohjankangas wind farm", "Wind", "Kalajoki", 96, "2019", "In operation"],
                ["KR-W02", "Lumivaara wind farm", "Wind", "Kuusamo", 54, "2022", "In operation"],
                ["KR-W03", "Ristineva wind farm", "Wind", "Pyhäjoki", 120, "2027 (planned)", "Under construction"],
                ["KR-W04", "Tervaharju wind farm", "Wind", "Lestijärvi", 78, "2028 (planned)", "Permitting"],
                ["KR-S01", "Kivijärvi solar park", "Solar", "Hollola", 38, "2024", "In operation"],
                ["KR-S02", "Haukilahti solar park", "Solar", "Kokemäki", 22, "2026 (planned)", "Under construction"],
                ["KR-H01", "Koskenniska hydropower plant", "Hydro", "Kemijärvi", 31, "1968", "In operation"],
                ["KR-B01", "Hietasaari battery storage", "Battery", "Oulu", 30, "2026 (planned)", "Under construction"],
                ["KR-C01", "Vanhalinna CHP plant", "Biomass CHP", "Lieto", 45, "1994", "Closing in 2028"],
            ],
            "Incidents": [
                ["Date", "Site", "Type", "Description", "Days lost"],
                ["2025-02-12", "Vanhalinna CHP plant", "Lost-time injury", "Fall from a ladder during boiler maintenance", 9],
                ["2025-06-03", "Koskenniska hydropower plant", "Lost-time injury", "Hand injury during turbine renovation", 14],
                ["2025-08-21", "Ristineva wind farm", "Lost-time injury", "Contractor vehicle accident on the site road", 22],
                ["2025-11-07", "Vanhalinna CHP plant", "Lost-time injury", "Chemical splash to the eye", 3],
            ],
        },
    },
    "fi": {
        "filename": "kohderekisteri.xlsx",
        "sheets": {
            "Kohteet": [
                ["Kohdetunnus", "Kohde", "Tyyppi", "Kunta", "Teho (MW)", "Käyttöönotto", "Tila"],
                ["KR-W01", "Pohjankankaan tuulipuisto", "Tuuli", "Kalajoki", 96, "2019", "Käytössä"],
                ["KR-W02", "Lumivaaran tuulipuisto", "Tuuli", "Kuusamo", 54, "2022", "Käytössä"],
                ["KR-W03", "Ristinevan tuulipuisto", "Tuuli", "Pyhäjoki", 120, "2027 (suunniteltu)", "Rakenteilla"],
                ["KR-W04", "Tervaharjun tuulipuisto", "Tuuli", "Lestijärvi", 78, "2028 (suunniteltu)", "Luvitusvaiheessa"],
                ["KR-S01", "Kivijärven aurinkopuisto", "Aurinko", "Hollola", 38, "2024", "Käytössä"],
                ["KR-S02", "Haukilahden aurinkopuisto", "Aurinko", "Kokemäki", 22, "2026 (suunniteltu)", "Rakenteilla"],
                ["KR-H01", "Koskenniskan vesivoimalaitos", "Vesi", "Kemijärvi", 31, "1968", "Käytössä"],
                ["KR-B01", "Hietasaaren akkuvarasto", "Akku", "Oulu", 30, "2026 (suunniteltu)", "Rakenteilla"],
                ["KR-C01", "Vanhalinnan yhteistuotantolaitos", "Biomassa (CHP)", "Lieto", 45, "1994", "Suljetaan 2028"],
            ],
            "Tapaturmat": [
                ["Päivämäärä", "Kohde", "Tyyppi", "Kuvaus", "Menetetyt työpäivät"],
                ["12.2.2025", "Vanhalinnan yhteistuotantolaitos", "Poissaoloon johtanut tapaturma", "Putoaminen tikkailta kattilan huollossa", 9],
                ["3.6.2025", "Koskenniskan vesivoimalaitos", "Poissaoloon johtanut tapaturma", "Käsivamma turbiinin peruskorjauksessa", 14],
                ["21.8.2025", "Ristinevan tuulipuisto", "Poissaoloon johtanut tapaturma", "Urakoitsijan ajoneuvo-onnettomuus työmaatiellä", 22],
                ["7.11.2025", "Vanhalinnan yhteistuotantolaitos", "Poissaoloon johtanut tapaturma", "Kemikaaliroiske silmään", 3],
            ],
        },
    },
}

# Order in which the documents are given to the model. Fixed, so that the
# full-context prompt is identical for every question and llama-server can
# reuse its cached prompt between questions.
DOCUMENT_ORDER = ("report", "minutes", "slides", "register")

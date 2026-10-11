// ── Header offset ──
const wpHeader = document.querySelector('.middle-header-contain');
const updateHeaderOffset = () => {
    const h = wpHeader?.getBoundingClientRect().height || 0;
    document.documentElement.style.setProperty('--header-h', h + 'px');
};
updateHeaderOffset();
window.addEventListener('resize', updateHeaderOffset);

// ═══════════════════════════════════════════════
// DATA
// ═══════════════════════════════════════════════

const reps = [
    { name: "Nathaniel Oducado",               pl: "1 TAHANAN",                   cat: "none",               note: "" },
    { name: "Rodge Gutierrez",                 pl: "1-RIDER PARTYLIST",            cat: "Both",               note: "Relative/s in elective office:\nLuis Gutierrez - Vice Mayor of Legazpi City, Albay (brother)\n\nContractor link:\nHis father, Basil Ramon Gutierrez, and brother, Luis Gutierrez, co-own public works contractor Alro Construction and Development Corporation (based on the company's April 2025 General Information Sheet). His partylist also received donations from Bicol-based government contractors Jose Marcial F. Villanueva, Dandy U. Deyto, and Sharon S. Deyto." },
    { name: "Iris Marie Montes",               pl: "4K",                          cat: "none",  note: "" },
    { name: "Marcelino Libanan",               pl: "4PS",                         cat: "Dynasty",            note: "Relatives in elective office:\nChristopher Sheen Projemo Gonzales - Eastern Samar Lone District Representative (son-in-law)" },
    { name: "Jonathan Clement Abalos",         pl: "4PS",                         cat: "Dynasty",            note: "Relatives in elective office:\nBenjamin Abalos III - Mandaluyong, councilor (cousin)\nMenchie Aguilar Abalos - Mandaluyong, mayor (aunt)\nCharisse Abalos - Mandaluyong, councilor (cousin)" },
    { name: "Robert Raymond Estrella",         pl: "ABONO",                       cat: "Dynasty",            note: "Relative/s previously in elective office:\nConrado Masonsong Estrella III - former Abono party-list rep (brother; held the post before him)" },
    { name: "Maximo Rodriguez Jr.",            pl: "ABAMIN",                      cat: "Dynasty",            note: "Relatives in elective office:\nRufus Rodriguez - Cagayan de Oro 2nd District Rep. (brother)\nJocelyn Rodriguez - Cagayan de Oro Vice Mayor (sister)\nMax Rodriguez III - Cagayan de Oro Councilor (son)" },
    { name: "Manuel Frederick Ong Ko",         pl: "ABANG LINGKOD",               cat: "none",               note: "" },
    { name: "Antonio Tinio",                   pl: "ACT TEACHERS",                cat: "none",               note: "" },
    { name: "Jocelyn Tulfo",                   pl: "ACT-CIS",                     cat: "Dynasty",            note: "Relatives in elective office:\nRaffy Tulfo - Senator (husband)\nErwin Tulfo - Senator (brother-in-law)\nRalph Tulfo - Quezon City Second District Rep. (son)" },
    { name: "Jeffrey Soriano",                   pl: "ACT-CIS",                     cat: "none",            note: "" },
    { name: "Nicanor Briones",                 pl: "AGAP",                        cat: "Dynasty",            note: "Relatives in elective office:\nKaye Briones - San Jose, Batangas Councilor (daughter)" },
    { name: "Bryan Revilla",                   pl: "AGIMAT",                      cat: "Both",               note: "Relatives in elective office:\nRam Revilla - Cavite Vice Governor (brother)\nJolo Revilla - Cavite First District Rep. (brother)\nLani Mercado-Revilla - Cavite Second District Rep. (mother)\nStrike Revilla - Bacoor, Cavite Mayor (uncle)\nRowena Mendiola-Bautista - Bacoor, Cavite Vice Mayor (aunt)\n\nContractor link:\nHis aunt, Rebecca Ocampo, is the president of Graia Construction Corporation, public works contractor." },
    { name: "Chel Diokno",                     pl: "AKBAYAN",                     cat: "none",               note: "" },
    { name: "Perci Cendaña",                   pl: "AKBAYAN",                     cat: "none",               note: "" },
    { name: "Dadah Kiram Ismula",              pl: "AKBAYAN",                     cat: "none",               note: "" },
    { name: "Jan Franz Chan",                  pl: "AKO BICOL",                   cat: "Contractor-linked",  note: "His party-list's first nominee Elizaldy Co poured P142 million in donations for the group's campaign activities. Co is the founder of big-time government contractors Sunwest Inc. and Hi-Tone Construction & Development Corp. The Ombudsman identified Co as a beneficial owner of Sunwest Inc." },
    { name: "Alfredo Garbin Jr.",              pl: "AKO BICOL",                   cat: "Contractor-linked",  note: "His party-list's first nominee Elizaldy Co poured P142 million in donations for the group's campaign activities. Co is the founder of big-time government contractors Sunwest Inc. and Hi-Tone Construction & Development Corp. The Ombudsman identified Co as a beneficial owner of Sunwest Inc." },
    { name: "Sonny Lagon",                     pl: "AKO BISAYA",                  cat: "Dynasty",            note: "Relatives in elective office:\nDaphne Lagon - Cebu 6th District Rep. (wife)\nLarenz Lagon - Board Member, Cebu 6th District (son)\nLorenz Lagon - Board Member, Cebu 3rd District (son)" },
    { name: "Richelle Singson-Michael",        pl: "AKO ILOCANO AKO",             cat: "Both",               note: "Relatives in elective office:\nRonald Singson - Ilocos Sur 1st District Rep. (brother)\nKristine Singson-Meehan - Ilocos Sur 2nd District Rep.\nJeremias Singson - Ilocos Sur Governor (uncle)\nRyan Singson - Ilocos Sur Vice Governor (brother)\nJanina Singson Medina-Farinas - Ilocos Sur board Member (relative)\nErickson Singson - Ilocos Sur Board Member (relative)\nFayina Pilar Zaragoza - Ilocos Sur board member (relative)\nAnnea Cassandra Singson De Leon - Sto. Domingo, Ilocos Sur Mayor (relative)\nKatherine Aguila Singson - Vigan, Ilocos Sur councilor (relative)\nRandy Singson - Vigan, Ilocos Sur Mayor (brother)\nEvaristo Singson III - Vigan, Ilocos Sur councilor (cousin)\nGermilina Goulart - Caoayan, Ilocos Sur Mayor (aunt)\nJuan Paolo Singson Ancheta - Caoayan, Ilocos Sur Vice Mayor (cousin)\nKristelle Singson - Candon, Ilocos Sur Mayor (relative)\nJaime Singson - Candon, Ilocos Sur councilor (relative)\nEric Owen Singson - Candon, Ilocos Sur councilor (relative)\n\nContractor link:\nHer sister, Regina Singson-Lim, is a stakeholder of Satrap Construction Co., Inc., a public works contractor." },
    { name: "Maria Cristina Lopez",            pl: "ALONA",                       cat: "none",               note: "" },
    { name: "Alfred Delos Santos",             pl: "ANG PROBINSYANO",             cat: "Contractor-linked",  note: "His mother and three brothers each manage their own construction companies that have public works contracts. These are Wearr Enterprises and Development Corp., WCS Construction Inc., RCDS Construction & Supply Inc., and 3Diamonds Construction Corp." },
    { name: "Sergio Dagooc",                   pl: "APEC",                        cat: "Franchisee-linked",  note: "His party-list received campaign donations from the general managers of Leyte III Electric Cooperative, Cebu 3 Electric Cooperative, and Romblon Electric Cooperative. Electric cooperatives are required to secure legislative franchises before they can operate." },
    { name: "Henry F. Oaminal Jr.",            pl: "ASENSO PINOY",                cat: "Both",               note: "Relatives in elective office:\nAndo Oaminal - Misamis Occidental 2nd District Rep. (brother)\nHenry Oaminal Sr. - Misamis Occidental Governor (father)\nGing Oaminal-delos Santos - Clarin, Misamis Occidental Mayor (aunt)\nSunny Oaminal - Ozamis City Councilor (uncle)\n\nContractor link:\nHe was named president of HSO Construction Corporation in its 2019 contracts with the DPWH." },
    { name: "Roberto Gerard Nazal Jr.",        pl: "BH",                          cat: "Both",               note: "Relative/s previously in elective office:\nBernadette Herrera - former BH party-list rep (wife; held the post before him)\n\nContractor link:\nHe is a co-founder of PERRC Construction and Development Corp." },
    { name: "Terry Ridon",                     pl: "BICOL SARO",                  cat: "none",               note: "" },
    { name: "Eddie Villanueva",                pl: "CIBAC",                       cat: "Dynasty",            note: "Relatives in elective office:\nJoel Villanueva - Senator (son)\nJonjon 'JJV' Villanueva - Bocaue Mayor (son)\nSherwin Tugna - Vice Mayor (son-in-law)" },
    { name: "Felimon Espares",                 pl: "COOP NATCCO",                 cat: "none",               note: "" },
    { name: "Tirso Edwin Gardiola",            pl: "CWS",                         cat: "Both",               note: "Relatives in elective office:\nEllery Loleng Gardiola-Silva - Mataas na Kahoy, Batangas mayor (sister)\nEarel Loleng Gardiola - Mataas na Kahoy, Batangas vice mayor (brother)\n\nContractor link:\nFour family members manage/own: JSG Construction, Newington Builders, Lourel Development Corporation, and S-Ang General Construction & Trading Inc. His party-list also received donations from Readycon Trading & Construction Corp." },
    { name: "Claudine Bautista-Lim",          pl: "DUMPER-PTDA",                 cat: "Dynasty",            note: "Relatives in elective office:\nColin Bautista - Davao Occidental Governor (uncle)\nLorna Bautista-Bandingan - Davao Occidental Vice Governor (aunt)\nClaude Bautista - Davao Occidental Lone District Rep. (father)\nBenjamin Bautista - Malita, Davao Occidental Mayor (uncle)\nBradly Bautista - Malita, Davao Occidental Vice Mayor (cousin)" },
    { name: "Brian Poe Llamanzares",           pl: "FPJ PANDAY BAYANIHAN",        cat: "Both",               note: "Relatives previously in elective office:\nGrace Poe Llamanzares - former senator (mother; finished her term in 2025)\n\nContractor link:\nReceived donations from Maynard Ngu, owner of Cosmic Technologies, Inc., and Joseph John Quirante, owner of Octagon Concrete Solutions. Cosmic is a Department of Education contractor, while Octagon is a public works contractor." },
    { name: "Sarah Elago",                     pl: "GABRIELA",                    cat: "none",               note: "" },
    { name: "Jan Rurik Padiernos",             pl: "GP (GALING SA PUSO)",         cat: "Dynasty",            note: "Relatives in elective office:\nJose Gay Padiernos - former GP Party-list rep (father; held the position before him)" },
    { name: "Renee Co",                        pl: "KABATAAN",                    cat: "none",               note: "" },
    { name: "Caroline Tanchay",               pl: "KAMALAYAN",                   cat: "none",               note: "" },
    { name: "Eli San Fernando",                pl: "KAMANGGAGAWA",                cat: "none",               note: "" },
    { name: "Munir Arbison Jr.",               pl: "KAPUSO PM",                   cat: "Both",               note: "Relatives in elective office:\nMunir Arbison - Sulu 2nd District Rep. (father)\n\nContractor link:\nHis relative Ash-Ashid Arbison is the president of Nirrain Construction and Supply Corporation, a public works contractor." },
    { name: "Kenneth Paolo Tereng",            pl: "KM NGAYON NA",                cat: "none",               note: "" },
    { name: "Aiman Tan",                       pl: "KUSUG TAUSUG",                cat: "Dynasty",            note: "Relatives in elective office:\nAbdusakur Tan II - Sulu Governor\nAbdusakur Tan - Sulu Vice Governor\nSamier Tan - Sulu 1st District Rep.\nShihla Tan-Hayudini - Maimbung, Sulu Mayor\nShernee Tan-Tambut - Maimbung, Sulu Vice Mayor" },
    { name: "Allan Ty",                        pl: "LPGMA",                       cat: "Dynasty",            note: "Relatives in elective office:\nArnel Ty - former LPGMA rep (brother; held the post before him)" },
    { name: "Ferdinand Beltran",               pl: "MAGBUBUKID",                  cat: "Contractor-linked",  note: "He is the owner of Ferdstar Builders, a public works contractor. His daughter-in-law Maria Criselda Beltran is the owner of 11-16 Construction, another public works contractor. A technical staff of 11-16 Construction, Nikko Alfaro, is also listed as a campaign donor of Magbubukid Party-list." },
    { name: "Girlie Veloso",                   pl: "MALASAKIT@BAYANIHAN",         cat: "none",               note: "" },
    { name: "Maria Nina Francesca Lacson",     pl: "Manila Teachers",             cat: "Dynasty",            note: "Relatives in elective office:\nVirgilio Lacson - former Manila Teachers rep (father; held the post before her)" },
    { name: "Leila de Lima",                   pl: "ML",                          cat: "none",               note: "" },
    { name: "Arthur C. Yap",                   pl: "MURANG KURYENTE",             cat: "none",               note: "" },
    { name: "Florabel Yatco Co",              pl: "NANAY",                       cat: "Dynasty",            note: "Relatives in elective office:\nDonna Yatco - Biñan, Laguna councilor (sister-in-law)" },
    { name: "Maria Kristina Jihan Bana Glepa", pl: "ONE COOP",                   cat: "Dynasty",            note: "Relatives in elective office:\nCyril Glepa - Molave, Zamboanga del Sur Mayor (husband)\nRuel Cabardo - Tambulig, Zamboanga del Sur (uncle)\nDivina Yu - Zamboanga del Sur Governor (aunt)" },
    { name: "Presley Cheng De Jesus",          pl: "PHILRECA",                    cat: "Franchisee-linked",  note: "His party-list received campaign donations from general managers of electric cooperatives: Jose Raul Saniel Jr. of Zamboanga del Sur I Electric Cooperative, Jose F. Bognot Jr.* of Tarlac II Electric Cooperative, and Maria Elizabeth Urbano of Pampanga III Electric Cooperative. Electric cooperatives are required to secure legislative franchises before they can operate.\n* Bognot passed away in June 2025. He was Tarelco II's general manager when he made the donation, according to the party-list's disclosure." },
    { name: "Franz Vincent Legazpi",           pl: "PINOY WORKERS",               cat: "none",               note: "" },
    { name: "Harold Duterte",                 pl: "PPP",                         cat: "Dynasty",            note: "Relatives in elective office:\nPaolo Duterte - Davao City First District Rep. (cousin)\nSara Duterte - Vice President (cousin)\nSebastian Duterte - Davao City Mayor (cousin)\nOmar Vincent Duterte - Davao City Second District Rep. (nephew)\nRodrigo 'Rigo' Duterte II - Davao City Vice Mayor (nephew)" },
    { name: "Jernie Jett Valdecañas Nisay",    pl: "PUSONG PINOY",                cat: "Contractor-linked",  note: "He is the manager of JVN Construction and Trading." },
    { name: "Paolo Henry Magbitang Marcoleta", pl: "SAGIP",                       cat: "Dynasty",            note: "Relatives in elective office:\nRodante Marcoleta - Senator (father)" },
    { name: "Rodolfo Epimaco Malicse Ordanes", pl: "SENIOR CITIZENS PARTYLIST",   cat: "none",               note: "" },
    { name: "Ching Bernos",                    pl: "SOLID NORTH PARTY",           cat: "Both",               note: "Relatives in elective office:\nJB Bernos - Abra Lone District Rep. (husband)\nJaja Bernos - Bucay, Abra Mayor (daughter)\n\nContractor link: Her party-list received campaign donations from government contractors: Kevin Samidan, co-owner of M.G. Samidan Construction and Development Corporation, Dominguez Alones, authorized managing officer of Random Builders, and Herald Olsim, authorized managing officer of Olsim Construction." },
    { name: "Rolando Macasaet",               pl: "SSS-GSIS PENSIONADO",         cat: "Dynasty",            note: "Relatives in elective office:\nEmilio 'Mico' Yap-Macasaet - Tarlac Provincial Board Member (son)" },
    { name: "Arlyn Ayon",                     pl: "SWERTE",                      cat: "none",               note: "" },
    { name: "Jose Teves Jr.",                 pl: "TGP",                         cat: "Dynasty",            note: "Relatives in elective office:\nPaolo Teves - Baras, Catanduanes Mayor (son)" },
    { name: "Andrew Julian Romualdez",         pl: "TINGOG",                      cat: "Both",               note: "Relatives in elective office:\nFerdinand Martin Romualdez - Leyte 1st District Rep. (father)\nYedda Marie Romualdez - Tingog party-list Rep. (mother)\nMarty Romualdez - Tacloban City councilor (brother)\nFerdinand Marcos Jr. - President (uncle)\nFerdinand Alexander 'Sandro' Marcos - Ilocos Norte 1st District Rep. (cousin)\nMa. Imelda Josefa 'Imee' Marcos - Senator (aunt)\nMatthew Marcos Manotoc - Ilocos Norte vice governor (cousin)\n\nContractor link:\nHis party-list received donations from government contractors: Gilbert O. Consebido, owner of G.O.C. Builders and Aqualine Construction Corporation, and Janice N. Lin, owner of Tacloban 6500, Inc. (formerly LTZ Construction and Supply)." },
    { name: "Jude Acidre",                    pl: "TINGOG",                      cat: "Contractor-linked",  note: "His party-list received donations from government contractors: Gilbert O. Consebido, owner of G.O.C. Builders and Aqualine Construction Corporation, and Janice N. Lin, owner of Tacloban 6500, Inc. (formerly LTZ Construction and Supply)." },
    { name: "Yedda Marie Romualdez",           pl: "TINGOG",                      cat: "Both",               note: "Relatives in elective office:\nFerdinand Martin Romualdez - Leyte 1st District Rep. (husband)\nAndrew Julian Romualdez - Tingog party-list Rep. (son)\nMarty Romualdez - Tacloban City councilor (son)\nFerdinand Marcos Jr. - President (cousin-in-law)\nFerdinand Alexander 'Sandro' Marcos - Ilocos Norte 1st District Rep. (nephew)\nMa. Imelda Josefa 'Imee' Marcos - Senator (cousin-in-law)\nMatthew Marcos Manotoc - Ilocos Norte vice governor (nephew)\n\nContractor link:\nHer party-list received donations from government contractors: Gilbert O. Consebido, owner of G.O.C. Builders and Aqualine Construction Corporation, and Janice N. Lin, owner of Tacloban 6500, Inc. (formerly LTZ Construction and Supply)." },
    {name: "Johanne Monich Bautista",         pl: "TRABAHO",                     cat: "none",               note: "" },
    { name: "Raymond Mendoza",                pl: "TUCP",                        cat: "Dynasty",            note: "Relatives in elective office:\nLala Taliño Mendoza - Cotabato governor (wife)\nAlana Samantha Santos - Cotabato 3rd District Rep. (stepdaughter)\nYedda Romualdez - Tingog party-list rep (niece)" },
    { name: "Milagros Magsaysay",             pl: "United Senior Citizens",      cat: "Dynasty",            note: "Relatives in elective office:\nMiguel Corleone Buniag Magsaysay - La Union provincial board member (grandson)\nMilano Carlitos Buniag Magsaysay - San Juan, La Union municipal councilor (grandson)" },
    { name: "James Ang Jr.",                  pl: "USWAG ILONGGO",               cat: "Contractor-linked",  note: "He was a shareholder of Allencon Development Corporation, a public works contractor. His relatives own IBC International Builders Corporation, another public works contractor. His party-list also received campaign donations from public works contractors Manuel R. Bulaong Jr. and Eduard C. Chong. Bulaong is the president of MRBII Construction Corporation and Chong is the president of EC Structural Composites, Inc." }
];

// ── Category colour map (mirrors CSS vars, used for inline annotation text) ──
const CAT_COLOR = {
    "Dynasty":           "#BF3B3B",
    "Both":              "#D9814E",
    "Contractor-linked": "#E0B04B",
    "Franchisee-linked": "#E0B04B",
    "none":              "#5897A6",
};

const CAT_LABEL = {
    "Dynasty":           "Dynasty",
    "Both":              "Dynasty & Contractor",
    "Contractor-linked": "Contractor-linked",
    "Franchisee-linked": "Franchisee-linked",
    "none":              "No known ties",
};

// ── Sort alphabetically by last name ──
const suffixes = ["Jr.", "Sr.", "II", "III", "IV", "V"];
const compoundLastNames = ["delos santos", "de jesus", "de lima", "san fernando"];

const getLastName = name => {
    const normalized = name.trim().toLowerCase();

    // Check for known compound last names first
    const compound = compoundLastNames.find(c => normalized.endsWith(c));
    if (compound) return compound;

    const parts = name.trim().split(/\s+/);
    let last = parts.pop();
    if (suffixes.includes(last)) {
        last = parts.pop();
    }
    return last.toLowerCase();
};

reps.sort((a, b) => getLastName(a.name).localeCompare(getLastName(b.name)));

// ── Image path: direct filename lookup ──
const IMG = {
    "Jonathan Clement Abalos":         "ABALOS_JC_M.jpg",
    "Jude Acidre":                     "ACIDRE_JUDE_A.jpg",
    "James Ang Jr.":                   "ANG_JAMES_JOJO_JR.jpg",
    "Milagros Magsaysay":              "AQUINO-MAGSAYSAY_MILAGROS.jpg",
    "Munir Arbison Jr.":               "ARBISON_MUNIR_N_JR.jpg",
    "Arlyn Ayon":                      "AYON_ARLYN_P.jpg",
    "Johanne Monich Bautista":         "BAUTISTA_JOHANNE_MONICH_G.jpg",
    "Claudine Bautista-Lim":          "BAUTISTA-LIM_CLAUDINE_DIANA_D.jpg",
    "Ferdinand Beltran":               "BELTRAN_FERDINAND_B1_L.jpg",
    "Ching Bernos":                    "BERNOS_CHING_B.jpg",
    "Nicanor Briones":                 "BRIONES_NICANOR_M.jpg",
    "Perci Cendaña":                   "CENDAÑA_PERCIVAL_PERCI copy.jpg",
    "Jan Franz Chan":                  "CHAN_JAN_FRANZ.png",
    "Renee Co":                        "CO_RENEE_LOUISE_M.jpg",
    "Sergio Dagooc":                   "DAGOOC_SERGIO_C.jpg",
    "Presley Cheng De Jesus":          "DE_JESUS_PRESLEY_C.jpg",
    "Leila de Lima":                   "DE_LIMA_LEILA_M.jpg",
    "Alfred Delos Santos":             "DELOS_SANTOS_ALFRED_C.jpg",
    "Chel Diokno":                     "DIOKNO_JOSE_MANUEL_TADEO_CHEL_I.jpg",
    "Harold Duterte":                 "DUTERTE_HAROLD_JAMES_T.jpg",
    "Sarah Elago":                     "ELAGO_SARAH_JANE_I.jpg",
    "Felimon Espares":                 "ESPARES_FELIMON_M.jpg",
    "Robert Raymond Estrella":         "ESTRELLA_ROBERT_RAYMUND_ESKIMO_M.jpg",
    "Alfredo Garbin Jr.":              "GARBIN_ALFREDO_JR_A.jpg",
    "Tirso Edwin Gardiola":            "GARDIOLA_EDWIN_L.jpg",
    "Maria Kristina Jihan Bana Glepa": "GLEPA_MARIA_KRISTINA_JIHAN_B.jpg",
    "Rodge Gutierrez":                 "GUTIERREZ_RAMON_RODRIGO_L.jpg",
    "Dadah Kiram Ismula":              "ISMULA_DADAH_KIRAM.jpg",
    "Manuel Frederick Ong Ko":         "KO_MANUEL_MANMAN_O.jpg",
    "Maria Nina Francesca Lacson":     "LACSON_MANINA_FRANCESCA_P.png",
    "Sonny Lagon":                     "LAGON_SONNY_SL_L.jpg",
    "Franz Vincent Legazpi":           "LEGAZPI_FRANZ_VINCENT_F.jpg",
    "Marcelino Libanan":               "LIBANAN_MARCELINO_C.png",
    "Maria Cristina Lopez":            "LOPEZ_MA_CRISTINA_TALAVERA.jpg",
    "Rolando Macasaet":               "MACASAET_ROLANDO_LEDESMA.jpg",
    "Paolo Henry Magbitang Marcoleta": "MARCOLETA_PAOLO_HENRY_M.jpg",
    "Raymond Mendoza":                "MENDOZA_RAYMOND_DEMOCRITO_C.jpg",
    "Iris Marie Montes":               "MONTES_IRIS_MARIE_DEMESA.jpg",
    "Roberto Gerard Nazal Jr.":        "NAZAL_ROBERT.jpg",
    "Jernie Jett Valdecañas Nisay":    "NISAY_JERNIE_JETT_V.jpg",
    "Henry F. Oaminal Jr.":            "OAMINAL_HENRY_INDY_F_JR.png",
    "Nathaniel Oducado":               "ODUCADO_NATHANIEL_M.jpg",
    "Rodolfo Epimaco Malicse Ordanes": "ORDANES_RODOLFO_OMPONG_M.jpg",
    "Jan Rurik Padiernos":             "PADIERNOS_JAN_ATTY_JP.jpg",
    "Brian Poe Llamanzares":           "POE_BRIAN.jpg",
    "Bryan Revilla":                   "REVILLA_BRYAN_B.jpg",
    "Terry Ridon":                     "RIDON_TERRY_L.jpg",
    "Maximo Rodriguez Jr.":            "RODRIGUEZ_MAXIMO_B_JR.jpg",
    "Andrew Julian Romualdez":         "ROMUALDEZ_ANDREW_JULIAN_K.jpg",
    "Yedda Marie Romualdez":           "ROMUALDEZ_YEDDA_MARIE_K.jpg",
    "Eli San Fernando":                "SAN_FERNANDO_ELIJAH_RUMBAOA.jpg",
    "Richelle Singson-Michael":        "SINGSON_RICHELLE.jpg",
    "Aiman Tan":                       "TAN_AIMAN_T.png",
    "Caroline Tanchay":               "TANCHAY_CAROLINE_L.jpg",
    "Kenneth Paolo Tereng":            "TERENG_KENNETH_PAOLO.jpg",
    "Jose Teves Jr.":                 "TEVES_JOSE_BONG_J_JR.jpg",
    "Antonio Tinio":                   "TINIO_ANTONIO_L.jpg",
    "Jocelyn Tulfo":                   "TULFO_JOCELYN_P.jpg",
    "Jeffrey Soriano":                   "SORIANO_JEFFREY.png",
    "Allan Ty":                        "TY_ALLAN_U.jpg",
    "Girlie Veloso":                   "VELOSO_GIRLIE_E.jpg",
    "Eddie Villanueva":                "VILLANUEVA_EDUARDO_BRO_EDDIE_C.jpg",
    "Arthur C. Yap":                   "YAP_ARTHUR_C.jpg",
    "Florabel Yatco Co":              "YATCO_FLORABEL_C.jpg",
    "Nathaniel Oducado":               "ODUCADO_NATHANIEL_M.jpg",
};

function imgPath(name) {
    const file = IMG[name];
    if (!file) {
        console.warn('No image mapped for:', name);
        return 'images/placeholder.jpg';
    }
    return 'images/' + file;
}

// ═══════════════════════════════════════════════
// BUILD PHOTO GRID
// ═══════════════════════════════════════════════

const photoGrid = document.getElementById('photoGrid');

reps.forEach(r => {
    const card = document.createElement('div');
    card.className    = 'rep-card';
    card.dataset.cat  = r.cat;
    card.dataset.name = r.name;

    // Portrait image
    const img = document.createElement('img');
    img.src     = imgPath(r.name);
    img.alt     = r.name;
    img.loading = 'lazy';

    // Category corner square (visible when highlighted / in explore mode)
    const square = document.createElement('div');
    square.className = 'cat-square';

    // Name tag — shows on hover (name + party + tag only, no annotation)
    const nameTag = document.createElement('div');
    nameTag.className = 'name-tag';
    nameTag.innerHTML = `
        <span class="nt-name">${r.name}</span>
        <span class="nt-pl">${r.pl}</span>
        <span class="nt-cat" style="color:${CAT_COLOR[r.cat]}">${CAT_LABEL[r.cat]}</span>
    `;

    card.append(img, square, nameTag);
    photoGrid.appendChild(card);
});

// ═══════════════════════════════════════════════
// EXPLORE TOOLTIP
// ═══════════════════════════════════════════════

const tooltip    = document.getElementById('annTooltip');
const attName    = tooltip.querySelector('.att-name');
const attPl      = tooltip.querySelector('.att-pl');
const attCat     = tooltip.querySelector('.att-cat');
const attBody    = tooltip.querySelector('.att-body');
const annClose   = document.getElementById('annClose');

let tooltipStuck   = false;   // pinned by click
let currentHovered = null;    // card currently under cursor
let hideTimer      = null;

const TOOLTIP_OFFSET = 12;   // px gap between card and tooltip

function positionTooltip(cardEl) {
    const rect  = cardEl.getBoundingClientRect();
    const tw    = tooltip.offsetWidth;
    const th    = tooltip.offsetHeight;
    const vw    = window.innerWidth;
    const vh    = window.innerHeight;

    // Prefer right of card; fall back to left
    let left = rect.right + TOOLTIP_OFFSET;
    if (left + tw > vw - 8) left = rect.left - tw - TOOLTIP_OFFSET;

    // Align top with card, nudge up if it overflows bottom
    let top = rect.top;
    if (top + th > vh - 8) top = vh - th - 8;
    if (top < 8) top = 8;

    tooltip.style.left = left + 'px';
    tooltip.style.top  = top  + 'px';
}

function showTooltip(r, cardEl) {
    clearTimeout(hideTimer);

    attName.textContent      = r.name;
    attPl.textContent        = r.pl;
    attCat.textContent       = CAT_LABEL[r.cat];
    attCat.style.color       = CAT_COLOR[r.cat];

    if (r.note) {
        attBody.innerHTML    = '';
        attBody.textContent  = r.note;
        attBody.classList.remove('att-no-ties');
    } else {
        attBody.textContent  = 'No known ties on record.';
        attBody.classList.add('att-no-ties');
    }

    tooltip.classList.add('visible');
    // Re-position after content reflow
    // requestAnimationFrame(() => positionTooltip(cardEl));

    // Check after reflow whether content actually overflows
    requestAnimationFrame(() => {
        positionTooltip(cardEl);
        const isScrollable = attBody.scrollHeight > attBody.clientHeight;
        attBody.classList.toggle('is-scrollable', isScrollable);
    });
}

function hideTooltip(force = false) {
    if (tooltipStuck && !force) return;
    hideTimer = setTimeout(() => {
        tooltip.classList.remove('visible', 'stuck');
        tooltipStuck = false;
    }, 120);
}

function stickTooltip() {
    tooltipStuck = true;
    tooltip.classList.add('stuck');
    annClose.style.display = 'block';
}

function closeTooltip() {
    tooltipStuck = false;
    tooltip.classList.remove('visible', 'stuck');
    annClose.style.display = '';
    currentHovered = null;
}

attBody.addEventListener('scroll', () => {
    const atBottom = attBody.scrollHeight - attBody.scrollTop <= attBody.clientHeight + 2;
    attBody.classList.toggle('is-scrollable', !atBottom);
});

annClose.addEventListener('click', (e) => {
    e.stopPropagation();
    closeTooltip();
});

// Keep tooltip open when cursor moves onto it
tooltip.addEventListener('mouseenter', () => clearTimeout(hideTimer));
tooltip.addEventListener('mouseleave', () => { if (!tooltipStuck) hideTooltip(); });

// Wire up cards once explore mode is active
function attachCardTooltips() {
    const isMobile = () => window.innerWidth <= 600;

    allCards.forEach(card => {
        const rep = reps.find(r => r.name === card.dataset.name);
        if (!rep) return;

        card.addEventListener('mouseenter', () => {
            if (tooltipStuck) return;
            if (isMobile()) return;
            currentHovered = card;
            showTooltip(rep, card);
        });

        card.addEventListener('mouseleave', () => {
            if (tooltipStuck) return;
            if (isMobile()) return;
            currentHovered = null;
            hideTooltip();
        });

        card.addEventListener('click', (e) => {
            e.stopPropagation();
            if (tooltipStuck && currentHovered === card) {
                // Second click on same card → close
                closeTooltip();
            } else {
                currentHovered = card;
                showTooltip(rep, card);
                stickTooltip();
            }
        });
    });

    // Tap on backdrop (outside tooltip and cards) closes tooltip
    document.addEventListener('click', (e) => {
        if (tooltipStuck && !tooltip.contains(e.target) && !e.target.closest('.rep-card')) {
            closeTooltip();
        }
    });
}

let tooltipsAttached = false;

// ═══════════════════════════════════════════════
// SCROLL ENGINE
// ═══════════════════════════════════════════════

const allCards    = Array.from(photoGrid.querySelectorAll('.rep-card'));
const panels      = ['p1', 'p2', 'p3', 'p4', 'p5'].map(id => document.getElementById(id));
const scrollySec  = document.getElementById('scrollySection');
const progressBar = document.getElementById('progressBar');

let lastFrame = -1;
let rafId     = null;

// ── Apply card highlight/dim state for a given frame ──
function applyCardStates(frame) {
    allCards.forEach(card => {
        const cat = card.dataset.cat;
        const dot = card.querySelector('.cat-square');

        card.classList.remove('dimmed', 'highlighted');
        dot.style.opacity = '0';

        if (frame <= 0) {
            // All portraits shown at full opacity — no treatment
            return;
        }

        if (frame === 1) {
            // Highlight dynasty members (Dynasty + Both)
            if (cat === 'Dynasty' || cat === 'Both') {
                card.classList.add('highlighted');
                dot.style.opacity = '1';
            } else {
                card.classList.add('dimmed');
            }

        } else if (frame === 2) {
            // Highlight contractor-linked (Contractor + Franchisee + Both)
            if (cat === 'Contractor-linked' || cat === 'Franchisee-linked' || cat === 'Both') {
                card.classList.add('highlighted');
                dot.style.opacity = '1';
            } else {
                card.classList.add('dimmed');
            }

        } else if (frame === 3) {
            // Highlight only those with both ties
            if (cat === 'Both') {
                card.classList.add('highlighted');
                dot.style.opacity = '1';
            } else {
                card.classList.add('dimmed');
            }

        } else if (frame === 4) {
            // Explore mode — all visible, squares on for all categories, hover annotations active
            document.body.classList.add('explore-mode');
            if (!tooltipsAttached) {
                attachCardTooltips();
                tooltipsAttached = true;
            }
            card.querySelector('.cat-square').style.opacity = '1';
        }

        if (frame < 4) {
            document.body.classList.remove('explore-mode');
            closeTooltip();
        }
    });
}

// ── Scroll-ticker panel animation ──
//
// Each panel travels on the Y axis relative to the card container:
//   • Enters from BELOW the viewport  →  translateY starts at +100vh
//   • Rests at bottom of card         →  translateY = 0  (fully in)
//   • Exits UPWARD, fading out at 20% viewport height from top
//
// rawProgress is the continuous scroll float (0 = frame 0, 1 = frame 1, …)
// Panel i is "active" when rawProgress is closest to i.

function animatePanels(rawProgress) {
    const vh = window.innerHeight;
    const isMobile = window.innerWidth <= 600;

    panels.forEach((panel, i) => {
        const dist = rawProgress - i;

        let opacity, translateY;

        if (dist < -1 || dist > 1) {
            opacity    = 0;
            translateY = dist < 0 ? vh * 0.6 : -(vh * 0.6);

        } else if (dist < 0) {
            // ENTER: t goes 0 → 1 as panel approaches resting position
            const t = 1 + dist;
            translateY = vh * 0.8 * (1 - t);

            // Fully visible at t=1 (resting pos = 20% from bottom via CSS)
            // Fully opaque by t=0.9
            opacity = t < 0.9 ? 0 : (t - 0.9) / 0.1;

        } else {
            // EXIT: t goes 0 → 1 as panel moves upward
            const t = dist;

            translateY = -(vh * 0.6) * Math.pow(t, 1.4);

            // On mobile, exit faster so it doesn't feel sticky
            const exitStart = isMobile ? 0.2 : 0.5;
            const exitDuration = isMobile ? 0.15 : 0.2;

            // Stay fully visible briefly, then fade out fast
            opacity = t < 0.5 ? 1 : 1 - (t - 0.5) / 0.2;
        }

        opacity = Math.max(0, Math.min(1, opacity));

        panel.style.opacity   = opacity.toFixed(3);
        panel.style.transform = `translateY(${translateY.toFixed(1)}px)`;
        panel.classList.toggle('active', opacity > 0.15);
    });
}

// ── Main scroll handler ──
function onScroll() {
    const offset      = window.scrollY - (scrollySec.offsetTop || 0);
    const vh          = window.innerHeight;
    const rawProgress = offset / vh;
    const frame       = Math.max(0, Math.min(4, Math.floor(rawProgress)));

    // Card states change only on frame boundary
    if (frame !== lastFrame) {
        lastFrame = frame;
        applyCardStates(frame);
    }

    // Panel animation runs every scroll tick
    animatePanels(rawProgress);

    // Progress bar
    const totalScrollH = scrollySec.offsetHeight - vh;
    const pct = totalScrollH > 0 ? Math.min(100, (offset / totalScrollH) * 100) : 0;
    progressBar.style.width = pct + '%';
}

window.addEventListener('scroll', () => {
    if (rafId) cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(onScroll);
}, { passive: true });

// Initialise on load
onScroll();
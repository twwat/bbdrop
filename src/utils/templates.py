"""Template loading, conditional processing, and gallery artifact generation."""

import os
import json
from datetime import datetime
from typing import Optional

from src.utils.logger import log
from src.utils.paths import (
    __version__,
    get_central_store_base_path,
    get_central_storage_path,
    load_user_defaults,
)


# ISO 3166-1 country code mappings for [flag] tag support
FLAG_CODES = {
    "004": "af",
    "008": "al",
    "010": "aq",
    "012": "dz",
    "016": "as",
    "020": "ad",
    "024": "ao",
    "028": "ag",
    "031": "az",
    "032": "ar",
    "036": "au",
    "040": "at",
    "044": "bs",
    "048": "bh",
    "050": "bd",
    "051": "am",
    "052": "bb",
    "056": "be",
    "060": "bm",
    "064": "bt",
    "068": "bo",
    "070": "ba",
    "072": "bw",
    "074": "bv",
    "076": "br",
    "084": "bz",
    "086": "io",
    "090": "sb",
    "092": "vg",
    "096": "bn",
    "100": "bg",
    "104": "mm",
    "108": "bi",
    "112": "by",
    "116": "kh",
    "120": "cm",
    "124": "ca",
    "132": "cv",
    "136": "ky",
    "140": "cf",
    "144": "lk",
    "148": "td",
    "152": "cl",
    "156": "cn",
    "158": "tw",
    "162": "cx",
    "166": "cc",
    "170": "co",
    "174": "km",
    "175": "yt",
    "178": "cg",
    "180": "cd",
    "184": "ck",
    "188": "cr",
    "191": "hr",
    "192": "cu",
    "196": "cy",
    "203": "cz",
    "204": "bj",
    "208": "dk",
    "212": "dm",
    "214": "do",
    "218": "ec",
    "222": "sv",
    "226": "gq",
    "231": "et",
    "232": "er",
    "233": "ee",
    "234": "fo",
    "238": "fk",
    "239": "gs",
    "242": "fj",
    "246": "fi",
    "248": "ax",
    "250": "fr",
    "254": "gf",
    "258": "pf",
    "260": "tf",
    "262": "dj",
    "266": "ga",
    "268": "ge",
    "270": "gm",
    "275": "ps",
    "276": "de",
    "288": "gh",
    "292": "gi",
    "296": "ki",
    "300": "gr",
    "304": "gl",
    "308": "gd",
    "312": "gp",
    "316": "gu",
    "320": "gt",
    "324": "gn",
    "328": "gy",
    "332": "ht",
    "334": "hm",
    "336": "va",
    "340": "hn",
    "344": "hk",
    "348": "hu",
    "352": "is",
    "356": "in",
    "360": "id",
    "364": "ir",
    "368": "iq",
    "372": "ie",
    "376": "il",
    "380": "it",
    "384": "ci",
    "388": "jm",
    "392": "jp",
    "398": "kz",
    "400": "jo",
    "404": "ke",
    "408": "kp",
    "410": "kr",
    "414": "kw",
    "417": "kg",
    "418": "la",
    "422": "lb",
    "426": "ls",
    "428": "lv",
    "430": "lr",
    "434": "ly",
    "438": "li",
    "440": "lt",
    "442": "lu",
    "446": "mo",
    "450": "mg",
    "454": "mw",
    "458": "my",
    "462": "mv",
    "466": "ml",
    "470": "mt",
    "474": "mq",
    "478": "mr",
    "480": "mu",
    "484": "mx",
    "492": "mc",
    "496": "mn",
    "498": "md",
    "499": "me",
    "500": "ms",
    "504": "ma",
    "508": "mz",
    "512": "om",
    "516": "na",
    "520": "nr",
    "524": "np",
    "528": "nl",
    "531": "cw",
    "533": "aw",
    "534": "sx",
    "535": "bq",
    "540": "nc",
    "548": "vu",
    "554": "nz",
    "558": "ni",
    "562": "ne",
    "566": "ng",
    "570": "nu",
    "574": "nf",
    "578": "no",
    "580": "mp",
    "581": "um",
    "583": "fm",
    "584": "mh",
    "585": "pw",
    "586": "pk",
    "591": "pa",
    "598": "pg",
    "600": "py",
    "604": "pe",
    "608": "ph",
    "612": "pn",
    "616": "pl",
    "620": "pt",
    "624": "gw",
    "626": "tl",
    "630": "pr",
    "634": "qa",
    "638": "re",
    "642": "ro",
    "643": "ru",
    "646": "rw",
    "652": "bl",
    "654": "sh",
    "659": "kn",
    "660": "ai",
    "662": "lc",
    "663": "mf",
    "666": "pm",
    "670": "vc",
    "674": "sm",
    "678": "st",
    "682": "sa",
    "686": "sn",
    "688": "rs",
    "690": "sc",
    "694": "sl",
    "702": "sg",
    "703": "sk",
    "704": "vn",
    "705": "si",
    "706": "so",
    "710": "za",
    "716": "zw",
    "724": "es",
    "728": "ss",
    "729": "sd",
    "732": "eh",
    "740": "sr",
    "744": "sj",
    "748": "sz",
    "752": "se",
    "756": "ch",
    "760": "sy",
    "762": "tj",
    "764": "th",
    "768": "tg",
    "772": "tk",
    "776": "to",
    "780": "tt",
    "784": "ae",
    "788": "tn",
    "792": "tr",
    "795": "tm",
    "796": "tc",
    "798": "tv",
    "800": "ug",
    "804": "ua",
    "807": "mk",
    "818": "eg",
    "826": "gb",
    "831": "gg",
    "832": "je",
    "833": "im",
    "834": "tz",
    "840": "us",
    "850": "vi",
    "854": "bf",
    "858": "uy",
    "860": "uz",
    "862": "ve",
    "876": "wf",
    "882": "ws",
    "887": "ye",
    "894": "zm",
    "abw": "aw",
    "ad": "ad",
    "ae": "ae",
    "af": "af",
    "afg": "af",
    "afghanistan": "af",
    "ag": "ag",
    "ago": "ao",
    "ai": "ai",
    "aia": "ai",
    "al": "al",
    "ala": "ax",
    "aland islands": "ax",
    "alb": "al",
    "albania": "al",
    "algeria": "dz",
    "am": "am",
    "american samoa": "as",
    "and": "ad",
    "andorra": "ad",
    "angola": "ao",
    "anguilla": "ai",
    "antarctica": "aq",
    "antigua and barbuda": "ag",
    "ao": "ao",
    "aq": "aq",
    "ar": "ar",
    "are": "ae",
    "arg": "ar",
    "argentina": "ar",
    "arm": "am",
    "armenia": "am",
    "aruba": "aw",
    "as": "as",
    "asm": "as",
    "at": "at",
    "ata": "aq",
    "atf": "tf",
    "atg": "ag",
    "au": "au",
    "aus": "au",
    "australia": "au",
    "austria": "at",
    "aut": "at",
    "aw": "aw",
    "ax": "ax",
    "az": "az",
    "aze": "az",
    "azerbaijan": "az",
    "ba": "ba",
    "bahamas": "bs",
    "bahrain": "bh",
    "bangladesh": "bd",
    "barbados": "bb",
    "bb": "bb",
    "bd": "bd",
    "bdi": "bi",
    "be": "be",
    "bel": "be",
    "belarus": "by",
    "belgium": "be",
    "belize": "bz",
    "ben": "bj",
    "benin": "bj",
    "bermuda": "bm",
    "bes": "bq",
    "bf": "bf",
    "bfa": "bf",
    "bg": "bg",
    "bgd": "bd",
    "bgr": "bg",
    "bh": "bh",
    "bhr": "bh",
    "bhs": "bs",
    "bhutan": "bt",
    "bi": "bi",
    "bih": "ba",
    "bj": "bj",
    "bl": "bl",
    "blm": "bl",
    "blr": "by",
    "blz": "bz",
    "bm": "bm",
    "bmu": "bm",
    "bn": "bn",
    "bo": "bo",
    "bol": "bo",
    "bolivia": "bo",
    "bonaire": "bq",
    "bosnia and herzegovina": "ba",
    "botswana": "bw",
    "bouvet island": "bv",
    "bq": "bq",
    "br": "br",
    "bra": "br",
    "brazil": "br",
    "brb": "bb",
    "british indian ocean territory": "io",
    "brn": "bn",
    "brunei darussalam": "bn",
    "bs": "bs",
    "bt": "bt",
    "btn": "bt",
    "bulgaria": "bg",
    "burkina faso": "bf",
    "burundi": "bi",
    "bv": "bv",
    "bvt": "bv",
    "bw": "bw",
    "bwa": "bw",
    "by": "by",
    "bz": "bz",
    "ca": "ca",
    "cabo verde": "cv",
    "caf": "cf",
    "cambodia": "kh",
    "cameroon": "cm",
    "can": "ca",
    "canada": "ca",
    "cayman islands": "ky",
    "cc": "cc",
    "cck": "cc",
    "cd": "cd",
    "central african republic": "cf",
    "cf": "cf",
    "cg": "cg",
    "ch": "ch",
    "chad": "td",
    "che": "ch",
    "chile": "cl",
    "chinac": "cn",
    "chl": "cl",
    "chn": "cn",
    "christmas island": "cx",
    "ci": "ci",
    "civ": "ci",
    "ck": "ck",
    "cl": "cl",
    "cm": "cm",
    "cmr": "cm",
    "cn": "cn",
    "co": "co",
    "cocos keeling islands": "cc",
    "cod": "cd",
    "cog": "cg",
    "cok": "ck",
    "col": "co",
    "colombia": "co",
    "com": "km",
    "comoros": "km",
    "congo": "cd",
    "cook islands": "ck",
    "costa rica": "cr",
    "cote divoire": "ci",
    "cpv": "cv",
    "cr": "cr",
    "cri": "cr",
    "croatia": "hr",
    "cu": "cu",
    "cub": "cu",
    "cuba": "cu",
    "curacao": "cw",
    "cuw": "cw",
    "cv": "cv",
    "cw": "cw",
    "cx": "cx",
    "cxr": "cx",
    "cy": "cy",
    "cym": "ky",
    "cyp": "cy",
    "cyprus": "cy",
    "cz": "cz",
    "cze": "cz",
    "czechia": "cz",
    "de": "de",
    "denmark": "dk",
    "deu": "de",
    "dj": "dj",
    "dji": "dj",
    "djibouti": "dj",
    "dk": "dk",
    "dm": "dm",
    "dma": "dm",
    "dnk": "dk",
    "do": "do",
    "dom": "do",
    "dominica": "dm",
    "dominican republic": "do",
    "dz": "dz",
    "dza": "dz",
    "ec": "ec",
    "ecu": "ec",
    "ecuador": "ec",
    "ee": "ee",
    "eg": "eg",
    "egy": "eg",
    "egypt": "eg",
    "eh": "eh",
    "el salvador": "sv",
    "equatorial guinea": "gq",
    "er": "er",
    "eri": "er",
    "eritrea": "er",
    "es": "es",
    "esh": "eh",
    "esp": "es",
    "est": "ee",
    "estonia": "ee",
    "eswatini": "sz",
    "et": "et",
    "eth": "et",
    "ethiopia": "et",
    "falkland islands malvinas": "fk",
    "faroe islands": "fo",
    "fi": "fi",
    "fiji": "fj",
    "fin": "fi",
    "finland": "fi",
    "fj": "fj",
    "fji": "fj",
    "fk": "fk",
    "flk": "fk",
    "fm": "fm",
    "fo": "fo",
    "fr": "fr",
    "fra": "fr",
    "france": "fr",
    "french guiana": "gf",
    "french polynesia": "pf",
    "french southern territories": "tf",
    "fro": "fo",
    "fsm": "fm",
    "ga": "ga",
    "gab": "ga",
    "gabon": "ga",
    "gambia": "gm",
    "gb": "gb",
    "gbr": "gb",
    "gd": "gd",
    "ge": "ge",
    "geo": "ge",
    "georgia": "ge",
    "germany": "de",
    "gf": "gf",
    "gg": "gg",
    "ggy": "gg",
    "gh": "gh",
    "gha": "gh",
    "ghana": "gh",
    "gi": "gi",
    "gib": "gi",
    "gibraltar": "gi",
    "gin": "gn",
    "gl": "gl",
    "glp": "gp",
    "gm": "gm",
    "gmb": "gm",
    "gn": "gn",
    "gnb": "gw",
    "gnq": "gq",
    "gp": "gp",
    "gq": "gq",
    "gr": "gr",
    "grc": "gr",
    "grd": "gd",
    "greece": "gr",
    "greenland": "gl",
    "grenada": "gd",
    "grl": "gl",
    "gs": "gs",
    "gt": "gt",
    "gtm": "gt",
    "gu": "gu",
    "guadeloupe": "gp",
    "guam": "gu",
    "guatemala": "gt",
    "guernsey": "gg",
    "guf": "gf",
    "guinea": "gn",
    "guineabissau": "gw",
    "gum": "gu",
    "guy": "gy",
    "guyana": "gy",
    "gw": "gw",
    "gy": "gy",
    "haiti": "ht",
    "heard island and mcdonald islands": "hm",
    "hk": "hk",
    "hkg": "hk",
    "hm": "hm",
    "hmd": "hm",
    "hn": "hn",
    "hnd": "hn",
    "holy see": "va",
    "honduras": "hn",
    "hong kong": "hk",
    "hr": "hr",
    "hrv": "hr",
    "ht": "ht",
    "hti": "ht",
    "hu": "hu",
    "hun": "hu",
    "hungary": "hu",
    "iceland": "is",
    "id": "id",
    "idn": "id",
    "ie": "ie",
    "il": "il",
    "im": "im",
    "imn": "im",
    "in": "in",
    "ind": "in",
    "india": "in",
    "indonesia": "id",
    "io": "io",
    "iot": "io",
    "iq": "iq",
    "ir": "ir",
    "iran": "ir",
    "iraq": "iq",
    "ireland": "ie",
    "irl": "ie",
    "irn": "ir",
    "irq": "iq",
    "is": "is",
    "isl": "is",
    "isle of man": "im",
    "isr": "il",
    "israel": "il",
    "it": "it",
    "ita": "it",
    "italy": "it",
    "jam": "jm",
    "jamaica": "jm",
    "japan": "jp",
    "je": "je",
    "jersey": "je",
    "jey": "je",
    "jm": "jm",
    "jo": "jo",
    "jor": "jo",
    "jordan": "jo",
    "jp": "jp",
    "jpn": "jp",
    "kaz": "kz",
    "kazakhstan": "kz",
    "ke": "ke",
    "ken": "ke",
    "kenya": "ke",
    "kg": "kg",
    "kgz": "kg",
    "kh": "kh",
    "khm": "kh",
    "ki": "ki",
    "kir": "ki",
    "kiribati": "ki",
    "km": "km",
    "kn": "kn",
    "kna": "kn",
    "kor": "kr",
    "kp": "kp",
    "kr": "kr",
    "kuwait": "kw",
    "kw": "kw",
    "kwt": "kw",
    "ky": "ky",
    "kyrgyzstan": "kg",
    "kz": "kz",
    "la": "la",
    "lao": "la",
    "lao peoples democratic republic": "la",
    "latvia": "lv",
    "lb": "lb",
    "lbn": "lb",
    "lbr": "lr",
    "lby": "ly",
    "lc": "lc",
    "lca": "lc",
    "lebanon": "lb",
    "lesotho": "ls",
    "li": "li",
    "liberia": "lr",
    "libya": "ly",
    "lie": "li",
    "liechtenstein": "li",
    "lithuania": "lt",
    "lk": "lk",
    "lka": "lk",
    "lr": "lr",
    "ls": "ls",
    "lso": "ls",
    "lt": "lt",
    "ltu": "lt",
    "lu": "lu",
    "lux": "lu",
    "luxembourg": "lu",
    "lv": "lv",
    "lva": "lv",
    "ly": "ly",
    "ma": "ma",
    "mac": "mo",
    "macao": "mo",
    "madagascar": "mg",
    "maf": "mf",
    "malawi": "mw",
    "malaysia": "my",
    "maldives": "mv",
    "mali": "ml",
    "malta": "mt",
    "mar": "ma",
    "marshall islands": "mh",
    "martinique": "mq",
    "mauritania": "mr",
    "mauritius": "mu",
    "mayotte": "yt",
    "mc": "mc",
    "mco": "mc",
    "md": "md",
    "mda": "md",
    "mdg": "mg",
    "mdv": "mv",
    "me": "me",
    "mex": "mx",
    "mexico": "mx",
    "mf": "mf",
    "mg": "mg",
    "mh": "mh",
    "mhl": "mh",
    "micronesia": "fm",
    "mk": "mk",
    "mkd": "mk",
    "ml": "ml",
    "mli": "ml",
    "mlt": "mt",
    "mm": "mm",
    "mmr": "mm",
    "mn": "mn",
    "mne": "me",
    "mng": "mn",
    "mnp": "mp",
    "mo": "mo",
    "moldova": "md",
    "monaco": "mc",
    "mongolia": "mn",
    "montenegro": "me",
    "montserrat": "ms",
    "morocco": "ma",
    "moz": "mz",
    "mozambique": "mz",
    "mp": "mp",
    "mq": "mq",
    "mr": "mr",
    "mrt": "mr",
    "ms": "ms",
    "msr": "ms",
    "mt": "mt",
    "mtq": "mq",
    "mu": "mu",
    "mus": "mu",
    "mv": "mv",
    "mw": "mw",
    "mwi": "mw",
    "mx": "mx",
    "my": "my",
    "myanmar": "mm",
    "mys": "my",
    "myt": "yt",
    "mz": "mz",
    "na": "na",
    "nam": "na",
    "namibia": "na",
    "nauru": "nr",
    "nc": "nc",
    "ncl": "nc",
    "ne": "ne",
    "nepal": "np",
    "ner": "ne",
    "netherlands": "nl",
    "new caledonia": "nc",
    "new zealand": "nz",
    "nf": "nf",
    "nfk": "nf",
    "ng": "ng",
    "nga": "ng",
    "ni": "ni",
    "nic": "ni",
    "nicaragua": "ni",
    "niger": "ne",
    "nigeria": "ng",
    "niu": "nu",
    "niue": "nu",
    "nl": "nl",
    "nld": "nl",
    "no": "no",
    "nor": "no",
    "norfolk island": "nf",
    "north korea": "kp",
    "north macedonia": "mk",
    "northern mariana islands": "mp",
    "norway": "no",
    "np": "np",
    "npl": "np",
    "nr": "nr",
    "nru": "nr",
    "nu": "nu",
    "nz": "nz",
    "nzl": "nz",
    "om": "om",
    "oman": "om",
    "omn": "om",
    "pa": "pa",
    "pak": "pk",
    "pakistan": "pk",
    "palau": "pw",
    "palestine": "ps",
    "pan": "pa",
    "panama": "pa",
    "papua new guinea": "pg",
    "paraguay": "py",
    "pcn": "pn",
    "pe": "pe",
    "per": "pe",
    "peru": "pe",
    "pf": "pf",
    "pg": "pg",
    "ph": "ph",
    "philippines": "ph",
    "phl": "ph",
    "pitcairn": "pn",
    "pk": "pk",
    "pl": "pl",
    "plw": "pw",
    "pm": "pm",
    "pn": "pn",
    "png": "pg",
    "pol": "pl",
    "poland": "pl",
    "portugal": "pt",
    "pr": "pr",
    "pri": "pr",
    "prk": "kp",
    "prt": "pt",
    "pry": "py",
    "ps": "ps",
    "pse": "ps",
    "pt": "pt",
    "puerto rico": "pr",
    "pw": "pw",
    "py": "py",
    "pyf": "pf",
    "qa": "qa",
    "qat": "qa",
    "qatar": "qa",
    "re": "re",
    "reu": "re",
    "reunion": "re",
    "ro": "ro",
    "romania": "ro",
    "rou": "ro",
    "rs": "rs",
    "ru": "ru",
    "rus": "ru",
    "russian federation": "ru",
    "rw": "rw",
    "rwa": "rw",
    "rwanda": "rw",
    "sa": "sa",
    "saint barthelemy": "bl",
    "saint helena": "sh",
    "saint kitts and nevis": "kn",
    "saint lucia": "lc",
    "saint martin french part": "mf",
    "saint pierre and miquelon": "pm",
    "saint vincent and the grenadines": "vc",
    "samoa": "ws",
    "san marino": "sm",
    "sao tome and principe": "st",
    "sau": "sa",
    "saudi arabia": "sa",
    "sb": "sb",
    "sc": "sc",
    "sd": "sd",
    "sdn": "sd",
    "se": "se",
    "sen": "sn",
    "senegal": "sn",
    "serbia": "rs",
    "seychelles": "sc",
    "sg": "sg",
    "sgp": "sg",
    "sgs": "gs",
    "sh": "sh",
    "shn": "sh",
    "si": "si",
    "sierra leone": "sl",
    "singapore": "sg",
    "sint maarten dutch part": "sx",
    "sj": "sj",
    "sjm": "sj",
    "sk": "sk",
    "sl": "sl",
    "slb": "sb",
    "sle": "sl",
    "slovakia": "sk",
    "slovenia": "si",
    "slv": "sv",
    "sm": "sm",
    "smr": "sm",
    "sn": "sn",
    "so": "so",
    "solomon islands": "sb",
    "som": "so",
    "somalia": "so",
    "south africa": "za",
    "south georgia and the south sandwich islands": "gs",
    "south korea": "kr",
    "south sudan": "ss",
    "spain": "es",
    "spm": "pm",
    "sr": "sr",
    "srb": "rs",
    "sri lanka": "lk",
    "ss": "ss",
    "ssd": "ss",
    "st": "st",
    "stp": "st",
    "sudan": "sd",
    "sur": "sr",
    "suriname": "sr",
    "sv": "sv",
    "svalbard and jan mayen": "sj",
    "svk": "sk",
    "svn": "si",
    "swe": "se",
    "sweden": "se",
    "switzerland": "ch",
    "swz": "sz",
    "sx": "sx",
    "sxm": "sx",
    "sy": "sy",
    "syc": "sc",
    "syr": "sy",
    "syrian arab republic": "sy",
    "sz": "sz",
    "taiwan": "tw",
    "tajikistan": "tj",
    "tanzania": "tz",
    "tc": "tc",
    "tca": "tc",
    "tcd": "td",
    "td": "td",
    "tf": "tf",
    "tg": "tg",
    "tgo": "tg",
    "th": "th",
    "tha": "th",
    "thailand": "th",
    "timorleste": "tl",
    "tj": "tj",
    "tjk": "tj",
    "tk": "tk",
    "tkl": "tk",
    "tkm": "tm",
    "tl": "tl",
    "tls": "tl",
    "tm": "tm",
    "tn": "tn",
    "to": "to",
    "togo": "tg",
    "tokelau": "tk",
    "ton": "to",
    "tonga": "to",
    "tr": "tr",
    "trinidad and tobago": "tt",
    "tt": "tt",
    "tto": "tt",
    "tun": "tn",
    "tunisia": "tn",
    "tur": "tr",
    "turkiye": "tr",
    "turkmenistan": "tm",
    "turks and caicos islands": "tc",
    "tuv": "tv",
    "tuvalu": "tv",
    "tv": "tv",
    "tw": "tw",
    "twn": "tw",
    "tz": "tz",
    "tza": "tz",
    "ua": "ua",
    "ug": "ug",
    "uga": "ug",
    "uganda": "ug",
    "ukr": "ua",
    "ukraine": "ua",
    "um": "um",
    "umi": "um",
    "united arab emirates": "ae",
    "united kingdom of great britain and northern ireland": "gb",
    "united states minor outlying islands": "um",
    "united states of america": "us",
    "uruguay": "uy",
    "ury": "uy",
    "us": "us",
    "usa": "us",
    "uy": "uy",
    "uz": "uz",
    "uzb": "uz",
    "uzbekistan": "uz",
    "va": "va",
    "vanuatu": "vu",
    "vat": "va",
    "vc": "vc",
    "vct": "vc",
    "ve": "ve",
    "ven": "ve",
    "venezuela": "ve",
    "vg": "vg",
    "vgb": "vg",
    "vi": "vi",
    "viet nam": "vn",
    "vir": "vi",
    "virgin islands british": "vg",
    "virgin islands us": "vi",
    "vn": "vn",
    "vnm": "vn",
    "vu": "vu",
    "vut": "vu",
    "wallis and futuna": "wf",
    "western sahara": "eh",
    "wf": "wf",
    "wlf": "wf",
    "ws": "ws",
    "wsm": "ws",
    "ye": "ye",
    "yem": "ye",
    "yemen": "ye",
    "yt": "yt",
    "za": "za",
    "zaf": "za",
    "zambia": "zm",
    "zimbabwe": "zw",
    "zm": "zm",
    "zmb": "zm",
    "zw": "zw",
    "zwe": "zw",
}


def get_template_path():
    """Get the template directory path (uses configured central store location)."""
    base_path = get_central_store_base_path()  # Use configured path, not hardcoded
    template_path = os.path.join(base_path, "templates")
    os.makedirs(template_path, exist_ok=True)
    return template_path

def get_default_template():
    """Get the default template content"""
    return "#folderName#\n#allImages#"


_POST_TITLE_DIRECTIVE = "#POSTTITLE:"


def parse_template_file(content: str) -> tuple[str, str]:
    """Split an optional post-title directive off the top of a template file.

    The directive must be the very first line, at column 0, in the form:
        #POSTTITLE: <title template>
    Leading whitespace disqualifies the line so indented body content that
    happens to start with the literal text isn't mistaken for a directive.
    Returns (post_title, body). If no directive is present, post_title is "".
    """
    if not content:
        return "", content or ""
    first_line, _, rest = content.partition('\n')
    if first_line.startswith(_POST_TITLE_DIRECTIVE):
        post_title = first_line[len(_POST_TITLE_DIRECTIVE):].strip()
        return post_title, rest
    return "", content


def serialize_template_file(post_title: str, body: str) -> str:
    """Inverse of parse_template_file — prepends the directive when non-empty."""
    post_title = post_title.strip()
    if post_title:
        return f"{_POST_TITLE_DIRECTIVE} {post_title}\n{body}"
    return body


def load_templates():
    """Load all available templates from the template directory"""
    template_path = get_template_path()
    templates = {}

    # Add default template
    templates["default"] = get_default_template()

    # Add Extended Example template
    templates["Extended Example"] = """#folderName#
[hr][/hr]
[center][size=4][b][color=#11c153]#folderName#[/color][/b][/size]

[size=3][b][color="#888"]#pictureCount# IMAGES • #extension# • #width#x#height# • #folderSize# [/color] [/b][/font][/size]
[/center][hr][/hr]#allImages#
[if galleryLink][b]Gallery link[/b]: #galleryLink#[else][i][size=1]Sorry, no gallery link available.[/size][/i][/if]
ext1: [if ext1]#ext1#[else]no ext1 value set[/if]
ext2: [if ext2]#ext2#[else]no ext2 value set[/if]
ext3: [if ext3]#ext3#[else]no ext3 value set[/if]
ext4: [if ext4]#ext4#[else]no ext4 value set[/if]
custom1: [if custom1]#custom1#[else]no custom1 value set[/if]
custom2: [if custom2]#custom2#[else]no custom2 value set[/if]
custom3: [if custom3]#custom3#[else]no custom3 value set[/if]
custom4: [if custom4]#custom4#[else]no custom4 value set[/if]
[if hostLinks][b]Download links:[/b]
#hostLinks#[/if]"""

    # Add Video template
    templates["Video"] = """[b]#folderName#[/b]

#screenshotSheet#

[b]Video Info[/b]
File: #filename# (#filesize#)
Duration: #duration# | Resolution: #resolution# | FPS: #fps#
Video: #videoCodec#[if audioCodec] | Audio: #audioCodec#[/if]
[if audioTracks]
[b]Audio Tracks[/b]
#audioTracks#[/if]
[if downloadLinks]
[b]Download[/b]
#downloadLinks#[/if][if hostLinks]
#hostLinks#[/if]"""

    # Load custom templates
    if os.path.exists(template_path):
        for filename in os.listdir(template_path):
            template_name = filename
            if template_name.startswith(".template"):
                template_name = template_name[10:]  # Remove ".template " prefix
            # Remove .txt extension if present
            if template_name.endswith('.template.txt'):
                template_name = template_name[:-13]
            if template_name.endswith('.txt'):
                template_name = template_name[:-4]
            if template_name:  # Skip empty names
                template_file = os.path.join(template_path, filename)
                try:
                    with open(template_file, 'r', encoding='utf-8') as f:
                        raw = f.read()
                    # Strip the optional #POSTTITLE: directive so template
                    # body consumers (editor, BBCode generator) don't see it.
                    _, body = parse_template_file(raw)
                    templates[template_name] = body
                except Exception as e:
                    log(f"Could not load template '{template_name}': {e}", level="error", category="template")

    return templates


def load_post_titles() -> dict:
    """Load the post-title directive from each custom template file.

    Returns {template_name: post_title_template}. Built-in templates aren't
    included — they have no post-title directive on disk.
    """
    template_path = get_template_path()
    titles: dict = {}
    if not os.path.isdir(template_path):
        return titles
    for filename in os.listdir(template_path):
        template_name = filename
        if template_name.startswith(".template"):
            template_name = template_name[10:]
        if template_name.endswith('.template.txt'):
            template_name = template_name[:-13]
        if template_name.endswith('.txt'):
            template_name = template_name[:-4]
        if not template_name:
            continue
        try:
            with open(os.path.join(template_path, filename), 'r', encoding='utf-8') as f:
                post_title, _ = parse_template_file(f.read())
            if post_title:
                titles[template_name] = post_title
        except Exception as e:
            log(f"Could not load post-title for '{template_name}': {e}", level="error", category="template")
    return titles

def _camel_to_snake(name):
    """Convert camelCase placeholder name to snake_case data key.

    Template placeholders use camelCase (e.g. downloadLinks, videoDetails)
    while data dicts use snake_case (e.g. download_links, video_details).
    """
    import re
    # Insert underscore before uppercase letters and lowercase the result
    return re.sub(r'(?<=[a-z0-9])([A-Z])', r'_\1', name).lower()


def process_conditionals(template_content, data):
    """Process conditional logic in templates before placeholder replacement.

    Supports two syntax forms:
    1. [if placeholder]content[/if] - shows content if placeholder value is non-empty
    2. [if placeholder=value]content[else]alternative[/if] - shows content if placeholder equals value

    Features:
    - Multiple inline conditionals on the same line
    - Nested conditionals (processed inside-out)
    - Empty lines from removed conditionals are stripped
    - Placeholder names are matched as camelCase (template) or snake_case (data)
    """
    import re

    # Process conditionals iteratively until no more found
    max_iterations = 50  # Prevent infinite loops
    iteration = 0

    while iteration < max_iterations:
        # Look for innermost conditional pattern (no nested [if] tags inside)
        # This regex matches [if...] followed by content WITHOUT another [if, then [/if]
        if_pattern = r'\[if\s+(\w+)(=([^\]]+))?\]((?:(?!\[if).)*?)\[/if\]'
        match = re.search(if_pattern, template_content, re.DOTALL)

        if not match:
            # No more conditionals found
            break

        placeholder_name = match.group(1)
        expected_value = match.group(3)  # None if no = comparison
        conditional_block = match.group(4)  # Content between [if] and [/if]

        # Get the actual value from data -- try camelCase name first,
        # then fall back to snake_case conversion so that [if downloadLinks]
        # finds data['download_links'].
        actual_value = data.get(placeholder_name, '')
        if not actual_value:
            snake_key = _camel_to_snake(placeholder_name)
            if snake_key != placeholder_name:
                actual_value = data.get(snake_key, '')

        # Check for [else] clause (only at top level, not nested)
        else_pattern = r'^(.*?)\[else\](.*?)$'
        else_match = re.match(else_pattern, conditional_block, re.DOTALL)

        if else_match:
            true_content = else_match.group(1)
            false_content = else_match.group(2)
        else:
            true_content = conditional_block
            false_content = ''

        # Determine condition
        if expected_value is not None:
            # Equality check: [if placeholder=value]
            condition_met = (str(actual_value).strip() == expected_value.strip())
        else:
            # Existence check: [if placeholder]
            condition_met = bool(str(actual_value).strip())

        # Select content based on condition
        selected_content = true_content if condition_met else false_content

        # Replace the entire conditional block with selected content
        template_content = template_content[:match.start()] + selected_content + template_content[match.end():]

        iteration += 1

    # Clean up empty lines
    lines = template_content.split('\n')
    cleaned_lines = [line for line in lines if line.strip() or line == '']  # Keep intentional blank lines

    # Remove consecutive empty lines and leading/trailing empty lines
    result_lines = []
    prev_empty = False
    for line in cleaned_lines:
        is_empty = not line.strip()
        if is_empty:
            if not prev_empty and result_lines:  # Keep one empty line
                result_lines.append(line)
            prev_empty = True
        else:
            result_lines.append(line)
            prev_empty = False

    # Remove trailing empty lines
    while result_lines and not result_lines[-1].strip():
        result_lines.pop()

    return '\n'.join(result_lines)

def apply_template(template_content, data):
    """Apply a template with data replacement"""
    # Process conditional logic first (before placeholder replacement)
    result = process_conditionals(template_content, data)

    # Replace placeholders with actual data
    # hostLinks and allImages are expanded FIRST so that any main placeholders
    # embedded inside them (e.g. #folderSize# in a filehost bbcode_format)
    # get resolved in the second pass.
    composite_replacements = {
        '#hostLinks#': data.get('host_links', ''),
        '#allImages#': data.get('all_images', ''),
        '#cover#': data.get('cover', ''),
        '#videoDetails#': data.get('video_details', ''),
        '#screenshotSheet#': data.get('screenshot_sheet', ''),
        '#downloadLinks#': data.get('download_links', ''),
    }
    for placeholder, value in composite_replacements.items():
        result = result.replace(placeholder, str(value or ''))

    # #galleryName# falls back to #folderName# binding when not explicitly set,
    # so existing templates keep working and #galleryName# means the same thing
    # in practice until an auto-posting workflow populates gallery_title distinctly.
    gallery_name_value = data.get('gallery_name') or data.get('folder_name') or ''
    gallery_title_value = data.get('gallery_title') or gallery_name_value

    replacements = {
        '#folderName#': str(data.get('folder_name') or ''),
        '#galleryName#': str(gallery_name_value),
        '#galleryTitle#': str(gallery_title_value),
        '#width#': str(data.get('width', 0)),
        '#height#': str(data.get('height', 0)),
        '#longest#': str(data.get('longest', 0)),
        '#extension#': str(data.get('extension') or ''),
        '#pictureCount#': str(data.get('picture_count', 0)),
        '#folderSize#': str(data.get('folder_size') or ''),
        '#galleryLink#': str(data.get('gallery_link') or ''),
        '#custom1#': str(data.get('custom1') or ''),
        '#custom2#': str(data.get('custom2') or ''),
        '#custom3#': str(data.get('custom3') or ''),
        '#custom4#': str(data.get('custom4') or ''),
        '#ext1#': str(data.get('ext1') or ''),
        '#ext2#': str(data.get('ext2') or ''),
        '#ext3#': str(data.get('ext3') or ''),
        '#ext4#': str(data.get('ext4') or ''),
        '#filename#': str(data.get('filename', '')),
        '#duration#': str(data.get('duration', '')),
        '#resolution#': str(data.get('resolution', '')),
        '#fps#': str(data.get('fps', '')),
        '#bitrate#': str(data.get('bitrate', '')),
        '#videoCodec#': str(data.get('video_codec', '')),
        '#audioCodec#': str(data.get('audio_codec', '')),
        '#audioTracks#': str(data.get('audio_tracks', '')),
        '#filesize#': str(data.get('filesize', '')),
    }
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, str(value or ''))

    return result

def generate_bbcode_from_template(template_name, data):
    """Generate bbcode content using a specific template"""
    templates = load_templates()

    if template_name not in templates:
        log(f"Template '{template_name}' not found, using default", level="warning", category="template")
        template_name = "default"

    template_content = templates[template_name]
    return apply_template(template_content, data)


def extract_post_title(title_template: Optional[str], body_template: Optional[str], fallback_title: str = "") -> str:
    """Extract post title from template's #POSTTITLE: directive, with fallback.

    Args:
        title_template: Explicit title template name (preferred)
        body_template: Body template name (fallback for title directive)
        fallback_title: Fallback title if no directive found (e.g., gallery name)

    Returns:
        Post title string, or fallback_title if template has no directive.
    """
    lookup_key = title_template or body_template
    if not lookup_key:
        return fallback_title

    try:
        templates = load_templates() or {}
        if lookup_key in templates:
            template_content = templates[lookup_key]
            post_title_directive, _ = parse_template_file(template_content)
            if post_title_directive:
                return post_title_directive
    except Exception:
        pass

    return fallback_title


def save_gallery_artifacts(
    folder_path: str,
    results: dict,
    template_name: str = "default",
    store_in_uploaded: Optional[bool] = None,
    store_in_central: Optional[bool] = None,
    custom_fields: Optional[dict] = None,
    cover_bbcode: str = "",
) -> dict:
    """Save BBCode and JSON artifacts for a completed gallery.

    Parameters:
    - folder_path: path to the source image folder
    - results: the results dict returned by upload_folder (must contain keys used below)
    - template_name: which template to use for full bbcode generation
    - store_in_uploaded/store_in_central: overrides for storage locations. When None, read defaults
    - custom_fields: optional dict with custom1-4 and ext1-4 values

    Returns: dict with paths written: { 'uploaded': {'bbcode': str, 'json': str}, 'central': {...}}
    """
    from src.storage.gallery_management import build_gallery_filenames

    # Determine storage preferences
    defaults = load_user_defaults()
    if store_in_uploaded is None:
        store_in_uploaded = defaults.get('store_in_uploaded', True)
    if store_in_central is None:
        store_in_central = defaults.get('store_in_central', True)

    gallery_id = results.get('gallery_id', '') or os.path.splitext(os.path.basename(folder_path))[0]
    gallery_name = results.get('gallery_name') or os.path.basename(folder_path)
    if not gallery_name:
        return {}

    # Ensure .uploaded exists if needed (for video files, use parent directory)
    base_dir = folder_path if os.path.isdir(folder_path) else os.path.dirname(folder_path)
    uploaded_subdir = os.path.join(base_dir, ".uploaded")
    if store_in_uploaded:
        os.makedirs(uploaded_subdir, exist_ok=True)

    # Build filenames
    safe_gallery_name, json_filename, bbcode_filename = build_gallery_filenames(gallery_name, gallery_id)

    # Prepare template data from results for full bbcode
    total_size = results.get('total_size', 0)
    successful_images = results.get('successful_count', len(results.get('images', [])))
    avg_width = int(results.get('avg_width', 0) or 0)
    avg_height = int(results.get('avg_height', 0) or 0)

    # Fallback: Calculate from files if dimensions are missing
    if (avg_width == 0 or avg_height == 0) and os.path.isdir(folder_path):
        from src.utils.sampling_utils import calculate_folder_dimensions
        calc = calculate_folder_dimensions(folder_path)
        if calc:
            avg_width = int(calc.get('avg_width', 0))
            avg_height = int(calc.get('avg_height', 0))

    extension = "JPG"
    try:
        # Best-effort derive the most common extension from images if present
        exts = []
        for img in results.get('images', []):
            orig = img.get('original_filename') or ''
            if orig:
                _, ext = os.path.splitext(orig)
                if ext:
                    exts.append(ext.upper().lstrip('.'))
        if exts:
            extension = max(set(exts), key=exts.count)
    except Exception:
        pass

    # All-images bbcode (space-separated)
    # Generate per-image BBCode from image_url + thumb_url if not already present
    bbcode_parts = []
    for img in results.get('images', []):
        bb = img.get('bbcode')
        if not bb:
            iu = img.get('image_url', '')
            tu = img.get('thumb_url', '')
            if iu and tu:
                bb = f"[url={iu}][img]{tu}[/img][/url]"
            elif iu:
                bb = f"[url={iu}]{iu}[/url]"
        if bb:
            bbcode_parts.append(bb)
    all_images_bbcode = "  ".join(bbcode_parts)

    # Get file host data from database
    queue_store = None
    try:
        from src.storage.database import QueueStore
        queue_store = QueueStore()
    except Exception as e:
        log(f"Failed to open queue store for artifacts: {e}", level="warning", category="artifact")

    # Get file host download links for BBCode template
    host_links = ''
    if queue_store:
        try:
            from src.utils.template_utils import get_file_host_links_for_template
            host_links = get_file_host_links_for_template(queue_store, folder_path)
        except Exception as e:
            log(f"Failed to get file host links: {e}", level="warning", category="template")

    # Build file_hosts array for JSON artifact
    file_hosts_data = []
    if queue_store:
        try:
            fh_uploads = queue_store.get_file_host_uploads(folder_path)
            for u in fh_uploads:
                if u['status'] == 'completed' and u.get('download_url'):
                    file_hosts_data.append({
                        'host': u['host_name'],
                        'download_url': u['download_url'],
                        'file_id': u.get('file_id', ''),
                        'file_name': u.get('file_name', ''),
                        'md5_hash': u.get('md5_hash', ''),
                        'file_size': u.get('file_size', 0),
                        'deduped': u.get('deduped', False),
                        'part': u.get('part_number', 0) + 1,
                    })
        except Exception as e:
            log(f"Failed to build file_hosts artifact data: {e}", level="warning", category="artifact")

    # Get cover info from results if available (cover_result is a list of per-cover dicts)
    cover_results = results.get('cover_result', []) or []
    c_url = next((r.get('image_url', '') for r in cover_results if r.get('status') == 'success'), '')
    c_thumb = next((r.get('thumb_url', '') for r in cover_results if r.get('status') == 'success'), '')
    if not cover_bbcode:
        cover_bbcode = "\n".join(
            r['bbcode'] for r in cover_results
            if r.get('status') == 'success' and r.get('bbcode')
        )

    # Resolve the post-title template for this template (if any) before building
    # template_data, so #galleryTitle# can be populated for the body pass.
    post_title_templates = load_post_titles()
    post_title_tpl = post_title_templates.get(template_name, '')

    template_data = {
        'folder_name': gallery_name,
        'gallery_name': gallery_name,
        'width': avg_width,
        'height': avg_height,
        'longest': max(avg_width, avg_height),
        'extension': extension,
        'picture_count': successful_images,
        'folder_size': f"{total_size / (1024*1024):.1f} MB",
        'gallery_link': results.get('gallery_url', ''),
        'all_images': all_images_bbcode,
        'host_links': host_links,
        'cover': cover_bbcode,
        'cover_url': c_url,
        'cover_thumb_url': c_thumb,
        'custom1': (custom_fields or {}).get('custom1', ''),
        'custom2': (custom_fields or {}).get('custom2', ''),
        'custom3': (custom_fields or {}).get('custom3', ''),
        'custom4': (custom_fields or {}).get('custom4', ''),
        'ext1': (custom_fields or {}).get('ext1', ''),
        'ext2': (custom_fields or {}).get('ext2', ''),
        'ext3': (custom_fields or {}).get('ext3', ''),
        'ext4': (custom_fields or {}).get('ext4', '')
    }

    # Merge video metadata fields when present
    video_meta = results.get('video_metadata')
    if video_meta:
        video_streams = video_meta.get('video_streams', [])
        audio_streams = video_meta.get('audio_streams', [])

        # Build audio tracks summary
        track_lines = []
        for track in audio_streams:
            fmt = track.get('format', 'Unknown')
            ch = track.get('channels', '?')
            rate = track.get('sampling_rate', '?')
            br = track.get('bit_rate', '?')
            track_lines.append(f"{fmt}: {ch}-CH {rate}Hz {br} bps")

        # Format duration
        dur_secs = max(0, int(video_meta.get('duration') or 0))
        h, m, s = dur_secs // 3600, (dur_secs % 3600) // 60, dur_secs % 60
        duration_str = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"

        # Format filesize
        raw_size = video_meta.get('filesize') or 0
        if not raw_size:
            filesize_str = "Unknown"
        elif raw_size >= 1024 * 1024 * 1024:
            filesize_str = f"{raw_size / (1024**3):.2f} GB"
        elif raw_size >= 1024 * 1024:
            filesize_str = f"{raw_size / (1024**2):.1f} MB"
        else:
            filesize_str = f"{raw_size / 1024:.0f} KB"

        v_codec = video_streams[0].get('format', '') if video_streams else ''
        a_codec = audio_streams[0].get('format', '') if audio_streams else ''
        resolution = f"{video_meta.get('width', '')}x{video_meta.get('height', '')}"

        # Screenshot sheet BBCode = the uploaded sheet image's BBCode
        screenshot_bbcode = ''
        images = results.get('images', [])
        if images and results.get('media_type') == 'video':
            screenshot_bbcode = images[0].get('bbcode', '')

        # Build video_details from user template or fallback
        video_details_tpl = results.get('video_details_template', '')
        if video_details_tpl:
            video_details_text = video_details_tpl
            video_details_text = video_details_text.replace('#resolution#', resolution)
            video_details_text = video_details_text.replace('#duration#', duration_str)
            video_details_text = video_details_text.replace('#fps#', str(video_meta.get('fps', '')))
            video_details_text = video_details_text.replace('#bitrate#', str(video_meta.get('bitrate', '')))
            video_details_text = video_details_text.replace('#videoCodec#', v_codec)
            video_details_text = video_details_text.replace('#audioCodec#', a_codec)
            video_details_text = video_details_text.replace('#audioTracks#', '\n'.join(track_lines))
            video_details_text = video_details_text.replace('#filesize#', filesize_str)
            video_details_text = video_details_text.replace('#filename#', os.path.basename(folder_path))
        else:
            video_details_text = f"{resolution} | {duration_str} | {v_codec}" + (f" / {a_codec}" if a_codec else '')

        template_data.update({
            'filename': os.path.basename(folder_path),
            'duration': duration_str,
            'resolution': resolution,
            'fps': str(video_meta.get('fps', '')),
            'bitrate': str(video_meta.get('bitrate', '')),
            'video_codec': v_codec,
            'audio_codec': a_codec,
            'audio_tracks': '\n'.join(track_lines),
            'filesize': filesize_str,
            'screenshot_sheet': screenshot_bbcode,
            'video_details': video_details_text,
            'download_links': results.get('download_links', ''),
        })

    # Resolve post title using the same placeholder engine. Pre-populate
    # gallery_title to the gallery_name fallback so recursive #galleryTitle#
    # references in the title template stay bounded.
    if post_title_tpl:
        title_data = {**template_data, 'gallery_title': gallery_name}
        resolved_post_title = apply_template(post_title_tpl, title_data).strip()
    else:
        resolved_post_title = gallery_name
    template_data['gallery_title'] = resolved_post_title

    bbcode_content = generate_bbcode_from_template(template_name, template_data)

    # Compose JSON payload (align with CLI structure)
    json_payload = {
        'meta': {
            'gallery_name': gallery_name,
            'gallery_title': resolved_post_title,
            'gallery_id': gallery_id,
            'gallery_url': results.get('gallery_url', ''),
            'status': 'completed',
            'started_at': results.get('started_at') or None,
            'finished_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'uploader_version': __version__,
            'media_type': results.get('media_type', 'image'),
        },
        'settings': {
            'thumbnail_size': results.get('thumbnail_size'),
            'thumbnail_format': results.get('thumbnail_format'),
            'template_name': template_name,
            'parallel_batch_size': results.get('parallel_batch_size'),
            'video_details_template': results.get('video_details_template', ''),
        },
        'video_metadata': results.get('video_metadata') or {},
        'stats': {
            'total_images': results.get('total_images') or (successful_images + results.get('failed_count', 0)),
            'successful_count': successful_images,
            'failed_count': results.get('failed_count', 0),
            'upload_time': results.get('upload_time', 0),
            'total_size': total_size,
            'uploaded_size': results.get('uploaded_size', 0),
            'avg_width': results.get('avg_width', 0),
            'avg_height': results.get('avg_height', 0),
            'max_width': results.get('max_width', 0),
            'max_height': results.get('max_height', 0),
            'min_width': results.get('min_width', 0),
            'min_height': results.get('min_height', 0),
            'transfer_speed_mb_s': (results.get('transfer_speed', 0) / (1024*1024)) if results.get('transfer_speed', 0) else 0,
        },
        'images': results.get('images', []),
        'cover_result': cover_results,
        'file_hosts': file_hosts_data,
        'failures': [
            {
                'filename': fname,
                'failed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'reason': reason,
            }
            for fname, reason in results.get('failed_details', [])
        ],
        'bbcode_full': bbcode_content,
    }

    written_paths = {}
    # Save BBCode and JSON to .uploaded
    if store_in_uploaded:
        with open(os.path.join(uploaded_subdir, bbcode_filename), 'w', encoding='utf-8') as f:
            f.write(bbcode_content)
        with open(os.path.join(uploaded_subdir, json_filename), 'w', encoding='utf-8') as jf:
            json.dump(json_payload, jf, ensure_ascii=False, indent=2)
        written_paths.setdefault('uploaded', {})['bbcode'] = os.path.join(uploaded_subdir, bbcode_filename)
        written_paths.setdefault('uploaded', {})['json'] = os.path.join(uploaded_subdir, json_filename)

    # Save to central location as well
    if store_in_central:
        central_path = get_central_storage_path()
        os.makedirs(central_path, exist_ok=True)
        with open(os.path.join(central_path, bbcode_filename), 'w', encoding='utf-8') as f:
            f.write(bbcode_content)
        with open(os.path.join(central_path, json_filename), 'w', encoding='utf-8') as jf:
            json.dump(json_payload, jf, ensure_ascii=False, indent=2)
        written_paths.setdefault('central', {})['bbcode'] = os.path.join(central_path, bbcode_filename)
        written_paths.setdefault('central', {})['json'] = os.path.join(central_path, json_filename)

    return written_paths

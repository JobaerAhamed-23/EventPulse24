"""The world-city catalog: which places may be picked. Stdlib only.

**This is not a list of cities we have events for.** `domain.cities` answers "which written
forms name the same place" for text a source wrote; this module answers the question the
picker asks — "which places may a reader choose?" — and it answers it the same way whether
the catalog has ingested one event in that city or none. That is the whole point: a reader
in Chittagong picks Chittagong, and provisioning goes and finds the events afterwards.

**`name` is the value that gets stored.** `DigestPreference.city` holds "Portland, OR", a
string `split_region`, `city_identity` and `venue_fingerprint` all already understand. The
disambiguating form a human reads — "Portland, Oregon" — is `label`, derived for the
dropdown and never written anywhere. So a preference carries no country column and never
needed one.

**Every row declares what `domain.cities.split_region()` will make of its name**, and a
test asserts the two agree over the whole dataset. `split_region` reads a trailing
alphabetic run of <= 3 characters as a region qualifier, so "Portland, OR" keys as
`("portland", "or")` and "Chittagong" as `("chittagong", "")`. Declaring `region` rather
than re-deriving it downstream turns a bad row into a failing test at commit time instead
of a wrong city page in production.

**`tz` is the load-bearing column.** It is what lets a brand-new city resolve a date-only
event time with no registered venue to borrow a zone from, and unlike a population count
or a venue list it is a fact that does not go stale.

**Deliberately curated, deliberately not exhaustive.** Roughly a hundred and sixty rows,
one or two cities per country, each one read by a person and each one held to the
whole-dataset invariants below. A generated list of thousands would carry wrong zones and
region qualifiers that fight `split_region`, and the invariant tests would become
something the data was tuned to pass rather than a check on data that was verified.
Growing this is one line per city, which is the reason it is a checked-in list and not a
table someone edits through a form.

**Not routed through `CITY_ALIAS_GROUPS`.** That table says which spellings name the same
place; letting an alias resolve to a catalog row would hand the reader a `tz` and a country
that were never verified for the spelling they typed.
"""

from dataclasses import dataclass

from domain.cities import CityIdentity, city_identity, split_region


@dataclass(frozen=True)
class CityChoice:
    """One pickable place: what to store, what to show, and where it is in time.

    `region` and `region_name` are two columns rather than one derived from the other
    because they answer to different masters: `region` must be exactly what `split_region`
    emits, because it is part of `CityIdentity`; `region_name` is what a human reads.
    Deriving either from the other means carrying a table of every state and province
    inside `domain`, which is more surface than one short column. The same reasoning holds
    for `country_code`, `country_name` and `country_slug`.
    """

    name: str
    """The STORED value, exactly as it will sit on a preference: "Portland, OR", "Dhaka"."""

    country_code: str
    """ISO 3166-1 alpha-2, uppercase. Part of the identity."""

    country_name: str
    """Display form, for the label only: "United States", "Bangladesh"."""

    country_slug: str
    """URL templating only ("united-states"). **Not** an identity field."""

    region: str
    """What `split_region(name)` yields — lowercase, <= 3 chars, "" when there is none."""

    region_name: str
    """Display form of `region`, for the label only: "Oregon", "" when there is none."""

    tz: str
    """IANA zone. Canonical per `domain.timezones.canonical_zone`."""

    @property
    def label(self) -> str:
        """What the dropdown shows: "Portland, Oregon", "Chittagong, Bangladesh".

        Never stored. The qualifier in `name` is replaced by its display form, and a city
        with no qualifier is placed by its country, so two rows are always told apart by
        what a reader can see — and a test asserts no two rows share a label, because the
        dropdown shows this and two identical entries ask the reader a question with no
        answer. "Atlanta, Georgia" and "Tbilisi, Georgia" differ, and both are honest.
        """
        base = self.name.rsplit(",", 1)[0].strip() if self.region else self.name
        return f"{base}, {self.region_name or self.country_name}"

    @property
    def identity(self) -> CityIdentity:
        """The `domain.cities` identity this row will resolve to, derived, never declared."""
        return city_identity(self.name, self.country_code)


def _country(
    code: str, country_name: str, slug: str, tz: str, *rows: tuple[str, ...] | str
) -> tuple[CityChoice, ...]:
    """Rows for one country, so the country's four columns are written once, not per city.

    A row is a bare name when the country has one zone and the name needs no qualifier,
    `(name, region, region_name)` when it needs a qualifier, or `(name, region,
    region_name, tz)` when the city sits in a zone other than its country's first.
    """
    built: list[CityChoice] = []
    for row in rows:
        name, region, region_name, zone = (
            (*row, tz)[:4] if isinstance(row, tuple) else (row, "", "", tz)
        )
        built.append(
            CityChoice(
                name=name,
                country_code=code,
                country_name=country_name,
                country_slug=slug,
                region=region,
                region_name=region_name,
                tz=zone,
            )
        )
    return tuple(built)


#: Every pickable city. One or two per country, read by a person, held to the invariants
#: in `tests/domain/test_city_catalog.py` over the whole tuple rather than a sample.
WORLD_CITIES: tuple[CityChoice, ...] = (
    # --- South and Central Asia ----------------------------------------------------------
    *_country("BD", "Bangladesh", "bangladesh", "Asia/Dhaka", "Dhaka", "Chittagong"),
    *_country("IN", "India", "india", "Asia/Kolkata", "Mumbai", "Delhi", "Bengaluru", "Kolkata"),
    *_country("PK", "Pakistan", "pakistan", "Asia/Karachi", "Karachi"),
    *_country("LK", "Sri Lanka", "sri-lanka", "Asia/Colombo", "Colombo"),
    *_country("NP", "Nepal", "nepal", "Asia/Kathmandu", "Kathmandu"),
    *_country("KZ", "Kazakhstan", "kazakhstan", "Asia/Almaty", "Almaty"),
    *_country("UZ", "Uzbekistan", "uzbekistan", "Asia/Tashkent", "Tashkent"),
    # --- East and Southeast Asia ---------------------------------------------------------
    *_country("JP", "Japan", "japan", "Asia/Tokyo", "Tokyo", "Osaka"),
    *_country("KR", "South Korea", "south-korea", "Asia/Seoul", "Seoul", "Busan"),
    *_country("CN", "China", "china", "Asia/Shanghai", "Shanghai", "Beijing"),
    *_country("HK", "Hong Kong", "hong-kong", "Asia/Hong_Kong", "Hong Kong"),
    *_country("TW", "Taiwan", "taiwan", "Asia/Taipei", "Taipei"),
    *_country("SG", "Singapore", "singapore", "Asia/Singapore", "Singapore"),
    *_country("MY", "Malaysia", "malaysia", "Asia/Kuala_Lumpur", "Kuala Lumpur"),
    *_country("TH", "Thailand", "thailand", "Asia/Bangkok", "Bangkok"),
    *_country("VN", "Vietnam", "vietnam", "Asia/Ho_Chi_Minh", "Ho Chi Minh City", "Hanoi"),
    *_country("ID", "Indonesia", "indonesia", "Asia/Jakarta", "Jakarta"),
    *_country("PH", "Philippines", "philippines", "Asia/Manila", "Manila", "Cebu City"),
    *_country("KH", "Cambodia", "cambodia", "Asia/Phnom_Penh", "Phnom Penh"),
    # --- Western Asia --------------------------------------------------------------------
    *_country(
        "AE", "United Arab Emirates", "united-arab-emirates", "Asia/Dubai", "Dubai", "Abu Dhabi"
    ),
    *_country("SA", "Saudi Arabia", "saudi-arabia", "Asia/Riyadh", "Riyadh", "Jeddah"),
    *_country("QA", "Qatar", "qatar", "Asia/Qatar", "Doha"),
    *_country("KW", "Kuwait", "kuwait", "Asia/Kuwait", "Kuwait City"),
    *_country("JO", "Jordan", "jordan", "Asia/Amman", "Amman"),
    *_country("LB", "Lebanon", "lebanon", "Asia/Beirut", "Beirut"),
    *_country("IL", "Israel", "israel", "Asia/Jerusalem", "Tel Aviv", "Jerusalem"),
    *_country("IR", "Iran", "iran", "Asia/Tehran", "Tehran"),
    *_country("GE", "Georgia", "georgia", "Asia/Tbilisi", "Tbilisi"),
    *_country("AM", "Armenia", "armenia", "Asia/Yerevan", "Yerevan"),
    *_country("AZ", "Azerbaijan", "azerbaijan", "Asia/Baku", "Baku"),
    *_country("TR", "Turkey", "turkey", "Europe/Istanbul", "Istanbul", "Ankara"),
    # --- Western Europe ------------------------------------------------------------------
    *_country(
        "GB",
        "United Kingdom",
        "united-kingdom",
        "Europe/London",
        "London",
        "Manchester",
        "Birmingham",
        "Edinburgh",
    ),
    *_country("IE", "Ireland", "ireland", "Europe/Dublin", "Dublin"),
    *_country("FR", "France", "france", "Europe/Paris", "Paris", "Lyon", "Marseille"),
    *_country("DE", "Germany", "germany", "Europe/Berlin", "Berlin", "Munich", "Hamburg"),
    *_country("NL", "Netherlands", "netherlands", "Europe/Amsterdam", "Amsterdam", "Rotterdam"),
    *_country("BE", "Belgium", "belgium", "Europe/Brussels", "Brussels"),
    *_country("LU", "Luxembourg", "luxembourg", "Europe/Luxembourg", "Luxembourg"),
    *_country("CH", "Switzerland", "switzerland", "Europe/Zurich", "Zurich", "Geneva"),
    *_country("AT", "Austria", "austria", "Europe/Vienna", "Vienna"),
    # --- Southern Europe -----------------------------------------------------------------
    *_country("ES", "Spain", "spain", "Europe/Madrid", "Madrid", "Barcelona", "Valencia"),
    *_country("PT", "Portugal", "portugal", "Europe/Lisbon", "Lisbon", "Porto"),
    *_country("IT", "Italy", "italy", "Europe/Rome", "Rome", "Milan", "Naples"),
    *_country("GR", "Greece", "greece", "Europe/Athens", "Athens", "Thessaloniki"),
    *_country("HR", "Croatia", "croatia", "Europe/Zagreb", "Zagreb"),
    *_country("SI", "Slovenia", "slovenia", "Europe/Ljubljana", "Ljubljana"),
    *_country("RS", "Serbia", "serbia", "Europe/Belgrade", "Belgrade"),
    *_country("MT", "Malta", "malta", "Europe/Malta", "Valletta"),
    # --- Central and Eastern Europe ------------------------------------------------------
    *_country("CZ", "Czechia", "czechia", "Europe/Prague", "Prague"),
    *_country("PL", "Poland", "poland", "Europe/Warsaw", "Warsaw", "Krakow"),
    *_country("HU", "Hungary", "hungary", "Europe/Budapest", "Budapest"),
    *_country("SK", "Slovakia", "slovakia", "Europe/Bratislava", "Bratislava"),
    *_country("RO", "Romania", "romania", "Europe/Bucharest", "Bucharest"),
    *_country("BG", "Bulgaria", "bulgaria", "Europe/Sofia", "Sofia"),
    *_country("UA", "Ukraine", "ukraine", "Europe/Kyiv", "Kyiv", "Lviv"),
    *_country("RU", "Russia", "russia", "Europe/Moscow", "Moscow", "Saint Petersburg"),
    # --- Northern Europe -----------------------------------------------------------------
    *_country("DK", "Denmark", "denmark", "Europe/Copenhagen", "Copenhagen"),
    *_country("SE", "Sweden", "sweden", "Europe/Stockholm", "Stockholm", "Gothenburg"),
    *_country("NO", "Norway", "norway", "Europe/Oslo", "Oslo"),
    *_country("FI", "Finland", "finland", "Europe/Helsinki", "Helsinki"),
    *_country("IS", "Iceland", "iceland", "Atlantic/Reykjavik", "Reykjavik"),
    *_country("EE", "Estonia", "estonia", "Europe/Tallinn", "Tallinn"),
    *_country("LV", "Latvia", "latvia", "Europe/Riga", "Riga"),
    *_country("LT", "Lithuania", "lithuania", "Europe/Vilnius", "Vilnius"),
    # --- Africa --------------------------------------------------------------------------
    *_country("EG", "Egypt", "egypt", "Africa/Cairo", "Cairo", "Alexandria"),
    *_country("MA", "Morocco", "morocco", "Africa/Casablanca", "Casablanca"),
    *_country("TN", "Tunisia", "tunisia", "Africa/Tunis", "Tunis"),
    *_country("DZ", "Algeria", "algeria", "Africa/Algiers", "Algiers"),
    *_country("NG", "Nigeria", "nigeria", "Africa/Lagos", "Lagos", "Abuja"),
    *_country("GH", "Ghana", "ghana", "Africa/Accra", "Accra"),
    *_country("SN", "Senegal", "senegal", "Africa/Dakar", "Dakar"),
    *_country("CI", "Ivory Coast", "ivory-coast", "Africa/Abidjan", "Abidjan"),
    *_country("KE", "Kenya", "kenya", "Africa/Nairobi", "Nairobi"),
    *_country("TZ", "Tanzania", "tanzania", "Africa/Dar_es_Salaam", "Dar es Salaam"),
    *_country("UG", "Uganda", "uganda", "Africa/Kampala", "Kampala"),
    *_country("RW", "Rwanda", "rwanda", "Africa/Kigali", "Kigali"),
    *_country("ET", "Ethiopia", "ethiopia", "Africa/Addis_Ababa", "Addis Ababa"),
    *_country(
        "ZA",
        "South Africa",
        "south-africa",
        "Africa/Johannesburg",
        "Johannesburg",
        "Cape Town",
        "Durban",
    ),
    # --- United States -------------------------------------------------------------------
    # The country the qualifier exists for. "Portland, OR" and "Portland, ME" are the
    # worked case: one key, two regions, two rows, two city pages. "Brooklyn" is carried
    # without a qualifier because that is the string already stored and already ingested —
    # changing it to "Brooklyn, NY" would make a different city of it.
    *_country(
        "US",
        "United States",
        "united-states",
        "America/New_York",
        ("New York, NY", "ny", "New York"),
        ("Brooklyn", "", ""),
        ("Philadelphia, PA", "pa", "Pennsylvania"),
        ("Boston, MA", "ma", "Massachusetts"),
        ("Atlanta, GA", "ga", "Georgia"),
        ("Miami, FL", "fl", "Florida"),
        ("Portland, ME", "me", "Maine"),
        ("Washington, DC", "dc", "District of Columbia"),
        ("Chicago, IL", "il", "Illinois", "America/Chicago"),
        ("Houston, TX", "tx", "Texas", "America/Chicago"),
        ("Austin, TX", "tx", "Texas", "America/Chicago"),
        ("Nashville, TN", "tn", "Tennessee", "America/Chicago"),
        ("New Orleans, LA", "la", "Louisiana", "America/Chicago"),
        ("Minneapolis, MN", "mn", "Minnesota", "America/Chicago"),
        ("Denver, CO", "co", "Colorado", "America/Denver"),
        ("Phoenix, AZ", "az", "Arizona", "America/Phoenix"),
        ("Los Angeles, CA", "ca", "California", "America/Los_Angeles"),
        ("San Francisco, CA", "ca", "California", "America/Los_Angeles"),
        ("Seattle, WA", "wa", "Washington", "America/Los_Angeles"),
        ("Portland, OR", "or", "Oregon", "America/Los_Angeles"),
        ("Las Vegas, NV", "nv", "Nevada", "America/Los_Angeles"),
    ),
    # --- Canada --------------------------------------------------------------------------
    *_country(
        "CA",
        "Canada",
        "canada",
        "America/Toronto",
        ("Toronto, ON", "on", "Ontario"),
        ("Montreal, QC", "qc", "Quebec"),
        ("Ottawa, ON", "on", "Ontario"),
        ("Calgary, AB", "ab", "Alberta", "America/Edmonton"),
        ("Vancouver, BC", "bc", "British Columbia", "America/Vancouver"),
    ),
    # --- Latin America and the Caribbean --------------------------------------------------
    *_country(
        "MX",
        "Mexico",
        "mexico",
        "America/Mexico_City",
        "Mexico City",
        "Guadalajara",
        ("Monterrey", "", "", "America/Monterrey"),
    ),
    *_country(
        "BR",
        "Brazil",
        "brazil",
        "America/Sao_Paulo",
        "São Paulo",
        "Rio de Janeiro",
        "Brasília",
    ),
    *_country("AR", "Argentina", "argentina", "America/Argentina/Buenos_Aires", "Buenos Aires"),
    *_country("CL", "Chile", "chile", "America/Santiago", "Santiago"),
    *_country("CO", "Colombia", "colombia", "America/Bogota", "Bogotá", "Medellín"),
    *_country("PE", "Peru", "peru", "America/Lima", "Lima"),
    *_country("UY", "Uruguay", "uruguay", "America/Montevideo", "Montevideo"),
    *_country("EC", "Ecuador", "ecuador", "America/Guayaquil", "Quito"),
    *_country("CR", "Costa Rica", "costa-rica", "America/Costa_Rica", "San José"),
    *_country("PA", "Panama", "panama", "America/Panama", "Panama City"),
    *_country("GT", "Guatemala", "guatemala", "America/Guatemala", "Guatemala City"),
    *_country(
        "DO", "Dominican Republic", "dominican-republic", "America/Santo_Domingo", "Santo Domingo"
    ),
    *_country("JM", "Jamaica", "jamaica", "America/Jamaica", "Kingston"),
    # --- Oceania -------------------------------------------------------------------------
    *_country(
        "AU",
        "Australia",
        "australia",
        "Australia/Sydney",
        ("Sydney, NSW", "nsw", "New South Wales"),
        ("Canberra, ACT", "act", "Australian Capital Territory"),
        ("Melbourne, VIC", "vic", "Victoria", "Australia/Melbourne"),
        ("Brisbane, QLD", "qld", "Queensland", "Australia/Brisbane"),
        ("Perth, WA", "wa", "Western Australia", "Australia/Perth"),
    ),
    *_country("NZ", "New Zealand", "new-zealand", "Pacific/Auckland", "Auckland", "Wellington"),
)


def _index() -> dict[tuple[str, str], CityChoice]:
    """`(key, region)` to row, built once at import so `lookup` is a dict hit, not a scan.

    **The lookup key omits the country**, because the caller has none to give: a stored
    preference is a bare string. That makes "no two rows share a `(key, region)`" a real
    constraint on this dataset and not just a nicety — a collision would make `lookup`
    pick one of two countries at random. `tests/domain/test_city_catalog.py` asserts it.
    """
    return {split_region(row.name): row for row in WORLD_CITIES}


_INDEX = _index()


def lookup(name: str | None) -> CityChoice | None:
    """The row for a stored city string, or None when the city is not in the catalog.

    Case and spacing do not matter — "  portland, or " finds "Portland, OR" — because the
    index is keyed on what `split_region` makes of the name, the same folding
    `city_identity` uses. None is a real answer, not a failure: a reader may hold a city
    that predates the catalog, or one `city-coverage-request` has yet to add.
    """
    key = split_region(name)
    return _INDEX.get(key) if key[0] else None


def choices() -> tuple[CityChoice, ...]:
    """Every row, alphabetical by the label a reader sees, for the picker to render."""
    return tuple(sorted(WORLD_CITIES, key=lambda row: row.label.casefold()))


def is_known(name: str | None) -> bool:
    """Whether `name` may be picked. The question most callers actually have."""
    return lookup(name) is not None


__all__ = [
    "WORLD_CITIES",
    "CityChoice",
    "choices",
    "is_known",
    "lookup",
]

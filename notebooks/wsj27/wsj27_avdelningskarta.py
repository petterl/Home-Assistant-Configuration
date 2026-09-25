"""
WSJ 2027 - Avdelningskarta.

Bygger en KeplerGL-karta som visar var alla deltagare, ledare, IST och CMT bor,
med deltagare och ledare färgade per avdelning (1-53).

Avdelningen läses direkt ur Scoutnet, som är facit sedan pushen i juni 2026:
  - Deltagare (form 39188)            -> question 88168
  - Avdelningsledare (form 47115)     -> question 107592
IST och CMT har ingen avdelning - de jobbar i funktionärsteam - och får därför
egna, enfärgade lager.

Används av: wsj_karta_avdelningar.ipynb
"""

import json
import os
import statistics

import numpy as np

import wsj27_utils as _u
from wsj27_utils import (
    GROUP_COLORS,
    _HTML_TEMPLATE,
    MAPBOX_TOKEN,
    CMT_FEES,
    DELTAGARE_FEES,
    IST_FEES,
)

# =============================================================================
# Konstanter
# =============================================================================

# Avdelningsledare - egna fee_ids, ingen åldersvalidering i Scoutnet
LEDARE_DIREKTRESA = '25695'
LEDARE_RUNDRESA = '27560'
LEDARE_FEES = {LEDARE_DIREKTRESA, LEDARE_RUNDRESA}

# Question IDs för "Avdelning" - olika formulär har olika fält
Q_AVDELNING_DELTAGARE = '88168'   # form 39188 (Deltagare / IST)
Q_AVDELNING_LEDARE = '107592'     # form 47115 (Avdelningsledare)

# Globalt avdelningsschema: direktresa 1-16, rundresa 17-53
AVDELNING_MIN, AVDELNING_MAX = 1, 53

IST_COLOR = [232, 168, 56]    # WSJ-guld
CMT_COLOR = [150, 150, 150]   # grå


# =============================================================================
# Berikning: roll + avdelning från Scoutnet
# =============================================================================

def enrich_with_avdelning(df, raw_data):
    """Lägg till kolumnerna `roll` och `avdelning` på en deltagar-DataFrame.

    df:       resultatet av wsj27_utils.build_participant_dataframe()
    raw_data: samma råsvar från Scoutnet som df byggdes av

    `build_participant_dataframe` känner inte till ledar-avgifterna och klassar
    dem som `ist` med travel `other`. Den funktionen används av alla
    gruppindelnings-notebooks, så i stället för att ändra den rättar vi rollen
    och resetypen här.

    Nya kolumner:
      roll           - 'deltagare' | 'ledare' | 'ist' | 'cmt'
      avdelning      - int 1-53, eller 0 för den som saknar avdelning
      avdelning_txt  - '17' eller '-' för visning i tooltip
      avd_farg       - etikett ('Avd 07'), enbart för kartans färgskala

    Returnerar en kopia av df; originalet lämnas orört.
    """
    df = df.copy()

    # member_no -> (fee_id, avdelning). Nycklas på member_no, inte på API:ts
    # dict-nyckel, eftersom df:s member_no kommer från fältet member_no.
    info = {}
    for mid, p in raw_data.get('participants', {}).items():
        member_no = str(p.get('member_no', mid))
        fee_id = str(p.get('fee_id', ''))
        questions = p.get('questions', {})
        if not isinstance(questions, dict):
            questions = {}
        qid = Q_AVDELNING_LEDARE if fee_id in LEDARE_FEES else Q_AVDELNING_DELTAGARE
        raw_avd = questions.get(qid, '')
        try:
            avd = int(str(raw_avd).strip())
        except (TypeError, ValueError):
            avd = 0
        if not (AVDELNING_MIN <= avd <= AVDELNING_MAX):
            avd = 0
        info[member_no] = (fee_id, avd)

    def roll_for(fee_id):
        if fee_id in LEDARE_FEES:
            return 'ledare'
        if fee_id in DELTAGARE_FEES:
            return 'deltagare'
        if fee_id in CMT_FEES:
            return 'cmt'
        if fee_id in IST_FEES:
            return 'ist'
        return 'ist'

    def travel_for(fee_id, current):
        if fee_id == LEDARE_DIREKTRESA:
            return 'direktresa'
        if fee_id == LEDARE_RUNDRESA:
            return 'rundresa'
        return current

    rolls, avds, travels = [], [], []
    for _, row in df.iterrows():
        fee_id, avd = info.get(str(row['member_no']), (str(row.get('fee_id', '')), 0))
        rolls.append(roll_for(fee_id))
        avds.append(avd)
        travels.append(travel_for(fee_id, row.get('travel', 'other')))

    df['roll'] = rolls
    df['avdelning'] = avds
    df['avdelning_txt'] = ['-' if a == 0 else str(a) for a in avds]
    # Separat fält för färgsättningen. KeplerGL tillåter den ordinala
    # färgskalan bara på strängfält och typdetekterar fälten ur datan, inte ur
    # konfigurationen - en sifferliknande sträng som '07' blir ett heltalsfält
    # och skalan faller tillbaka till `quantize`, som målar alla punkter lika.
    # Prefixet gör fältet otvetydigt textuellt, och nollutfyllnaden gör att den
    # lexikografiska ordningen blir numerisk och därmed identisk i deltagar-
    # och ledardatasetet - så en avdelnings ledare får samma färg som dess
    # deltagare.
    df['avd_farg'] = ['Ingen' if a == 0 else f'Avd {a:02d}' for a in avds]
    df['travel'] = travels

    print('Roll och avdelning från Scoutnet:')
    for roll in ('deltagare', 'ledare', 'ist', 'cmt'):
        sub = df[df['roll'] == roll]
        if not len(sub):
            continue
        n_avd = int((sub['avdelning'] > 0).sum())
        print(f'  {roll:<10} {len(sub):>5} personer, {n_avd:>5} med avdelning')

    saknar = df[(df['roll'].isin(['deltagare', 'ledare'])) & (df['avdelning'] == 0)]
    if len(saknar):
        print(f'\nVARNING: {len(saknar)} deltagare/ledare saknar avdelning i Scoutnet:')
        for _, r in saknar.iterrows():
            print(f"  {r['name']} ({r['member_no']}) - {r['roll']}, {r['kar']}")

    return df


def print_avdelning_summary(df, expected_ledare=4):
    """Skriv ut en rad per avdelning: antal deltagare, ledare och geografisk spridning.

    Sprid = medelavståndet i km från avdelningens tyngdpunkt, vilket visar hur
    utspridd avdelningen är över landet. Kräver att df har lat/lng.
    """
    from wsj27_utils import haversine_km

    df_avd = df[df['avdelning'] > 0]
    if not len(df_avd):
        print('Ingen med avdelning - kör enrich_with_avdelning() först.')
        return

    print(f'{"Avd":>4} {"Resa":>11} {"Delt":>5} {"Led":>4} {"Sprid":>8}  Anmärkning')
    print('-' * 70)
    for avd in range(AVDELNING_MIN, AVDELNING_MAX + 1):
        a = df_avd[df_avd['avdelning'] == avd]
        if not len(a):
            print(f'{avd:>4} {"-":>11} {0:>5} {0:>4} {"-":>8}  TOM')
            continue
        n_del = int((a['roll'] == 'deltagare').sum())
        n_led = int((a['roll'] == 'ledare').sum())
        travel = a['travel'].mode().iat[0] if len(a['travel'].mode()) else '?'

        lat0, lng0 = a['lat'].mean(), a['lng'].mean()
        spread = np.mean([haversine_km(lat0, lng0, la, ln)
                          for la, ln in zip(a['lat'], a['lng'])])

        notes = []
        if n_led != expected_ledare:
            notes.append(f'{n_led} ledare (väntat {expected_ledare})')
        if n_del == 0:
            notes.append('inga deltagare')
        print(f'{avd:>4} {travel:>11} {n_del:>5} {n_led:>4} {spread:>6.0f} km  '
              f'{", ".join(notes)}')

    print('-' * 70)
    print(f'{"Tot":>4} {"":>11} {int((df_avd["roll"] == "deltagare").sum()):>5} '
          f'{int((df_avd["roll"] == "ledare").sum()):>4}')


# =============================================================================
# Koordinater
# =============================================================================

GEONAMES_PATH = '/config/notebooks/wsj27/input/geonames_SE.txt'
GEONAMES_URL = 'https://download.geonames.org/export/zip/SE.zip'


def load_postnummer_coords(path=GEONAMES_PATH, download_if_missing=True):
    """Returnera {postnummer utan blanksteg: (lat, lng, ort)} från GeoNames.

    Postnummer geokodas INTE med Nominatim. Ortnamn är tvetydiga - Spånga finns
    både i Stockholm och i Värmland, Korsberga både i Småland och i
    Västergötland - och namnuppslag valde fel ort i tiotals fall, vilket
    flyttade personer upp till 24 mil fel på kartan. GeoNames postnummerfil är
    en uppslagstabell över landets ~18 900 postnummer och har inget sådant
    tolkningsutrymme.
    """
    if not os.path.exists(path) and download_if_missing:
        import io, urllib.request, zipfile
        print(f'Hämtar postnummertabell från {GEONAMES_URL} ...')
        with urllib.request.urlopen(GEONAMES_URL, timeout=120) as r:
            blob = r.read()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(zipfile.ZipFile(io.BytesIO(blob)).read('SE.txt'))

    out = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            fields = line.rstrip('\n').split('\t')
            if len(fields) > 10 and fields[9] and fields[10]:
                out[fields[1].replace(' ', '')] = (
                    float(fields[9]), float(fields[10]), fields[2])
    return out


INPUT_DIR = '/config/notebooks/wsj27/input'


def adress_kallor(input_dir=INPUT_DIR):
    """Adressexporter att läsa, nyaste först.

    Scoutnets deltagar-API exponerar ingen adress alls (`contact_info` innehåller
    bara telefon och e-post), så hemadresserna måste komma från exportfiler.
    `projectParticipantsReportFull_*.xlsx` täcker även avdelningsledarna, vilket
    deltagar-CSV:n (formulär 39188) inte gör - utan den hamnar ledarna på sin
    kårs position i stället för där de bor.

    Filerna väljs dynamiskt så att en nyare uppladdad rapport används
    automatiskt; namnets tidsstämpel (`..._YYYYMMDD_HHMM.xlsx`) ger ordningen.
    """
    import glob
    reports = sorted(
        glob.glob(os.path.join(input_dir, 'projectParticipantsReportFull_*.xlsx')),
        reverse=True)
    paths = list(reports)
    newest_csv = _u._newest_participants_csv(input_dir)
    if newest_csv:
        paths.append(newest_csv)
    return paths


def _read_address_rows(paths=None):
    """Läs (member_no, postnummer, postort, land) ur adressexporterna.

    Tidigare filer i listan vinner. Returnerar {member_no: (pnr, ort, land)}.
    """
    import pandas as pd

    if paths is None:
        paths = adress_kallor()

    out = {}
    for path in paths:
        if not os.path.exists(path):
            print(f'  (adresskälla saknas: {os.path.basename(path)})')
            continue
        try:
            df = (pd.read_excel(path) if path.lower().endswith(('.xlsx', '.xls'))
                  else pd.read_csv(path, encoding='utf-8'))
        except Exception as e:
            print(f'  (kunde inte läsa {os.path.basename(path)}: {e})')
            continue
        cols = {str(c).strip().lower(): c for c in df.columns}
        need = ('medlemsnummer', 'postnummer', 'postort', 'land')
        if not all(n in cols for n in need):
            print(f'  (hoppar över {os.path.basename(path)}: saknar adresskolumner)')
            continue
        added = 0
        for _, r in df.iterrows():
            mno = str(r[cols['medlemsnummer']]).strip()
            if not mno or mno in out:
                continue
            out[mno] = (str(r[cols['postnummer']]).strip(),
                        str(r[cols['postort']]).strip(),
                        str(r[cols['land']]).strip())
            added += 1
        print(f'  {os.path.basename(path)}: +{added} adresser')
    return out


def assign_map_coordinates(df,
                           address_paths=None,
                           fallback_cache='/config/notebooks/wsj27/adress_geocode_cache.json',
                           kar_cache='/config/notebooks/wsj27/scoutkar_geocode_cache.json'):
    """Sätt lat/lng per person för avdelningskartan. Ändrar df på plats.

    Prioritet:
      1. Manuell override (manual_friend_overrides.MANUAL_PERSON_COORDS)
      2. Hemadressens postnummer via GeoNames  <- nästan alla
      3. Hemadressen via den gamla Nominatim-cachen (utländska adresser)
      4. Kårens position, i första hand medianen av kårmedlemmarnas hem
      5. Sveriges mittpunkt

    Steg 4 föredrar medianen framför den geokodade kårpositionen därför att
    kårnamn är opålitliga att slå upp: 98 av dem matchade en gata i stället för
    en ort (`Equmenia Scout` blev Scoutvägen i Bromölla) och 22 gav ingen träff
    alls. Medlemmarnas egna postnummer säger var kåren faktiskt finns.

    Lägger till kolumnen `coord_source` så det går att se vad som är exakt och
    vad som är uppskattat. Skriver inte till någon delad cache.
    """
    postnr = load_postnummer_coords()

    old_cache = {}
    if os.path.exists(fallback_cache):
        with open(fallback_cache, encoding='utf-8') as f:
            old_cache = json.load(f)

    print('Adresskällor:')
    rows = _read_address_rows(address_paths)

    home, home_src = {}, {}
    for mno, (pnr, city, land) in rows.items():
        hit = postnr.get(pnr.replace(' ', ''))
        if hit:
            home[mno] = (hit[0], hit[1])
            home_src[mno] = 'postnr'
            continue
        entry = old_cache.get(f'{pnr}|{city}|{land}')
        if entry and entry.get('lat') is not None:
            home[mno] = (entry['lat'], entry['lng'])
            home_src[mno] = 'cache'

    kar_geo = {}
    if os.path.exists(kar_cache):
        with open(kar_cache, encoding='utf-8') as f:
            kar_geo = json.load(f)

    members = {}
    for _, r in df.iterrows():
        c = home.get(str(r['member_no']))
        if c and r['kar']:
            members.setdefault(r['kar'], []).append(c)

    kar_coord, kar_src = {}, {}
    for kar in df['kar'].dropna().unique():
        pts = members.get(kar, [])
        if len(pts) >= 2:
            kar_coord[kar] = (statistics.median(p[0] for p in pts),
                              statistics.median(p[1] for p in pts))
            kar_src[kar] = 'medlemsmedian'
        elif (kar_geo.get(kar) or {}).get('lat') is not None:
            g = kar_geo[kar]
            kar_coord[kar] = (g['lat'], g['lng'])
            kar_src[kar] = 'geokod'
        elif len(pts) == 1:
            kar_coord[kar] = pts[0]
            kar_src[kar] = 'enda medlem'

    person_coords = {}
    try:
        import importlib, sys as _sys
        if '/config/notebooks/wsj27' not in _sys.path:
            _sys.path.insert(0, '/config/notebooks/wsj27')
        if 'manual_friend_overrides' in _sys.modules:
            importlib.reload(_sys.modules['manual_friend_overrides'])
        import manual_friend_overrides as mfo
        person_coords = {str(k): tuple(v)
                         for k, v in getattr(mfo, 'MANUAL_PERSON_COORDS', {}).items()}
    except ImportError:
        pass

    lats, lngs, srcs = [], [], []
    for _, r in df.iterrows():
        mno = str(r['member_no'])
        if mno in person_coords:
            c, src = person_coords[mno], 'manuell'
        elif mno in home:
            c, src = home[mno], f'hem ({home_src[mno]})'
        elif r['kar'] in kar_coord:
            c, src = kar_coord[r['kar']], f'kår ({kar_src[r["kar"]]})'
        else:
            c, src = (_u.SWEDEN_LAT, _u.SWEDEN_LNG), 'MITTPUNKT'
        lats.append(c[0]); lngs.append(c[1]); srcs.append(src)

    df['lat'], df['lng'], df['coord_source'] = lats, lngs, srcs

    print('\nKoordinatkälla:')
    for src, n in df['coord_source'].value_counts().items():
        print(f'  {src:<22} {n:>5}')
    print('\n  varav per roll (hemadress):')
    for roll in ('deltagare', 'ledare', 'ist', 'cmt'):
        sub = df[df['roll'] == roll]
        if len(sub):
            n = int(sub['coord_source'].str.startswith('hem').sum())
            print(f'    {roll:<10} {n:>5} av {len(sub):>5}')
    kvar = df[df['coord_source'] == 'MITTPUNKT']
    if len(kvar):
        print(f'\nUtan position ({len(kvar)} st) - hamnar mitt i Sverige:')
        for _, r in kvar.iterrows():
            print(f"  {r['name']} ({r['member_no']}) - {r['roll']}, kår={r['kar']!r}")
    return df


# =============================================================================
# Kartan
# =============================================================================

def _point_layer(layer_id, data_id, label, color, radius, visible=True,
                 palette=None, outline=False):
    """Bygg ett KeplerGL-punktlager ovanpå ett dataset.

    palette satt -> färgas per avdelning (ordinal skala), annars enfärgat.
    """
    vis_config = {
        'radius': radius,
        'fixedRadius': False,
        'opacity': 0.85,
        'outline': outline,
        'thickness': 2,
        'strokeColor': [255, 255, 255],
        'radiusRange': [4, 20],
        'filled': True,
    }
    visual_channels = {
        'colorField': None,
        'colorScale': 'quantile',
        'sizeField': None,
        'sizeScale': 'linear',
        'strokeColorField': None,
        'strokeColorScale': 'quantile',
    }
    if palette:
        vis_config['colorRange'] = {
            'name': 'Avdelningsfärger',
            'type': 'qualitative',
            'category': 'Custom',
            'colors': palette,
        }
        visual_channels['colorField'] = {'name': 'avd_farg', 'type': 'string'}
        visual_channels['colorScale'] = 'ordinal'

    return {
        'id': layer_id,
        'type': 'point',
        'config': {
            'dataId': data_id,
            'label': label,
            'isVisible': visible,
            'columns': {'lat': 'lat', 'lng': 'lng'},
            'color': color,
            'visConfig': vis_config,
        },
        'visualChannels': visual_channels,
    }


def _tooltip_fields():
    return [
        {'name': 'name', 'format': None},
        {'name': 'roll', 'format': None},
        {'name': 'avdelning_txt', 'format': None},
        {'name': 'kar', 'format': None},
        {'name': 'age', 'format': None},
        {'name': 'travel', 'format': None},
    ]


def generate_avdelning_map_html(
        df,
        output_path='/config/notebooks/wsj27/output/wsj_avdelningar_karta.html',
        title='WSJ 2027 - Avdelningar',
        jitter=0.01):
    """Skriv en fristående KeplerGL-karta över alla personer, färgad per avdelning.

    df: DataFrame med kolumnerna name, kar, roll, avdelning, avdelning_txt,
        avd_farg, age, travel, lat, lng (se enrich_with_avdelning +
        wsj27_utils.assign_coordinates).
    jitter: slumpmässig spridning i grader (~1 km vid 0.01) så att personer som
        delar koordinat - kårkompisar utan hemadress - inte döljer varandra.

    Varje roll får ett eget dataset. KeplerGL:s filter är dataset-breda - fältet
    `layerId` skopar dem INTE till ett enskilt lager - så ett gemensamt dataset
    hade låtit rollfiltren krocka med varandra. Med ett dataset per roll blir
    lagren oberoende, och avdelningsfiltret spänner över de två dataset som
    faktiskt har en avdelning.
    """
    cols = ['name', 'kar', 'roll', 'avdelning', 'avdelning_txt', 'avd_farg',
            'age', 'travel', 'lat', 'lng']
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f'df saknar kolumnerna: {missing}')

    np.random.seed(42)
    df_map = df[cols].copy()
    df_map['age'] = df_map['age'].astype(int)
    df_map['lat'] = df_map['lat'] + np.random.uniform(-jitter, jitter, len(df_map))
    df_map['lng'] = df_map['lng'] + np.random.uniform(-jitter, jitter, len(df_map))

    # GROUP_COLORS har 21 färger, avdelningarna är 53. Färgerna cyklas, så en
    # färg delas av ett par avdelningar - avdelningsfiltret är det som skiljer
    # dem åt i praktiken. Den ordinala skalan tilldelar färg efter `avd_farg`s
    # sorteringsordning; deltagar- och ledardatasetet innehåller båda samtliga
    # 53 avdelningar, så domänen blir identisk och en avdelnings ledare får
    # samma färg som dess deltagare.
    palette = ['#' + ''.join(f'{c:02x}' for c in GROUP_COLORS[i % len(GROUP_COLORS)])
               for i in range(AVDELNING_MAX + 1)]

    data = {}
    for roll in ('deltagare', 'ledare', 'ist', 'cmt'):
        sub = df_map[df_map['roll'] == roll]
        if len(sub):
            data[roll] = sub.to_dict(orient='split')

    layers = []
    if 'deltagare' in data:
        layers.append(_point_layer('lager-deltagare', 'deltagare', 'Deltagare',
                                   [31, 120, 180], radius=7, palette=palette))
    if 'ledare' in data:
        layers.append(_point_layer('lager-ledare', 'ledare', 'Ledare',
                                   [31, 120, 180], radius=14, palette=palette,
                                   outline=True))
    if 'ist' in data:
        layers.append(_point_layer('lager-ist', 'ist', 'IST', IST_COLOR, radius=6))
    if 'cmt' in data:
        layers.append(_point_layer('lager-cmt', 'cmt', 'CMT', CMT_COLOR, radius=6,
                                   visible=False))

    # Ett avdelningsfilter per dataset. Ett enda filter över båda dataseten
    # (`dataId: ['deltagare', 'ledare']`) ser rimligt ut men är trasigt i
    # KeplerGL 2.5.5: när konfigen laddas statiskt slås fältindexet upp för
    # bara ett av dataseten och det andra får `fieldIdx: null`. GPU-filtret
    # läser då en obefintlig kolumn, ingen rad klarar spannet, och hela det
    # datasetet försvinner från kartan. Med ett filter per dataset slår vardera
    # upp sitt eget index. Priset är två reglage i filterpanelen i stället för
    # ett - dra båda till samma avdelning för att isolera den.
    filters = [
        {
            'dataId': [data_id],
            'id': f'filter-avdelning-{data_id}',
            'name': ['avdelning'],
            'type': 'range',
            'value': [AVDELNING_MIN, AVDELNING_MAX],
            'enlarged': False,
            'plotType': 'histogram',
            'animationWindow': 'free',
            'yAxis': None,
        }
        for data_id in ('deltagare', 'ledare') if data_id in data
    ]

    kepler_config = {
        'version': 'v1',
        'config': {
            'mapState': {'latitude': 60.0, 'longitude': 15.5, 'zoom': 4.5},
            'visState': {
                'filters': filters,
                'layers': layers,
                'interactionConfig': {
                    'tooltip': {
                        'fieldsToShow': {k: _tooltip_fields() for k in data},
                        'compareMode': False,
                        'compareType': 'absolute',
                        'enabled': True,
                    },
                    'brush': {'size': 0.5, 'enabled': False},
                    'geocoder': {'enabled': False},
                    'coordinate': {'enabled': False},
                },
            },
        },
    }

    data_config = {
        'config': kepler_config,
        'data': data,
        'options': {'readOnly': False, 'centerMap': False},
    }

    html_content = (_HTML_TEMPLATE
                    .replace('__DATA_CONFIG__', json.dumps(data_config))
                    .replace('__MAPBOX_TOKEN__', MAPBOX_TOKEN)
                    .replace('__TITLE__', title))

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f'Sparade avdelningskarta: {output_path}')
    print(f'  {len(df_map)} personer: ' +
          ', '.join(f'{len(v["data"])} {k}' for k, v in data.items()))
    return output_path

# curve_detector v2 — supporto GPX e KML in input, output KML o GPX
import math, argparse, re, os, sys
from xml.etree import ElementTree as ET

def haversine_m(p1, p2):
    R=6371000
    lat1,lon1 = math.radians(p1[1]), math.radians(p1[0])
    lat2,lon2 = math.radians(p2[1]), math.radians(p2[0])
    dlat=lat2-lat1; dlon=lon2-lon1
    a=math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(a))

def lerp(a, b, t):
    return (a[0] + (b[0]-a[0])*t, a[1] + (b[1]-a[1])*t)

def densify(coords, step_m=10):
    if step_m <= 0 or len(coords) < 2: return coords[:]
    out=[coords[0]]
    for i in range(1,len(coords)):
        a=out[-1]; b=coords[i]
        seglen = haversine_m(a,b)
        if seglen>step_m:
            n=int(seglen//step_m)
            for k in range(1,n+1):
                t=min(1.0, (k*step_m)/seglen)
                out.append(lerp(a,b,t))
        else:
            out.append(b)
    return out

def turn_angle_deg(p_prev, p, p_next):
    R=6378137.0
    lat0=math.radians(p[1])
    def to_xy(pt):
        lon,lat=math.radians(pt[0]), math.radians(pt[1])
        x = R*(lon - math.radians(p[0]))*math.cos(lat0)
        y = R*(lat - math.radians(p[1]))
        return (x,y)
    a=to_xy(p_prev); b=(0.0,0.0); c=to_xy(p_next)
    v1=(a[0]-b[0], a[1]-b[1]); v2=(c[0]-b[0], c[1]-b[1])
    n1=math.hypot(*v1); n2=math.hypot(*v2)
    if n1==0 or n2==0: return 0.0
    dot = (v1[0]*v2[0] + v1[1]*v2[1])/(n1*n2)
    dot = max(-1.0, min(1.0, dot))
    ang = math.degrees(math.acos(dot))
    return abs(180.0 - ang)  # deviazione dalla rettilineità

def turn_angle_signed_deg(p_prev, p, p_next):
    """Angolo di svolta con segno in gradi (SX positivo, DX negativo).
    Usa base locale XY centrata su p. Il modulo misura la deviazione dalla rettilineità.
    """
    R = 6378137.0
    lat0 = math.radians(p[1])
    def to_xy(pt):
        lon, lat = math.radians(pt[0]), math.radians(pt[1])
        x = R * (lon - math.radians(p[0])) * math.cos(lat0)
        y = R * (lat - math.radians(p[1]))
        return (x, y)
    a = to_xy(p_prev)
    b = (0.0, 0.0)
    c = to_xy(p_next)
    # vettori entrante (prev->p) e uscente (p->next)
    u = (b[0] - a[0], b[1] - a[1])
    v = (c[0] - b[0], c[1] - b[1])
    nu = math.hypot(*u)
    nv = math.hypot(*v)
    if nu == 0 or nv == 0:
        return 0.0
    # angolo con segno: positivo = SX (CCW), negativo = DX (CW)
    cross = u[0]*v[1] - u[1]*v[0]
    dot = u[0]*v[0] + u[1]*v[1]
    return math.degrees(math.atan2(cross, dot))

# --- Angle banding ---
def angle_band(angle_deg: float) -> str:
    """Classificazione aggiornata:
    0–30 = lunga
    30–55 = lunga
    55–100 = stretta
    100–130 = tornante aperto
    ≥150 = tornante
    """
    a = abs(angle_deg)
    if a >= 150:
        return "tornante"
    if a >= 100:
        return "tornante aperto"
    if a >= 55:
        return "stretta"
    if a >= 30:
        return "lunga"
    return "lunga"

def _cumdist_until(coords, start_idx, target_m):
    """Restituisce l'indice j >= start_idx tale che la distanza cumulata da start_idx a j >= target_m.
    Se non raggiunge target_m, ritorna l'ultimo indice disponibile."""
    if start_idx >= len(coords)-1:
        return start_idx
    acc = 0.0
    j = start_idx
    while j < len(coords)-1 and acc < target_m:
        acc += haversine_m(coords[j], coords[j+1])
        j += 1
    return j

def _cumdist_back_until(coords, start_idx, target_m):
    """Indice k <= start_idx tale che la distanza cumulata da start_idx a k >= target_m (camminando indietro).
    Se non raggiunge target_m, ritorna 0 o il minimo disponibile."""
    if start_idx <= 0:
        return 0
    acc = 0.0
    k = start_idx
    while k > 0 and acc < target_m:
        acc += haversine_m(coords[k], coords[k-1])
        k -= 1
    return k

def turn_angle_signed_deg_window(coords, i, back_m=25.0, fwd_m=25.0):
    """Angolo con segno in gradi usando punti a distanza metrica fissa prima/dopo i.
    Migliora la stima su tornanti rispetto all'uso dei soli adiacenti."""
    n = len(coords)
    if i <= 0 or i >= n-1:
        return 0.0
    ib = _cumdist_back_until(coords, i, back_m)
    jf = _cumdist_until(coords, i, fwd_m)
    # protezioni
    ib = max(0, min(i-1, ib))
    jf = min(n-1, max(i+1, jf))
    return turn_angle_signed_deg(coords[ib], coords[i], coords[jf])

def curve_evolution(coords, i, lookahead_m=40.0, delta_deg=15.0, baseline_m=25.0):
    """Etichetta evoluzione basata su bande: 'chiude molto', 'chiude' oppure ''.
    Confronta la banda al punto i con quella a ~lookahead_m metri dopo,
    usando una finestra metrica (baseline_m) per stimare gli angoli."""
    ang_now = abs(turn_angle_signed_deg_window(coords, i, back_m=baseline_m, fwd_m=baseline_m))
    band_now = angle_band(ang_now)
    j = _cumdist_until(coords, i, lookahead_m)
    if j <= i or j >= len(coords)-1:
        return ""
    ang_future = abs(turn_angle_signed_deg_window(coords, j, back_m=baseline_m, fwd_m=baseline_m))
    band_future = angle_band(ang_future)
    if band_now == "lunga" and band_future == "stretta":
        return "chiude molto"
    if band_now == "stretta" and band_future in ("stretta", "tornante aperto"):
        return "chiude"
    return ""

def classify_curve(angle_deg: float) -> str:
    """Ritorna la banda richiesta dall'utente: '6','5','4','3','2','1' o 'tornante'."""
    return angle_band(angle_deg)

def spectator_tip(curve_class: str):
    """Restituisce un breve consiglio dal punto di vista spettatore rally."""
    if curve_class == "tornante":
        return (
            "Spot sicuro sull'esterno, in alto rispetto al piano strada. Buona visuale di frenata e inversione; evita l'interno e l'uscita." 
        )
    if curve_class == "curva stretta":
        return (
            "Ottima lentezza vetture: posizionati sull'esterno rialzato prima del punto di corda. Mantieni grande distanza sull'uscita." 
        )
    if curve_class == "curva media":
        return (
            "Buon compromesso tra velocità e sicurezza: cerca un terrapieno esterno o un ingresso rialzato. Evita l'esterno in linea con la traiettoria." 
        )
    # curva veloce
    return (
        "Alta velocità: privilegia un punto molto arretrato e rialzato, dietro barriere naturali. Evita assolutamente esterno e vie di fuga." 
    )

def street_view_url(lat: float, lon: float) -> str:
    """Genera un link a Google Street View per la coppia lat/lon."""
    # Uso del layer Street View con coordinate base della camera
    return f"https://www.google.com/maps?cbll={lat:.7f},{lon:.7f}&layer=c"

def xml_escape(s: str) -> str:
    """Escape minimale per l'inserimento in XML (KML/GPX)."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# --- Parser KML ---
def parse_first_linestring_from_kml(kml_text):
    m = re.search(r"<LineString[\s\S]*?<coordinates>([\s\S]*?)</coordinates>", kml_text, re.IGNORECASE)
    if not m: return []
    coord_text = m.group(1).strip()
    coords=[]
    for part in coord_text.replace("\n"," ").split():
        if ',' in part:
            lonlatalt = part.split(",")
            if len(lonlatalt)>=2:
                try:
                    lon=float(lonlatalt[0]); lat=float(lonlatalt[1])
                    coords.append((lon,lat))
                except: pass
    return coords

# --- Parser GPX ---
def parse_tracks_from_gpx(gpx_text):
    coords=[]
    try:
        root = ET.fromstring(gpx_text)
    except ET.ParseError:
        return []
    # trk/trkseg/trkpt
    for trk in root.findall('.//{*}trk'):
        for seg in trk.findall('.//{*}trkseg'):
            for pt in seg.findall('{*}trkpt'):
                lat = pt.get('lat'); lon = pt.get('lon')
                if lat is not None and lon is not None:
                    try:
                        coords.append((float(lon), float(lat)))
                    except: continue
    # fallback a rte/rtept
    if not coords:
        for rtept in root.findall('.//{*}rtept'):
            lat = rtept.get('lat'); lon = rtept.get('lon')
            if lat is not None and lon is not None:
                try:
                    coords.append((float(lon), float(lat)))
                except: continue
    return coords

def parse_coords_auto(path):
    txt = open(path, "r", encoding="utf-8").read()
    low = txt.lower()
    if path.lower().endswith(".gpx") or "<gpx" in low:
        coords = parse_tracks_from_gpx(txt)
        if not coords:
            raise ValueError("GPX valido ma nessun <trkpt> o <rtept> trovato.")
        return coords
    coords = parse_first_linestring_from_kml(txt)
    if not coords:
        raise ValueError("KML/GPX non riconosciuto: nessun LineString (KML) o trkpt (GPX) trovato.")
    return coords

def write_points_kml(points, out_path, name="Curve"):
    def placemark(p):
        name_esc = xml_escape(p.get('name','Curve'))
        desc_esc = xml_escape(p.get('desc',''))
        return f"""
        <Placemark>
          <styleUrl>#binoc</styleUrl>
          <name>{name_esc}</name>
          <description>{desc_esc}</description>
          <Point><coordinates>{p['lon']},{p['lat']},0</coordinates></Point>
        </Placemark>
        """.strip()
    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>{xml_escape(name)}</name>
  <Style id="binoc">
    <IconStyle>
      <scale>1.0</scale>
      <Icon>
        <href>http://maps.google.com/mapfiles/kml/shapes/binoculars.png</href>
      </Icon>
    </IconStyle>
  </Style>
  {"".join(placemark(p) for p in points)}
</Document>
</kml>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(kml)

def write_points_gpx(points, out_path, name="Curve"):
    parts = []
    for p in points:
        nm = xml_escape(p.get("name","Curve"))
        ds = xml_escape(p.get("desc",""))
        parts.append(f'<wpt lat="{p["lat"]}" lon="{p["lon"]}"><name>{nm}</name><desc>{ds}</desc></wpt>')
    gpx = f'''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="curve_detector" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata><name>{xml_escape(name)}</name></metadata>
  {''.join(parts)}
</gpx>
'''
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(gpx)

def main():
    ap=argparse.ArgumentParser(description="Crea geotag su curve da KML/GPX.")
    ap.add_argument("in_path", help="Input .gpx o .kml")
    ap.add_argument("out_path", help="Output .kml o .gpx (deciso dall’estensione)")
    ap.add_argument("--threshold", type=float, default=15.0, help="Soglia svolta in gradi (default 15)")
    ap.add_argument("--step", type=float, default=5.0, help="Densificazione (m) per segmenti lunghi (default 5)")
    ap.add_argument("--minsep", type=float, default=35.0, help="Distanza minima (m) tra curve successive (default 35)")
    ap.add_argument("--baseline", type=float, default=35.0, help="Distanza (m) prima/dopo il punto per stimare l'angolo firmato (default 35)")
    args=ap.parse_args()

    coords = parse_coords_auto(args.in_path)
    if len(coords) < 3:
        raise ValueError("Tracciato troppo corto (<3 punti).")
    coords = densify(coords, step_m=args.step)

    curve_pts=[]; last_kept=None
    i = 1
    n = len(coords)
    while i < n-1:
        ang_signed = turn_angle_signed_deg_window(coords, i, back_m=args.baseline, fwd_m=args.baseline)
        t = abs(ang_signed)
        if t >= args.threshold:
            # entra in cluster: scorri fino a uscire dalla soglia, tenendo il max
            max_t = t
            max_i = i
            j = i + 1
            while j < n-1:
                ang_j_signed = turn_angle_signed_deg_window(coords, j, back_m=args.baseline, fwd_m=args.baseline)
                tj = abs(ang_j_signed)
                if tj < args.threshold:
                    break
                if tj > max_t:
                    max_t = tj
                    max_i = j
                j += 1
            # usa il punto di massimo (punto di corda) se rispetta la distanza minima
            apex = coords[max_i]
            if last_kept is None or haversine_m(apex, last_kept) >= args.minsep:
                ang_signed_apex = turn_angle_signed_deg_window(coords, max_i, back_m=args.baseline, fwd_m=args.baseline)
                t_apex = abs(ang_signed_apex)
                categoria = classify_curve(t_apex)
                dir_lbl = "Sinistra" if ang_signed_apex > 0 else ("Destra" if ang_signed_apex < 0 else "—")
                evol = curve_evolution(coords, max_i, lookahead_m=40.0, delta_deg=15.0, baseline_m=args.baseline)
                lat_i = apex[1]
                lon_i = apex[0]
                sv = street_view_url(lat_i, lon_i)
                title = f"{dir_lbl} {categoria}"
                if evol:
                    title += f" {evol}"
                curve_pts.append({
                    "lon": lon_i,
                    "lat": lat_i,
                    "name": title,
                    "desc": (
                        f"Svolta ≈ {t_apex:.1f}°\nStreet View: {sv}"
                    )
                })
                last_kept = apex
            # salta al termine del cluster
            i = j
        else:
            i += 1
    name=f"Curve (≥ {args.threshold}°)"
    ext = os.path.splitext(args.out_path.lower())[1]
    if ext == ".gpx":
        write_points_gpx(curve_pts, args.out_path, name=name)
    else:
        write_points_kml(curve_pts, args.out_path, name=name)

    print(f"Creati {len(curve_pts)} punti curva → {os.path.abspath(args.out_path)}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        sys.exit(1)
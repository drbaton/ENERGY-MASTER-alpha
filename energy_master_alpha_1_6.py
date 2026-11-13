"""Energy Master Alpha 1.6 — compact final report, topology-aware demand, music and large map.
Install: pip install pygame
Run: python energy_master_alpha_1_3.py
"""
import math
from pathlib import Path
import random
from collections import defaultdict
from collections import deque
import pygame

pygame.init()

# Muzyka w tle: music.mp3 obok pliku .py lub .exe.
# Klawisze: M — wlacz/wylacz, < i > — zmiana glosnosci o 10 p.p.
MUSIC_VOLUME = 0.20
MUSIC_ENABLED = True
MUSIC_AVAILABLE = False

def music_path():
    # PyInstaller onefile: najpierw katalog EXE, potem zasoby spakowane.
    import sys
    paths = []
    if getattr(sys, 'frozen', False):
        paths.append(Path(sys.executable).resolve().parent / 'music.mp3')
        if hasattr(sys, '_MEIPASS'):
            paths.append(Path(sys._MEIPASS) / 'music.mp3')
    paths.append(Path(__file__).resolve().parent / 'music.mp3')
    return next((p for p in paths if p.is_file()), None)

def start_music():
    global MUSIC_AVAILABLE
    path = music_path()
    if path is None:
        print('Muzyka: brak music.mp3 — gra uruchomi sie bez dzwieku.')
        return
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.set_volume(MUSIC_VOLUME)
        pygame.mixer.music.play(-1)
        MUSIC_AVAILABLE = True
    except (pygame.error, OSError) as exc:
        print(f'Muzyka niedostepna: {exc}')

def handle_music_key(event):
    global MUSIC_VOLUME, MUSIC_ENABLED
    if event.key == pygame.K_m:
        MUSIC_ENABLED = not MUSIC_ENABLED
        if MUSIC_AVAILABLE:
            pygame.mixer.music.set_volume(MUSIC_VOLUME if MUSIC_ENABLED else 0.0)
        return True
    # Na polskiej klawiaturze znaki < > moga wymagac Shift.
    # Akceptujemy zarowno znaki tekstowe, jak i fizyczne klawisze , .
    if event.unicode in ('<', '>') or event.key in (pygame.K_COMMA, pygame.K_PERIOD):
        direction = -1 if event.unicode == '<' or event.key == pygame.K_COMMA else 1
        MUSIC_VOLUME = round(max(0.0, min(1.0, MUSIC_VOLUME + direction * 0.10)), 2)
        if MUSIC_AVAILABLE:
            pygame.mixer.music.set_volume(MUSIC_VOLUME if MUSIC_ENABLED else 0.0)
        return True
    return False

def show_splash():
    """Trzysekundowy ekran startowy, bez dodatkowych zaleznosci."""
    splash = pygame.display.set_mode((640, 480), pygame.NOFRAME)
    pygame.display.set_caption('Energy Master')
    splash.fill((17, 30, 43))
    logo_path = Path(__file__).resolve().parent / 'em.png'
    if logo_path.is_file():
        try:
            logo = pygame.image.load(str(logo_path)).convert_alpha()
            iw, ih = logo.get_size()
            if iw > 0 and ih > 0:
                scale = min(640 / iw, 480 / ih)
                logo = pygame.transform.smoothscale(logo, (max(1, int(iw * scale)),
                                                            max(1, int(ih * scale))))
                splash.blit(logo, logo.get_rect(center=(320, 230)))
        except (pygame.error, OSError) as exc:
            print(f'Nie mozna wczytac em.png: {exc}')
    title_font = pygame.font.SysFont('arial', 12, bold=True)
    title = title_font.render('alpha v1.6, by JakDab | poz 2026-11-13', True, (243, 207, 119))
    splash.blit(title, title.get_rect(center=(320, 468)))
    pygame.display.flip()
    start = pygame.time.get_ticks()
    timer = pygame.time.Clock()
    while pygame.time.get_ticks() - start < 3000:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
        timer.tick(60)

show_splash()
R = 40
MAP_W, MAP_H = 900, 680
CHART_H = 0
PANEL = 380
WIDTH, HEIGHT = 1280, 720
BESS_BUTTON_Y = 594
ECON_BUTTON_Y = 635
# Alpha 1.4: swiat ~5x wiekszy powierzchniowo, okno gry bez zmian.
WORLD_SCALE = 5 ** 0.5
WORLD_W, WORLD_H = round(MAP_W * WORLD_SCALE), round(MAP_H * WORLD_SCALE)
COLS, ROWS = math.ceil(WORLD_W / (math.sqrt(3) * R)) + 5, math.ceil(WORLD_H / (1.5 * R)) + 5
OX, OY = 40, 40
camera_x = camera_y = 0.0
CAMERA_SPEED = 580.0  # piksele swiata / sekunde
MINIMAP = pygame.Rect(MAP_W - 232, 12, 220, 153)
MINIMAP_INNER = MINIMAP.inflate(-14, -29)

LINE_CAPACITY = 50.0
CUSTOMERS_PER_TILE = 500
DEMAND_PER_CUSTOMER = 0.012  # MW at nominal demand; 6 MW per city hex
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption('Energy Master Alpha 1.6 — LARGE MAP & MINIMAP')
clock = pygame.time.Clock()
font = pygame.font.SysFont('arial', 18)
small = pygame.font.SysFont('arial', 15)
chart_font = pygame.font.SysFont('arial', 14)
big = pygame.font.SysFont('arial', 24, bold=True)
BUILD = {
    '1': ('PV', 200, (243, 196, 64)),
    '2': ('WIND', 350, (107, 194, 227)),
    '3': ('GAS', 600, (216, 120, 105)),
    '4': ('BESS', 450, (175, 151, 225)),
    '5': ('FACTORY', 1000, (237, 231, 209)),
    '6': ('LINE', 25, (234, 194, 90)),
}
HEX_BORDER_COLOR = (25, 75, 10)  # kolor obwodki (RGB)
HEX_BORDER_WIDTH = 2
HEX_BORDER_ALPHA = 180  # 0 = niewidoczna, 255 = pelna
LINE_ALPHA = 128  # przezroczystosc polaczen: 128/255 = ok. 50%
LINE_MAINTENANCE_DAILY = 10.0  # coins / dobe / heks typu LINE
FACTORY_DAILY_INCOME = 100.0  # coins na fabryke za zakonczona dobe
# Taryfa OSD: oplata stala za heks odbiorczy/dobe i zmienna za MWh.
DISTRIBUTION_FIXED_FEE = 1.0
DISTRIBUTION_VARIABLE_FEE = 1.0
DEMAND_ELASTICITY = 0.30  # wrazliwosc poboru na zmienna taryfe (model gry)

# OPCJONALNA GRAFIKA PNG — katalog assets obok tego pliku.
# assets/terrain/grass_1..3.png, forest_1..3.png, farmland_1..3.png, city_1..3.png
# assets/buildings/pv.png, wind.png, gas.png, bess.png, factory.png, line.png
# Obrazy z przezroczystym tlem (RGBA); przy braku pliku zostaje rysunek Pygame.
ASSET_DIR = Path(__file__).resolve().parent / "assets"
TERRAIN_SPRITE_SIZE = (round(math.sqrt(3) * (R + 2)), round(2 * (R + 2)))
SPRITE_SIZE = TERRAIN_SPRITE_SIZE  # budynki i teren: identyczne proporcje heksa

def load_sprite(relative_path, size=SPRITE_SIZE):
    path = ASSET_DIR / relative_path
    if not path.is_file():
        return None
    try:
        image = pygame.image.load(str(path)).convert_alpha()
        if isinstance(size, int):
            size = (size, size)
        return pygame.transform.scale(image, size)
    except (pygame.error, OSError) as exc:
        print(f"Nie mozna wczytac grafiki {path}: {exc}")
        return None

TERRAIN_SPRITES = {name: load_sprite(f"terrain/{name}.png", TERRAIN_SPRITE_SIZE)
                   for name in ("grass", "forest", "farmland", "city")}
FOREST_SPRITES = [load_sprite(f"terrain/forest_{i}.png", TERRAIN_SPRITE_SIZE) for i in (1, 2, 3)]
FARMLAND_SPRITES = [load_sprite(f"terrain/farmland_{i}.png", TERRAIN_SPRITE_SIZE) for i in (1, 2, 3)]
CITY_SPRITES = [load_sprite(f"terrain/city_{i}.png", TERRAIN_SPRITE_SIZE) for i in (1, 2, 3)]
# Miasta nocne: wstaw swoje PNG city_night_1.png ... city_night_3.png.
# Brak pliku nocnego -> automatycznie uzywamy odpowiadajacej grafiki dziennej.
CITY_NIGHT_SPRITES = [load_sprite(f"terrain/city_night_{i}.png", TERRAIN_SPRITE_SIZE)
                      for i in (1, 2, 3)]
for i, sprite in enumerate(CITY_NIGHT_SPRITES, start=1):
    if sprite is None:
        print(f"[CITY DAY/NIGHT] Brak assets/terrain/city_night_{i}.png — noc uzyje wersji dziennej.")


def city_sprite_at(pos, sim_hour):
    q, r = pos
    index = ((q * 73856093) ^ (r * 19349663)) % 3
    day_sprite = CITY_SPRITES[index]
    if 6 <= sim_hour % 24 < 18:
        return day_sprite
    return CITY_NIGHT_SPRITES[index] or day_sprite

# Trzy stale warianty trawy (wybor zalezy od wspolrzednych heksa).
GRASS_SPRITES = [load_sprite(f"terrain/grass_{i}.png", TERRAIN_SPRITE_SIZE) for i in (1, 2, 3)]
if not any(GRASS_SPRITES):
    GRASS_SPRITES = [TERRAIN_SPRITES.get('grass')]

def terrain_sprite_at(pos, kind):
    q, r = pos
    variants = {"grass": GRASS_SPRITES, "forest": FOREST_SPRITES,
                "farmland": FARMLAND_SPRITES, "city": CITY_SPRITES}.get(kind, [])
    available = [sprite for sprite in variants if sprite is not None]
    if available:
        return available[((q * 73856093) ^ (r * 19349663)) % len(available)]
    return TERRAIN_SPRITES.get(kind)

# Animacja: 3 klatki PNG, co 500 ms. Brakujace klatki -> oryginalny PNG.
ANIMATION_FRAME_MS = 500
ANIMATION_COUNT = 3
ANIMATED_BUILDINGS = ("PV", "WIND", "GAS", "BESS", "FACTORY")
BUILDING_SPRITES = {name: load_sprite(f"buildings/{name.lower()}.png")
                    for name in (*ANIMATED_BUILDINGS, "LINE")}
BUILDING_FRAMES = {}
for name in ANIMATED_BUILDINGS:
    frames = [load_sprite(f"buildings/{name.lower()}_{i}.png") for i in (1, 2, 3)]
    BUILDING_FRAMES[name] = [frame if frame is not None else BUILDING_SPRITES[name]
                             for frame in frames]

def animated_building_sprite(kind, frame_index):
    frames = BUILDING_FRAMES.get(kind)
    return frames[frame_index] if frames else BUILDING_SPRITES.get(kind)

# Kliki myszka w istniejace wiersze panelu. Rect nie jest rysowany.
def build_button_at(mouse_position):
    px = MAP_W + 18
    for i, key in enumerate(BUILD):
        yy = 167 + i * 31
        hitbox = pygame.Rect(px - 5, yy - 3, PANEL - 32, 29)
        if hitbox.collidepoint(mouse_position):
            return key
    return None

def night_alpha(sim_hour):
    """Ciemnosc: 20-22 zachod, 22-06 noc, 06-08 swit."""
    h = sim_hour % 24
    if 20 <= h < 22:
        return round(160 * (h - 20) / 2)
    if h >= 22 or h < 6:
        return 160
    if 6 <= h < 8:
        return round(160 * (8 - h) / 2)
    return 0

# Bufor warstwy nocy tworzony raz, zamiast alokacji 60 razy/s.
NIGHT_LAYER = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)


def blit_hex_sprite(sprite, position):
    if sprite is None:
        return False
    x, y = screen_center(*position)
    screen.blit(sprite, sprite.get_rect(center=(round(x), round(y))))
    return True

DIRECTIONS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))
rng = random.Random()

def center(q, r):
    return OX + math.sqrt(3)*R*(q+r/2), OY+1.5*R*r

def screen_center(q, r):
    x, y = center(q, r)
    return x - camera_x, y - camera_y

def hex_points(pos, radius=R+0.45):
    x, y = screen_center(*pos)
    return [(round(x+radius*math.cos(math.radians(60*k-30))),
             round(y+radius*math.sin(math.radians(60*k-30)))) for k in range(6)]

def cube_round(q, r):
    x, z, y = q, r, -q-r
    rx, ry, rz = round(x), round(y), round(z)
    dx, dy, dz = abs(rx-x), abs(ry-y), abs(rz-z)
    if dx > dy and dx > dz:
        rx = -ry-rz
    elif dy > dz:
        ry = -rx-rz
    else:
        rz = -rx-ry
    return rx, rz

def mouse_hex(mx, my):
    if not (0 <= mx < MAP_W and 0 <= my < MAP_H):
        return None
    px, py = mx+camera_x-OX, my+camera_y-OY
    pos = cube_round((math.sqrt(3)/3*px-py/3)/R, (2*py/3)/R)
    return pos if pos in terrain else None

def adjacent(pos):
    q, r = pos
    for dq, dr in DIRECTIONS:
        p = (q+dq, r+dr)
        if p in terrain:
            yield p

def generate_world():
    global terrain, world, city_tiles, city_groups, bess_energy, money, hour, day
    global score_green_hours, score_total_hours, game_finished
    score_green_hours = score_total_hours = 0
    game_finished = False
    terrain = {}
    # Losowe polozenie i rozmiar farmy przy kazdym generowaniu mapy.
    farm_cx = rng.uniform(WORLD_W * 0.22, WORLD_W * 0.78)
    farm_cy = rng.uniform(WORLD_H * 0.25, WORLD_H * 0.75)
    farm_rx = rng.uniform(2.1 * R, 3.4 * R)
    farm_ry = rng.uniform(1.8 * R, 2.9 * R)
    for q in range(-ROWS, COLS+ROWS):
        for r in range(-3, ROWS+3):
            x, y = center(q, r)
            if not (-R <= x <= WORLD_W+R and -R <= y <= WORLD_H+R):
                continue
            terrain[q, r] = 'farmland' if ((x-farm_cx)/farm_rx)**2 + ((y-farm_cy)/farm_ry)**2 < 1 else ('forest' if rng.random()<.085 else 'grass')
    world = {}
    city_tiles = set()
    city_groups = []
    candidates = [p for p, t in terrain.items() if t == 'grass' and
                  70 < center(*p)[0] < WORLD_W-70 and 65 < center(*p)[1] < WORLD_H-65]
    rng.shuffle(candidates)
    count = rng.randint(15, 20)
    for start in candidates:
        if len(city_groups) >= count:
            break
        if any(min(abs(center(*start)[0]-center(*p)[0]), 9999) < 155 and
               abs(center(*start)[1]-center(*p)[1]) < 155 for p in city_tiles):
            continue
        size = rng.randint(3, 4)
        cluster = [start]
        while len(cluster) < size:
            options = [n for p in cluster for n in adjacent(p)
                       if n not in cluster and n not in city_tiles and terrain[n] == 'grass'
                       and 55 < center(*n)[0] < WORLD_W-55 and 55 < center(*n)[1] < WORLD_H-55]
            if not options:
                break
            cluster.append(rng.choice(options))
        if len(cluster) != size:
            continue
        city_groups.append(cluster)
        city_tiles.update(cluster)
        for p in cluster:
            world[p] = 'CITY'
    bess_energy = {}
    money, hour, day = 6000., 0, 1
    reset_day()
    history.clear()
    make_weather()

def energized_components():
    """Topologia uproszczona: CITY przewodzi dalej, tak samo LINE i inne obiekty.

    Komponent jest aktywny, jesli zawiera co najmniej jeden odbiornik
    (CITY lub FACTORY) oraz zrodlo (PV/WIND/GAS lub naladowany BESS).
    Sam kabel przy miescie nie aktywuje jego poboru.
    """
    for group in networks():
        kinds = {world[p] for p in group}
        has_customer = bool(kinds & {'CITY', 'FACTORY'})
        has_source = bool(kinds & {'PV', 'WIND', 'GAS'}) or any(
            world[p] == 'BESS' and bess_energy.get(p, 0.) > 0 for p in group
        )
        if has_customer and has_source:
            yield group


def networks():
    groups, seen = [], set()
    for start in world:
        if start in seen:
            continue
        group, todo = [], deque([start])
        seen.add(start)
        while todo:
            p = todo.popleft()
            group.append(p)
            for n in adjacent(p):
                if n in world and n not in seen:
                    seen.add(n)
                    todo.append(n)
        groups.append(group)
    return groups

# Edmonds-Karp max-flow for a simplified transmission model. Each line hex
# has a 50 MW total throughput (node capacity), not 50 MW per outgoing edge.
def max_delivered(group, generation, demand):
    source, sink = ('S',), ('T',)
    capacity = {}
    def edge(a, b, amount):
        capacity[a, b] = capacity.get((a, b), 0.)+amount
        capacity.setdefault((b, a), 0.)
    for p in group:
        kind = world[p]
        limit = LINE_CAPACITY if kind == 'LINE' else 1e8
        edge((p, 'in'), (p, 'out'), limit)
        if generation.get(p, 0.) > 0:
            edge(source, (p, 'in'), generation[p])
        if demand.get(p, 0.) > 0:
            edge((p, 'out'), sink, demand[p])
        for n in adjacent(p):
            if n in world:
                edge((p, 'out'), (n, 'in'), 1e8)
    residual = dict(capacity)
    total = 0.
    while True:
        prev = {source: None}
        queue = deque([source])
        while queue and sink not in prev:
            u = queue.popleft()
            for (a, b), v in residual.items():
                if a == u and v > 1e-7 and b not in prev:
                    prev[b] = u
                    queue.append(b)
        if sink not in prev:
            break
        amount, node = float('inf'), sink
        while prev[node] is not None:
            parent = prev[node]
            amount = min(amount, residual[parent, node])
            node = parent
        node = sink
        while prev[node] is not None:
            parent = prev[node]
            residual[parent, node] -= amount
            residual[node, parent] += amount
            node = parent
        total += amount
    return total

BUY_PRICE = 5.0  # umowne jednostki / MWh
SELL_PRICE = 3.0
NEGATIVE_EXPORT_PRICE = -0.5
EXPORT_THRESHOLD_MW = 10.0
IMPORT_SCORE_LIMIT_MW = 10.0
GAME_DAYS = 30
score_green_hours = 0
score_total_hours = 0
game_finished = False
GAS_COST = 1.4
history = []
daily = {}
weather = []
CITY_DAILY_VARIATION = 0.05  # +/- 5% losowane raz na dobe, wspolne dla miast
city_daily_factor = 1.0
charge_start, discharge_start = 12, 18
BESS_POWER, BESS_CAPACITY = 20., 80.
BESS_EFF = math.sqrt(.90)

def make_weather():
    """Generate one coherent day; hourly wind has temporal persistence."""
    global weather, city_daily_factor
    city_daily_factor = rng.uniform(1.0 - CITY_DAILY_VARIATION, 1.0 + CITY_DAILY_VARIATION)
    peak = rng.uniform(450., 1000.)
    avg_wind = rng.uniform(4., 13.)
    wind = rng.uniform(3., 13.)
    weather = []
    for h in range(24):
        wind = max(0., min(25., .8*wind+.2*avg_wind+rng.gauss(0, 1.5)))
        solar = peak*max(0., math.sin(math.pi*(h-6)/12))
        weather.append((solar, wind))

def wind_capacity_factor(v):
    if v < 3 or v >= 25: return 0.
    if v >= 12: return 1.
    return (v**3-3**3)/(12**3-3**3)

def bess_window(h):
    # Two non-overlapping windows: charge until discharge begins, then discharge
    # until next charge begins (wraps around midnight).
    if charge_start == discharge_start: return 'idle'
    if charge_start < discharge_start:
        return 'charge' if charge_start <= h < discharge_start else 'discharge'
    return 'charge' if h >= charge_start or h < discharge_start else 'discharge'

def network_settings():
    """Okno ustawien BESS i dwuskladnikowej taryfy OSD."""
    import tkinter as tk
    from tkinter import messagebox
    global charge_start, discharge_start, DISTRIBUTION_FIXED_FEE, DISTRIBUTION_VARIABLE_FEE
    root = tk.Toplevel(charts_root) if charts_root is not None else tk.Tk()
    root.title('Energy Master — Ustawienia sieci')
    root.geometry('465x375')
    root.configure(bg='#f5efdb')
    tk.Label(root, text='USTAWIENIA SIECI', bg='#f5efdb', font=('Arial', 16, 'bold')).pack(pady=(13, 8))
    frame = tk.Frame(root, bg='#f5efdb'); frame.pack(padx=15, pady=4)
    labels = ['BESS — ladowanie od [h]:', 'BESS — rozladowanie od [h]:',
              'Oplata stala [coins/heks/dobe]:', 'Oplata zmienna [coins/MWh]:']
    for i, label in enumerate(labels):
        tk.Label(frame, text=label, bg='#f5efdb', anchor='w').grid(row=i, column=0, sticky='w', padx=6, pady=8)
    c, d = tk.IntVar(value=charge_start), tk.IntVar(value=discharge_start)
    fixed = tk.StringVar(value=f'{DISTRIBUTION_FIXED_FEE:g}')
    variable = tk.StringVar(value=f'{DISTRIBUTION_VARIABLE_FEE:g}')
    tk.Spinbox(frame, from_=0, to=23, textvariable=c, width=9).grid(row=0, column=1)
    tk.Spinbox(frame, from_=0, to=23, textvariable=d, width=9).grid(row=1, column=1)
    tk.Entry(frame, textvariable=fixed, width=11).grid(row=2, column=1)
    tk.Entry(frame, textvariable=variable, width=11).grid(row=3, column=1)
    message = tk.Label(root, text='Pobor reaguje na oplate zmienna (epsilon = 0.30).',
                       bg='#f5efdb', fg='#344c39', wraplength=430)
    message.pack(pady=9)
    def save():
        global charge_start, discharge_start, DISTRIBUTION_FIXED_FEE, DISTRIBUTION_VARIABLE_FEE
        try:
            a, b = int(c.get()), int(d.get())
            f = float(fixed.get().replace(',', '.'))
            v = float(variable.get().replace(',', '.'))
        except (ValueError, tk.TclError):
            message.config(text='Podaj poprawne wartosci liczbowe.', fg='#bb3333'); return
        if not (0 <= a < 24 and 0 <= b < 24) or a == b:
            message.config(text='Godziny BESS: 0-23, musza byc rozne.', fg='#bb3333'); return
        if not (math.isfinite(f) and math.isfinite(v) and 0 <= f <= 1000 and 0 <= v <= 1000):
            message.config(text='Oplaty musza byc w przedziale 0-1000.', fg='#bb3333'); return
        charge_start, discharge_start = a, b
        DISTRIBUTION_FIXED_FEE, DISTRIBUTION_VARIABLE_FEE = f, v
        root.destroy()
        simulate(0)  # aktualizuj profil popytu i SCADA bez rozliczania godziny
    tk.Button(root, text='Zapisz ustawienia', command=save,
              font=('Arial', 11, 'bold')).pack(pady=6)
    # Tk obslugiwany w istniejacej petli Pygame.


def economy_model_window():
    """EDIT HERE: standalone, editable explanation of the game economy.

    Change ECONOMY_DESCRIPTION below to edit the text and formulas.
    The window is non-blocking and shares the existing Tk event loop.
    """
    import tkinter as tk
    global paused, economy_window, economy_previous_pause
    # Otwieramy tylko jedno okno ekonomii; pauza wraca do stanu sprzed otwarcia.
    if economy_window is not None:
        try:
            if economy_window.winfo_exists():
                economy_window.lift()
                economy_window.focus_force()
                return
        except tk.TclError:
            economy_window = None
    economy_previous_pause = paused
    paused = True
    root = tk.Toplevel(charts_root) if charts_root is not None else tk.Tk()
    economy_window = root
    def close_economy():
        global paused, economy_window
        paused = economy_previous_pause
        economy_window = None
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', close_economy)
    root.title('Energy Master — model ekonomiczny')
    root.geometry('750x640')
    root.configure(bg='#f5efdb')

    # === POCZATEK EDYTOWALNEGO OPISU MODELU ===
    ECONOMY_DESCRIPTION = f"""ZASADY GRY I EKONOMIA — ENERGY MASTER ALPHA 1.6

1. BILANS MOCY (krok symulacji: 1 godzina)
   P_gen = P_PV + P_wiatr + P_gaz + P_BESS_oddanie
   P_pob = P_miasta + P_fabryki + P_BESS_ladowanie
   Saldo = P_gen - P_pob                 [MW]
   Energia = moc * 1 h                 [MWh]

2. POGODA I ZRODLA
   P_PV = 20 MWp * G / 1000 W/m2 (na farme)
   P_wiatr = 30 MW * CF(v) (na farme)
   Fabryka: 18 MW (06:00-22:00), 5 MW poza zmianami.
   Miasta: 6 MW/heks razy godzinowy profil popytu.
   W kazdej dobie losowany jest wspolczynnik k_d ~ U(0.95, 1.05).
   P_CITY(d,h) = 6 MW * profil(h) * k_d * wspolczynnik_taryfy.
   k_d jest staly przez 24 h i zmienia sie przy kolejnej dobie.
   Losowosc dotyczy CITY, a nie FACTORY; tylko aktywne miasta sa liczone.
   Pobor miast i fabryk zalezy od oplaty zmiennej:
   P(b) = P_bazowe * exp[-epsilon * (b - 1)]
   epsilon = {DEMAND_ELASTICITY:.2f}; b = oplata zmienna [coins/MWh].
   Przy b=1 popyt jest bazowy. Oplata stala nie zmienia popytu.
   Koszt budowy fabryki: 1000 coins.
   Kazda fabryka daje {FACTORY_DAILY_INCOME:.0f} coins za zakonczona dobe.
   Przychod naliczany jest raz na dobe, niezaleznie od zasilania.
   Gaz: stale 50 MW na kazde zrodlo, niezaleznie od poboru.
   Nadwyzka moze zostac wyeksportowana do sasiada.

3. BESS
   Moc: {BESS_POWER:.0f} MW, pojemnosc: {BESS_CAPACITY:.0f} MWh na magazyn
   Sprawnosc cyklu: 90%, eta_lad = eta_odd = sqrt(0.90)
   E_nowe = E_stare + eta_lad * P_lad * 1h
                     - P_odd * 1h / eta_odd
   0 <= E_nowe <= 80 MWh
   Ladowanie: {charge_start:02d}:00; rozladowanie: {discharge_start:02d}:00

4. SIEC I HANDEL Z SASIADEM
   ALPHA 1.6 — MECHANIKA PRZYLACZEN:
   Heksy CITY, LINE, PV, WIND, GAS, BESS i FACTORY tworza graf.
   Sasiadujace heksy obiektow sa polaczone; CITY przewodzi dalej.
   Aktywna podsiec musi zawierac odbiorce i zrodlo wytworcze
   (PV/WIND/GAS lub BESS z energia). Same linie nie wystarczaja.
   Tylko aktywne podsieci wchodza do bilansu, wykresow i SCADA.
   Odizolowane miasta nie generuja poboru ani oplat OSD.
   Odizolowane zrodla nie generuja mocy ani kosztu paliwa.
   Przylaczenie nie oznacza pelnego pokrycia zapotrzebowania.
   Import pozostaje uproszczonym bilansem zewnetrznym bez EXT.
   Przepustowosc polaczenia: {LINE_CAPACITY:.0f} MW.
   Dostawa lokalna: maksymalny przeplyw w uproszczonej sieci.
   Eksport = max(0, generacja - dostawa_lokalna)
   Import = max(0, pobor - dostawa_lokalna)
   Import i eksport moga wystepowac jednoczesnie,
   gdy siec lokalna jest ograniczona lub podzielona.
   Nie modelujemy fizycznego punktu wymiany ani rozpływow AC.

5. TARYFA DYSTRYBUCYJNA OSD (waluta: coins)
   Oplata stala a = {DISTRIBUTION_FIXED_FEE:.2f} coins/heks/dobe
   Oplata zmienna b = {DISTRIBUTION_VARIABLE_FEE:.2f} coins/MWh
   N = liczba heksow CITY + FACTORY w aktywnych podsieciach.
   E = energia pobrana przez przylaczone CITY + FACTORY [MWh], bez BESS.
   Przychod OSD = a * N + b * E.
   Skladnik staly naliczamy raz na koniec doby,
   zmienny w kazdej godzinie (takze dla importowanej energii).
   Koszt utrzymania sieci = {LINE_MAINTENANCE_DAILY:.0f} coins * liczba heksow LINE / dobe.
   Naliczenie raz na koniec doby, za istniejace heksy LINE.
   Nie naliczamy tego kosztu za CITY, budynki ani za same polaczenia.
   Liczba przylaczen nie zalezy od oplaty stalej.

6. CENY I FINANSE (waluta: coins)
   Cena importu: {BUY_PRICE:.1f} coins/MWh
   Cena eksportu do {EXPORT_THRESHOLD_MW:g} MW wlacznie: +{SELL_PRICE:.1f} coins/MWh
   Cena eksportu powyzej {EXPORT_THRESHOLD_MW:g} MW: {NEGATIVE_EXPORT_PRICE:.1f} coins/MWh
   Po przekroczeniu progu ujemna cena dotyczy CALEGO eksportu
   w danej godzinie, a nie tylko nadwyzki ponad prog.
   Koszt gazu: {GAS_COST:.1f} coins/MWh
   Przychod = eksport_MWh * cena_eksportu
   Koszt = import_MWh * cena_importu + gaz_MWh * koszt_gazu
           + liczba_heksow_LINE * {LINE_MAINTENANCE_DAILY:.0f} coins/dobe
   Wplywy z fabryk = liczba_fabryk * {FACTORY_DAILY_INCOME:.0f} coins/dobe
   Wynik doby = eksport + OSD + fabryki - koszty - inwestycje + zwroty
   Saldo konta = saldo poprzednie + wynik doby
   Mozna inwestowac takze przy ujemnym stanie konta.

7. SCORE — WARUNEK ZWYCIESTWA
   Rozgrywka trwa {GAME_DAYS} dob (720 godzin symulacji).
   Zielona godzina: saldo mocy calej sieci jest w przedziale
   (-10 MW, +10 MW), bez wartosci granicznych.
   Saldo = generacja (PV + FW + GAZ + rozladowanie BESS)
           - zapotrzebowanie (miasta + fabryki + ladowanie BESS).
   Import i eksport nie sa osobnymi warunkami punktacji.
   Score = 100 * liczba zielonych godzin / liczba godzin gry [%].
   Godziny liczymy od pierwszej godziny pierwszej doby.
   Po dobie {GAME_DAYS} gra konczy sie raportem wyniku.
   Budzet pozostaje osobnym wynikiem ekonomicznym.

UWAGA: To uproszczony model gry, nie model rynku rzeczywistego.
"""
    # === KONIEC EDYTOWALNEGO OPISU MODELU ===
    tk.Label(root, text='MODEL EKONOMII I BILANSOWANIA', bg='#f5efdb',
             fg='#263646', font=('Arial', 15, 'bold')).pack(pady=(12, 5))
    area = tk.Frame(root, bg='#f5efdb')
    area.pack(fill='both', expand=True, padx=16, pady=8)
    scroll = tk.Scrollbar(area)
    scroll.pack(side='right', fill='y')
    content = tk.Text(area, wrap='word', font=('Consolas', 11), bg='#fffaf0',
                      fg='#263646', padx=14, pady=12, yscrollcommand=scroll.set)
    content.pack(side='left', fill='both', expand=True)
    scroll.config(command=content.yview)
    content.insert('1.0', ECONOMY_DESCRIPTION)
    content.config(state='disabled')
    tk.Button(root, text='Zamknij', command=close_economy,
              font=('Arial', 11, 'bold')).pack(pady=(0, 12))


def reset_day():
    global daily
    daily = dict(investments=0., refunds=0., generation=0., demand=0.,
                 supplied=0., export=0., imports=0., sale=0., purchase=0., fuel=0.,
                 bess_charge=0., bess_discharge=0., bess_losses=0., factory_income=0., distribution_fixed=0.,
                 distribution_variable=0., distribution_energy=0., line_maintenance=0.)


def draw_budget_chart(canvas, points, width=490, height=175):
    """Rysuje historie salda od poczatku rozgrywki, z ujemnymi wartosciami."""
    canvas.delete('all')
    left, right, top, bottom = 68, width - 18, 15, height - 35
    values = [value for _, value in points]
    lo, hi = min(0., *values), max(0., *values)
    padding = max(1., (hi - lo) * .10)
    lo -= padding
    hi += padding
    def yy(value):
        return bottom - (value - lo) / (hi - lo) * (bottom - top)
    def xx(index):
        return left + (index / max(1, len(points) - 1)) * (right - left)
    canvas.create_line(left, top, left, bottom, right, bottom, fill='#687985')
    if lo < 0 < hi:
        z = yy(0)
        canvas.create_line(left, z, right, z, fill='#c17b7b', dash=(4, 4))
    for i in range(5):
        value = lo + (hi - lo) * i / 4
        y = yy(value)
        canvas.create_text(left - 6, y, text=f'{value:,.0f}', anchor='e',
                           font=('Arial', 8), fill='#263646')
    coords = []
    for index, (_, value) in enumerate(points):
        coords.extend((xx(index), yy(value)))
    if len(coords) >= 4:
        canvas.create_line(*coords, fill='#2679ad', width=2, smooth=False)
    for index, (day_number, value) in enumerate(points):
        if index in (0, len(points) - 1) or (len(points) <= 12 or index % max(1, len(points)//8) == 0):
            canvas.create_text(xx(index), bottom + 12, text=str(day_number),
                               font=('Arial', 8), fill='#263646')
    if coords:
        x, y = coords[-2:]
        canvas.create_oval(x-3, y-3, x+3, y+3, fill='#2679ad', outline='')
    canvas.create_text((left+right)/2, height-7, text='Dzien gry',
                       font=('Arial', 9), fill='#263646')

report_open = False
show_daily_report = True  # Opcja gracza: raport po kazdej dobie
economy_window = None
economy_previous_pause = False

def advance_to_next_day():
    """Przejscie do nastepnej doby bez otwierania okna raportu."""
    global day, elapsed
    if day >= GAME_DAYS:
        return
    day += 1
    reset_day()
    history.clear()
    make_weather()
    elapsed = 0.
    simulate(0)
    update_charts()

def draw_final_series(parent, title, series, unit, colors, width=616, height=132, legend_bottom_right=False):
    """Trzy wykresy bez matplotlib: tylko Tkinter Canvas."""
    import tkinter as tk
    tk.Label(parent, text=title, bg='#17283a', fg='#f3cf77',
             font=('Arial', 10, 'bold'), anchor='w').pack(fill='x', pady=(5, 2))
    canvas = tk.Canvas(parent, width=width, height=height, bg='#20364a',
                       highlightthickness=0)
    canvas.pack(fill='x')
    left, right, top, bottom = 73, width-17, 12, height-27
    values = [v for _, points in series for _, v in points]
    lo, hi = (min(values), max(values)) if values else (0., 1.)
    if unit == '%':
        lo, hi = 0.0, max(1.0, min(100.0, hi * 1.20))
    else:
        lo = min(0., lo)
        if hi <= lo: hi = lo + 1.
        margin = max(1., (hi-lo)*.08)
        lo -= margin; hi += margin
    def xx(day_number): return left+(day_number-1)/max(1,GAME_DAYS-1)*(right-left)
    def yy(value): return bottom-(value-lo)/(hi-lo)*(bottom-top)
    for i in range(5):
        v=lo+(hi-lo)*i/4
        y=yy(v)
        canvas.create_line(left,y,right,y,fill='#3a5368')
        canvas.create_text(left-7,y,text=(f'{v:.0f}%' if unit == '%' else f'{v:,.0f}'),fill='#d6e2eb',
                           anchor='e',font=('Consolas',8))
    for d in (1,5,10,15,20,25,30):
        canvas.create_text(xx(d),bottom+13,text=str(d),fill='#c2d1de',font=('Arial',8))
    for i,(name,points) in enumerate(series):
        coords=[]
        for d,v in points: coords.extend((xx(d),yy(v)))
        if len(coords)>=4:canvas.create_line(*coords,fill=colors[i],width=2.5)
        elif len(coords)==2:
            x,y=coords;canvas.create_oval(x-3,y-3,x+3,y+3,fill=colors[i],outline='')
        if not legend_bottom_right:
            canvas.create_text(right-8,top+14*i,text=name,fill=colors[i],
                               anchor='ne',font=('Arial',8,'bold'))
    if legend_bottom_right:
        # Legenda w prawym dolnym rogu obszaru wykresu.
        legend_x = right - 145
        legend_y = bottom - 32
        canvas.create_rectangle(legend_x-8, legend_y-6, right-2, bottom-1,
                                fill='#20364a', outline='#526477')
        for i, (name, _) in enumerate(series):
            y = legend_y + i*15
            canvas.create_line(legend_x, y+4, legend_x+18, y+4, fill=colors[i], width=3)
            canvas.create_text(legend_x+23, y+4, text=name, fill='#e3edf5',
                               anchor='w', font=('Arial',8))
    canvas.create_text(left+3,top+2,text=unit,fill='#b6c7d7',anchor='nw',font=('Arial',8))


def show_final_report():
    """Zwarty raport koncowy; eksport danych do czytelnego pliku TXT."""
    import tkinter as tk
    from tkinter import messagebox
    from datetime import datetime
    import getpass
    import re
    import sys
    global report_open, final_report_window
    if final_report_window is not None:
        try:
            if final_report_window.winfo_exists():
                final_report_window.lift()
                return
        except tk.TclError:
            pass
    report_open = True
    root = tk.Toplevel(charts_root) if charts_root is not None else tk.Tk()
    final_report_window = root
    root.title('Energy Master Alpha 1.6 — raport koncowy / 30 dni')
    root.geometry('730x795')
    root.resizable(False, False)
    root.configure(bg='#111e2b')
    content = tk.Frame(root, bg='#17283a', padx=15, pady=8)
    content.pack(fill='both', expand=True)

    tk.Label(content, text='ENERGY MASTER  |  RAPORT KONCOWY', bg='#17283a',
             fg='#f3cf77', font=('Arial', 16, 'bold')).pack(pady=(0, 3))
    tk.Label(content,
             text=f'30 DNI  /  BUDZET: {money:,.1f} coins  /  '
                  f'SCORE: {100*score_green_hours/max(1,score_total_hours):.1f}% '
                  f'({score_green_hours}/{score_total_hours} h)',
             bg='#17283a', fg='#dce8f1', font=('Consolas', 10, 'bold')).pack(pady=(0, 3))

    days = final_day_history
    draw_final_series(content, '1. Budzet w czasie',
                      [('Coins', [(d,m) for d,m,_,_,_,_ in days])],
                      'coins', ['#f3cf77'])
    draw_final_series(content, '2. SCORE — procent godzin zbilansowanych',
                      [('SCORE %', [(d, 100.0*good/total if total else 0.0)
                                    for d,_,good,total,_,_ in days])],
                      '%', ['#74dba7'])
    draw_final_series(content, '3. Dobowa generacja i zapotrzebowanie',
                      [('Generacja', [(d,g) for d,_,_,_,g,_ in days]),
                       ('Zapotrzebowanie', [(d,z) for d,_,_,_,_,z in days])],
                      'MWh', ['#78c6f2','#f1b66c'], legend_bottom_right=True)

    counts = {kind: sum(v == kind for v in world.values())
              for kind in ('PV','WIND','GAS','BESS','FACTORY','LINE')}
    simulate(0)  # tylko odswiezenie topologii, bez naliczania energii
    rows = [('PV', counts['PV']), ('WIND', counts['WIND']),
            ('GAS', counts['GAS']), ('BESS', counts['BESS']),
            ('FACTORY', counts['FACTORY']), ('LINE (heksy)', counts['LINE']),
            ('CITY przylaczone (heksy)', connected_city_count),
            ('CITY wszystkie (heksy)', len(city_tiles))]
    tk.Label(content, text='INFRASTRUKTURA — STAN KONCOWY', bg='#17283a',
             fg='#f3cf77', font=('Arial', 10, 'bold')).pack(pady=(8, 3))
    table = tk.Frame(content, bg='#20364a')
    table.pack(fill='x', padx=28)
    for i, (name, number) in enumerate(rows):
        bg = '#20364a' if i % 2 == 0 else '#294057'
        tk.Label(table, text=name, bg=bg, fg='#e3ecf3', anchor='w',
                 font=('Consolas', 9), padx=12).grid(row=i, column=0, sticky='ew')
        tk.Label(table, text=str(number), bg=bg, fg='#f3cf77', anchor='e',
                 font=('Consolas', 9, 'bold'), padx=12).grid(row=i, column=1, sticky='ew')
    table.grid_columnconfigure(0, weight=1)
    table.grid_columnconfigure(1, minsize=95)

    status = tk.Label(content, text='', bg='#17283a', fg='#9fdfbc',
                      font=('Arial', 9))
    status.pack(pady=(3, 0))

    def save_report():
        """Eksport pelnych 30 dni oraz stanu infrastruktury; bez Pillow i DPI."""
        from datetime import datetime
        import getpass
        import re
        import sys
        from tkinter import messagebox

        # Obok EXE w PyInstaller -F; obok pliku .py przy normalnym uruchomieniu.
        base_dir = (Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False)
                    else Path(__file__).resolve().parent)
        username = re.sub(r'[^A-Za-z0-9_-]+', '_', getpass.getuser()).strip('_') or 'user'
        stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = base_dir / f'Energy_Master_raport_{username}_{stamp}.txt'

        lines = [
            'ENERGY MASTER - RAPORT KONCOWY',
            '=' * 83,
            f'Uzytkownik Windows: {getpass.getuser()}',
            f'Data zapisu: {datetime.now():%Y-%m-%d %H:%M:%S}',
            f'Czas gry: {GAME_DAYS} dni',
            f'Budzet koncowy: {money:.2f} coins',
            f'SCORE koncowy: {100.0 * score_green_hours / score_total_hours if score_total_hours else 0.0:.2f}%'
            f' ({score_green_hours}/{score_total_hours} godzin)',
            '',
            'WYNIKI DOBOWE',
            '-' * 83,
            f'{"Dzien":>5} | {"Coins":>15} | {"SCORE [%]":>11} | {"Pobor [MWh]":>15} | {"Generacja [MWh]":>17}',
            '-' * 83,
        ]
        for d, coins, good, total, generation, demand in days:
            score_pct = 100.0 * good / total if total else 0.0
            lines.append(f'{d:5d} | {coins:15.2f} | {score_pct:11.2f} | '
                         f'{demand:15.2f} | {generation:17.2f}')

        lines.extend([
            '-' * 83,
            'SCORE [%] = skumulowany odsetek godzin zbilansowanych do konca danej doby.',
            'Pobor i generacja: energia w danej dobie (MWh), nie wartosci skumulowane.',
            '',
            'INFRASTRUKTURA - STAN NA KONIEC ROZGRYWKI',
            '-' * 48,
            f'{"Typ":<35} | {"Liczba":>8}',
            '-' * 48,
        ])
        for name, number in rows:
            lines.append(f'{name:<35} | {number:8d}')
        lines.extend(['-' * 48, ''])

        try:
            filename.write_text('\n'.join(lines), encoding='utf-8-sig')
            status.config(text=f'Zapisano: {filename.name}', fg='#9fdfbc')
        except OSError as exc:
            messagebox.showerror('Nie mozna zapisac TXT', str(exc), parent=root)

    def close():
        global report_open, final_report_window
        report_open = False
        final_report_window = None
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', close)
    buttons = tk.Frame(content, bg='#17283a')
    buttons.pack(pady=(5, 2))
    tk.Button(buttons, text='Zapisz raport (TXT)', command=save_report,
              font=('Arial', 10, 'bold'), bg='#74dba7', fg='#17283a').pack(side='left', padx=7, ipady=4)
    tk.Button(buttons, text='Zamknij', command=close,
              font=('Arial', 10, 'bold'), bg='#f3cf77', fg='#17283a').pack(side='left', padx=7, ipady=4)


def daily_report():
    # Oddzielne okno systemowe. Zamkniecie wznawia gre.
    import tkinter as tk
    global report_open
    report_open = True
    root = tk.Toplevel(charts_root) if charts_root is not None else tk.Tk()
    root.title(f'Energy Master — raport dobowy {day}')
    root.geometry('555x900')
    root.configure(bg='#f5efdb')
    report = [
        f'RAPORT DOBOWY — DZIEŃ {day}/{GAME_DAYS}', '',
        f'SCORE: {100*score_green_hours/max(1,score_total_hours):.2f}%  ({score_green_hours}/{score_total_hours} h)', '',
        f'Inwestycje:                 -{daily["investments"]:,.1f} coins',
        f'Zwroty z rozbiorek:         +{daily["refunds"]:,.1f} coins', '',
        f'Miasta podlaczone (heksy):  {connected_city_count}/{len(city_tiles)}',
        f'Generacja (bez BESS):       {daily["generation"]:,.1f} MWh',
        f'Pobor netto (z BESS):       {daily["demand"]:,.1f} MWh',
        f'Energia dostarczona lokalnie:{daily["supplied"]:,.1f} MWh',
        f'Oddanie (eksport):          {daily["export"]:,.1f} MWh',
        f'Kupno (import):             {daily["imports"]:,.1f} MWh', '',
        f'Wynik eksportu:            {daily["sale"]:+,.1f} coins',
        f'Kupno od sąsiada:          -{daily["purchase"]:,.1f} coins',
        f'Koszt paliwa (gaz):        -{daily["fuel"]:,.1f} coins', '',
        f'BESS ladowanie:             {daily["bess_charge"]:,.1f} MWh',
        f'BESS oddanie:               {daily["bess_discharge"]:,.1f} MWh',
        f'BESS straty:                {daily["bess_losses"]:,.1f} MWh',
        f'BESS SoC na koniec:         {sum(bess_energy.values()):,.1f} MWh',
        f'Wplywy z fabryk:           +{daily["factory_income"]:,.1f} coins',
        f'OSD oplata stala:          +{daily["distribution_fixed"]:,.1f} coins',
        f'OSD oplata zmienna:        +{daily["distribution_variable"]:,.1f} coins',
        f'OSD energia rozliczona:     {daily["distribution_energy"]:,.1f} MWh',
        f'Utrzymanie linii (LINE):    -{daily["line_maintenance"]:,.1f} coins', '',
        f'WYNIK DOBY: {daily["sale"] - daily["purchase"] - daily["fuel"] - daily["investments"] + daily["refunds"] + daily["factory_income"] + daily["distribution_fixed"] + daily["distribution_variable"] - daily["line_maintenance"]:+,.1f} coins',
        f'STAN KONTA: {money:,.1f} coins', '',
        'Waluta: coins; 1 krok = 1 godzina.',
        'Import/eksport: uproszczony rynek zewnętrzny.',
    ]
    tk.Label(root, text='\n'.join(report), justify='left', anchor='nw',
             bg='#f5efdb', fg='#263646', font=('Consolas', 11),
             padx=20, pady=12).pack(fill='x')
    tk.Label(root, text='HISTORIA BUDZETU — od poczatku gry [coins]',
             bg='#f5efdb', fg='#263646', font=('Arial', 11, 'bold')).pack(pady=(4, 2))
    chart = tk.Canvas(root, width=490, height=175, bg='#fffaf0',
                      highlightthickness=1, highlightbackground='#d6cdb8')
    chart.pack(padx=15, pady=(0, 4))
    draw_budget_chart(chart, budget_history)
    def next_day():
        global report_open
        report_open = False
        root.destroy()
        advance_to_next_day()
    if day >= GAME_DAYS:
        tk.Label(root, text=f'KONIEC GRY — WYNIK: {100*score_green_hours/max(1,score_total_hours):.2f}%',
                 font=('Arial', 14, 'bold'), bg='#f5efdb', fg='#263646').pack(pady=10)
        def close_final():
            global report_open
            report_open = False
            root.destroy()
        root.protocol('WM_DELETE_WINDOW', close_final)
        tk.Button(root, text='Zamknij — koniec gry', command=close_final,
                  font=('Arial', 12, 'bold')).pack(pady=8)
    else:
        root.protocol('WM_DELETE_WINDOW', next_day)
        tk.Button(root, text='Kolejna doba  →', font=('Arial', 12, 'bold'),
                  command=next_day).pack(pady=8)
    # Nie wywolujemy mainloop(): to blokowalo synchronizacje z Pygame.


generate_world()
# Start kamery przy pierwszym miescie, aby od razu bylo co ogladac.
if city_groups:
    sx, sy = center(*city_groups[0][0])
    camera_x = max(0., min(sx - MAP_W/2, WORLD_W - MAP_W))
    camera_y = max(0., min(sy - MAP_H/2, WORLD_H - MAP_H))
# Historia salda: inicjalizacja dopiero po ustawieniu money w generate_world().
budget_history = [(0, money)]
final_day_history = []  # (dzien, coins, score_h, score_total_h, generacja_MWh, pobor_MWh)
final_report_window = None
selected, speed, paused, elapsed = '6', 1, False, 0.
REPORT_CHECKBOX = pygame.Rect(MAP_W + 18, 386, 23, 23)
notice = 'Miasta wygenerowane. Polacz je liniami z elektrowniami!'
stats = (0., 0., 0., 0., 0., 0.)
served = 0.
connected = set()
network_count = 0
connected_city_count = 0
connected_factory_count = 0
scada_data = {}

def factory_demand(hour):
    """Fabryka dwuzmianowa: 18 MW od 06:00 do 21:59, poza zmianami 5 MW."""
    return 18.0 if 6 <= hour < 22 else 5.0


def simulate(hours):
    global money, stats, served, connected, network_count, scada_data
    global connected_city_count, connected_factory_count
    global score_green_hours, score_total_hours
    connected = set()
    soc_before = sum(bess_energy.values())
    groups = list(energized_components())
    network_count = len(groups)
    connected = {p for group in groups for p in group}
    connected_city_count = sum(world[p] == 'CITY' for p in connected)
    connected_factory_count = sum(world[p] == 'FACTORY' for p in connected)
    irradiance, wind_speed = weather[hour]
    pv_factor = irradiance/1000.
    wind_factor = wind_capacity_factor(wind_speed)
    demand_factor = .65+.35*(.5+.5*math.cos((hour-19)*math.pi/12))
    # Cena zmienna zmienia popyt. Domyslne b=1 daje mnoznik 1.
    tariff_factor = math.exp(-DEMAND_ELASTICITY * (DISTRIBUTION_VARIABLE_FEE - 1.0))
    totals = defaultdict(float)
    for group in groups:
        pv = {p:20*pv_factor for p in group if world[p]=='PV'}
        wind = {p:30*wind_factor for p in group if world[p]=='WIND'}
        loads = {p: (6.0 * demand_factor * city_daily_factor if world[p] == 'CITY' else factory_demand(hour)) * tariff_factor
                 for p in group if world[p] in ('CITY', 'FACTORY')}
        gas_sites = [p for p in group if world[p]=='GAS']
        bess_sites = [p for p in group if world[p]=='BESS']
        total_demand = sum(loads.values())
        renewable = sum(pv.values())+sum(wind.values())
        # BESS operates on a player-defined schedule. Charge is a grid load,
        # discharge is generation. SOC is changed ONLY on hourly settlement.
        mode = bess_window(hour)
        bess_charge, bess_out = {}, {}
        for p in bess_sites:
            soc = bess_energy.get(p, 0.)
            if mode == 'charge':
                bess_charge[p] = min(BESS_POWER, (BESS_CAPACITY-soc)/BESS_EFF)
            elif mode == 'discharge':
                bess_out[p] = min(BESS_POWER, soc*BESS_EFF)
        for p, v in bess_charge.items(): loads[p] = v
        total_demand = sum(loads.values())
        gas = 50.0 * len(gas_sites)  # stale 50 MW na kazda gazowke
        sources = dict(pv)
        sources.update(wind)
        sources.update(bess_out)
        for p in gas_sites:
            sources[p] = gas/len(gas_sites)
        delivered = max_delivered(group, sources, loads) if loads and sources else 0.
        # Rynek zewnetrzny jest abstrakcyjnym bilansem systemowym:
        # nie modelujemy fizycznego punktu przylaczenia ani rozpływu importu.
        generation = renewable+gas+sum(bess_out.values())
        totals['bess_charge'] += sum(bess_charge.values())
        totals['bess_discharge'] += sum(bess_out.values())
        if hours:
            for p, v in bess_charge.items():
                bess_energy[p] = min(BESS_CAPACITY, bess_energy[p]+v*BESS_EFF*hours)
            for p, v in bess_out.items():
                bess_energy[p] = max(0., bess_energy[p]-v/BESS_EFF*hours)
        export = max(0., generation-delivered)
        imports = max(0., total_demand-delivered)
        totals['pv'] += sum(pv.values())
        totals['wind'] += sum(wind.values())
        totals['gas'] += gas
        totals['bess_power'] += sum(bess_out.values())-sum(bess_charge.values())
        totals['city'] += sum(value for pos, value in loads.items() if world[pos] == 'CITY')
        totals['factory'] += sum(value for pos, value in loads.items() if world[pos] == 'FACTORY')
        totals['demand'] += total_demand
        totals['delivered'] += delivered
        totals['export'] += export
        totals['imports'] += imports
    served = totals['delivered']
    # BESS jest odbiornikiem o mocy ze znakiem: ladowanie (+), oddawanie (-).
    # Generacja bez BESS; zapotrzebowanie netto zawiera oba kierunki pracy BESS.
    generation = totals['pv'] + totals['wind'] + totals['gas']
    net_demand = totals['demand'] - totals['bess_discharge']
    system_balance = generation - net_demand
    stats = (totals['pv'], totals['wind'], totals['gas'], totals['bess_power'],
             net_demand, system_balance)
    # Snapshot do SCADA: MW, nie energia dobowa [MWh].
    # EXT dodatni = eksport, ujemny = import (oddzielnie pokazujemy oba kierunki).
    scada_data = dict(pv=totals['pv'], fw=totals['wind'], gaz=totals['gas'],
                      bess=totals['bess_power'], city=totals['city'],
                      factory=totals['factory'], export=totals['export'],
                      imports=totals['imports'], generation=generation,
                      demand=net_demand, delivered=totals['delivered'],
                      balance=system_balance, connected_cities=connected_city_count,
                      disconnected_cities=len(city_tiles)-connected_city_count)
    update_scada()
    if hours:
        # Kazdy krok godzinowy jest rozliczany dokladnie raz.
        score_total_hours += 1
        # Punktacja dotyczy bilansu CALEJ sieci (jak na SCADA),
        # a nie osobnych przeplywow importu/eksportu w podsieciach.
        system_balance_mw = system_balance
        if connected_city_count > 0 and -10.0 < system_balance_mw < 10.0:
            score_green_hours += 1
        export_price = (NEGATIVE_EXPORT_PRICE if totals['export'] > EXPORT_THRESHOLD_MW
                        else SELL_PRICE)
        sale = totals['export'] * export_price * hours
        purchase = totals['imports']*BUY_PRICE*hours
        fuel = totals['gas']*GAS_COST*hours
        # OSD pobiera skladnik zmienny od zuzycia miast i fabryk, nie od BESS.
        distribution_energy = (totals['city'] + totals['factory']) * hours
        distribution_variable = DISTRIBUTION_VARIABLE_FEE * distribution_energy
        money += sale-purchase-fuel+distribution_variable
        daily['distribution_energy'] += distribution_energy
        daily['distribution_variable'] += distribution_variable
        daily['generation'] += generation*hours
        daily['demand'] += net_demand*hours
        daily['supplied'] += totals['delivered']*hours
        daily['export'] += totals['export']*hours
        daily['imports'] += totals['imports']*hours
        daily['sale'] += sale
        daily['purchase'] += purchase
        daily['fuel'] += fuel
        daily['bess_charge'] += totals['bess_charge']*hours
        daily['bess_discharge'] += totals['bess_discharge']*hours
        daily['bess_losses'] += (totals['bess_charge']-totals['bess_discharge'])*hours - (sum(bess_energy.values())-soc_before)
        history.append((hour, net_demand, generation))

# Osobne okno wykresow (Tkinter); Pygame zachowuje pelna powierzchnie mapy.
# Okno mozna zamknac i ponownie otworzyc klawiszem W.
charts_root = None
charts_canvas = None

def open_charts():
    global charts_root, charts_canvas
    import tkinter as tk
    if charts_root is not None:
        try:
            charts_root.lift()
            return
        except tk.TclError:
            charts_root = None
    charts_root = tk.Tk()
    charts_root.title('Energy Master — wykresy i prognoza pogody')
    charts_root.geometry('555x318')
    charts_root.configure(bg='#1e2c39')
    charts_canvas = tk.Canvas(charts_root, width=531, height=294,
                              bg='#1e2c39', highlightthickness=0)
    charts_canvas.pack(fill='both', expand=True, padx=10, pady=10)
    def close_charts():
        global charts_root, charts_canvas, scada_window, scada_canvas
        scada_window, scada_canvas = None, None
        charts_root.destroy()
        charts_root, charts_canvas = None, None
    charts_root.protocol('WM_DELETE_WINDOW', close_charts)
    update_charts()

def update_charts():
    if charts_root is None or charts_canvas is None:
        return
    import tkinter as tk
    c = charts_canvas
    try:
        c.delete('all')
        w = max(560, c.winfo_width())
        h = max(270, c.winfo_height())
        panels = [(8, 16, w-8, h//2-5), (8, h//2+9, w-8, h-7)]
        for x0,y0,x1,y1 in panels:
            c.create_rectangle(x0,y0,x1,y1,fill='#26394b',outline='#526477',width=1)
        c.create_text(18, 28, text='POBOR NETTO / GENERACJA [MW]',
                      fill='#efd679', anchor='nw', font=('Arial',10,'bold'))
        c.create_text(18,h//2+21,text='PROGNOZA POGODY NA CALA DOBE',
                      fill='#efd679',anchor='nw',font=('Arial',10,'bold'))
        def axes(rect, maximum, right_scale=None):
            x0,y0,x1,y1=rect
            left,right=x0+45,x1-42
            top,bottom=y0+29,y1-23
            for f in (0,.5,1):
                yy=bottom-f*(bottom-top)
                c.create_line(left,yy,right,yy,fill='#485d6f')
                c.create_text(left-10,yy,text=f'{maximum*f:.0f}',anchor='e',fill='#aabecb',font=('Arial',8))
                if right_scale is not None:
                    c.create_text(right+10,yy,text=f'{right_scale*f:.0f}',anchor='w',fill='#7fcaf1',font=('Arial',8))
            for hh in (0,6,12,18,23):
                xx=left+(right-left)*hh/23
                c.create_text(xx,bottom+14,text=f'{hh:02d}',fill='#aabecb',font=('Arial',8))
            return left,right,top,bottom
        def curve(series,color,scale,box):
            left,right,top,bottom=box
            pts=[]
            for hh,val in series:
                pts.extend((left+(right-left)*hh/23,bottom-max(0.,val)/max(scale,1e-6)*(bottom-top)))
            if len(pts)>=4: c.create_line(*pts,fill=color,width=3,smooth=False)
            elif len(pts)==2: c.create_oval(pts[0]-3,pts[1]-3,pts[0]+3,pts[1]+3,fill=color,outline='')
        max_power=max([10.]+[max(d,g) for _,d,g in history])*1.12
        b1=axes(panels[0],max_power)
        curve([(hh,d) for hh,d,g in history],'#ff9d74',max_power,b1)
        curve([(hh,g) for hh,d,g in history],'#67d9aa',max_power,b1)
        c.create_text(w-236,28,text='Pobor',fill='#ff9d74',anchor='nw',font=('Arial',10))
        c.create_text(w-166,28,text='Generacja',fill='#67d9aa',anchor='nw',font=('Arial',10))
        b2=axes(panels[1],1000.,25.)
        # Prognoza pogody: wszystkie 24 godziny sa widoczne od poczatku doby.
        curve([(hh,weather[hh][0]) for hh in range(24)],'#f4c958',1000.,b2)
        curve([(hh,weather[hh][1]) for hh in range(24)],'#7fcaf1',25.,b2)
        c.create_text(w-170,h//2+21,text='G [W/m2]',fill='#f4c958',anchor='nw',font=('Arial',10))
        c.create_text(w-86,h//2+21,text='Wiatr [m/s]',fill='#7fcaf1',anchor='nw',font=('Arial',10))
        # Wskaznik czasu to pionowa linia: przesuwa sie po osi godzin.
        xx=b2[0]+(b2[1]-b2[0])*hour/23
        c.create_line(xx,b2[2],xx,b2[3],fill='#ffffff',width=2,dash=(5,3))
        c.create_text(xx,b2[2]+6,text=f'{hour:02d}:00',fill='#ffffff',font=('Arial',8,'bold'))
        c.create_text(w//2,8,text=f'DZIEN {day}  |  AKTUALNA GODZINA {hour:02d}:00',
                      fill='#d9e7ef',font=('Arial',10,'bold'))
        charts_root.update_idletasks()
    except tk.TclError:
        pass

# SCADA: trzecie okno, schemat jednokreskowy ZBIORCZY (nie rozpływy mocy).
# Toplevel pod tym samym korzeniem Tk co wykresy; brak drugiego mainloop().
scada_window = None
scada_canvas = None

def open_scada():
    global scada_window, scada_canvas
    import tkinter as tk
    if charts_root is None:
        open_charts()
    if scada_window is not None:
        try:
            if scada_window.winfo_exists():
                scada_window.lift()
                return
        except tk.TclError:
            pass
    scada_window = tk.Toplevel(charts_root)
    scada_window.title('Energy Master — SCADA / schemat zbiorczy')
    scada_window.geometry('555x383')
    scada_window.configure(bg='#111e2b')
    scada_canvas = tk.Canvas(scada_window, bg='#111e2b', highlightthickness=0,
                             width=535, height=363)
    scada_canvas.pack(fill='both', expand=True, padx=10, pady=10)
    scada_canvas.bind('<Configure>', lambda _event: update_scada())
    def close_scada():
        global scada_window, scada_canvas
        scada_window.destroy()
        scada_window, scada_canvas = None, None
    scada_window.protocol('WM_DELETE_WINDOW', close_scada)
    update_scada()

def update_scada():
    """Odswieza schemat przy kazdym kroku i kazdej zmianie obiektow."""
    if scada_window is None or scada_canvas is None:
        return
    import tkinter as tk
    try:
        if not scada_window.winfo_exists():
            return
        c = scada_canvas
        c.delete('all')
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        scale = min(w / 720.0, h / 490.0)
        # Projekt w jednostkach pierwotnych, przeskalowany wraz z tekstem.
        w, h = w / scale, h / scale
        def fontsize(n): return max(7, round(n * scale))
        green, red, neutral = '#65e3a6', '#ff8585', '#e2ebf4'
        c.create_text(22, 20, text='ENERGY MASTER / SCADA', anchor='nw',
                      fill='#f3cf77', font=('Consolas', fontsize(17), 'bold'))
        c.create_text(w-22, 25, text=f'DZIEN {day}  |  {hour:02d}:00', anchor='ne',
                      fill=neutral, font=('Consolas', fontsize(12), 'bold'))
        c.create_text(w/2, 69, text='SZyna zbiorcza — bilans systemowy [MW]'.upper(),
                      fill='#afc3d3', font=('Consolas', fontsize(11)))
        xs = [w*.17, w*.50, w*.83]
        bus_y = h*.48
        top_y = 103
        bottom_y = h*.61
        # Linie schematu jednokreskowego; symbole sa oznaczeniami umownymi.
        c.create_line(42, bus_y, w-42, bus_y, fill='#e4bd68', width=6)
        def block(x, y, name, power, positive=True, sign_mode='fixed'):
            bw, bh = 148, 71
            color = green if (power >= -1e-8 if sign_mode == 'signed' else positive) else red
            c.create_rectangle(x-bw/2, y, x+bw/2, y+bh,
                               fill='#22384a', outline='#658197', width=1)
            c.create_text(x, y+21, text=name, fill=neutral,
                          font=('Consolas', fontsize(13), 'bold'))
            c.create_text(x, y+49, text=f'{power:+.1f} MW', fill=color,
                          font=('Consolas', fontsize(14), 'bold'))
        for x in xs:
            c.create_line(x, top_y+71, x, bus_y, fill='#8ba6bc', width=2)
            c.create_line(x, bus_y, x, bottom_y, fill='#8ba6bc', width=2)
        block(xs[0], top_y, 'G_PV', scada_data.get('pv', 0.))
        block(xs[1], top_y, 'G_FW', scada_data.get('fw', 0.))
        block(xs[2], top_y, 'G_GAZ', scada_data.get('gaz', 0.))
        block(xs[0], bottom_y, 'BESS', scada_data.get('bess', 0.), sign_mode='signed')
        block(xs[1], bottom_y, 'P_city', -scada_data.get('city', 0.), positive=False)
        block(xs[2], bottom_y, 'P_factory', -scada_data.get('factory', 0.), positive=False)
        ext_y = h-82
        # Rynek EXT: netto eksport minus import. W modelu obydwa moga
        # wystapic rownoczesnie w roznych niepolaczonych podsieciach.
        exp = scada_data.get('export', 0.)
        imp = scada_data.get('imports', 0.)
        ext_net = exp-imp
        # EXT zielony dokladnie w otwartym przedziale SCORE (-10, +10) MW.
        # Na granicach -10 i +10 MW jest czerwony.
        # Kolor samego eksportu jest liczony osobno, aby import w innej
        # podsieci nie zmienial barwy wskazania eksportu.
        ext_color = green if -IMPORT_SCORE_LIMIT_MW < ext_net < IMPORT_SCORE_LIMIT_MW else red
        export_color = green if exp <= EXPORT_THRESHOLD_MW else red
        c.create_text(w/2, ext_y, text=f'EXT (eksport - import): {ext_net:+.1f} MW',
                      fill=ext_color, font=('Consolas', fontsize(12), 'bold'))
        # Osobne napisy: eksport ma swoj kolor, import swoj.
        c.create_text(w/2-12, ext_y+22, text=f'Eksport: {exp:.1f} MW',
                      anchor='e', fill=export_color, font=('Consolas', fontsize(10), 'bold'))
        c.create_text(w/2+12, ext_y+22, text=f'Import: {imp:.1f} MW',
                      anchor='w', fill=red if imp > 0 else '#adc3d3',
                      font=('Consolas', fontsize(10), 'bold'))
        bal = scada_data.get('balance', 0.)
        c.create_text(w/2, h-18,
                      text=f'GEN {scada_data.get("generation", 0.):.1f}  /  '
                           f'POBOR NETTO {scada_data.get("demand", 0.):.1f}  /  SALDO {bal:+.1f} MW',
                      fill=green if bal >= 0 else red,
                      font=('Consolas', fontsize(11), 'bold'))
        c.scale('all', 0, 0, scale, scale)
    except tk.TclError:
        pass

def pump_charts():
    if charts_root is not None:
        try:
            charts_root.update()
        except Exception:
            pass

def draw_text(txt, x, y, color=(234, 239, 242), f=font):
    screen.blit(f.render(str(txt), True, color), (x, y))

def clamp_camera():
    global camera_x, camera_y
    camera_x = max(0., min(camera_x, WORLD_W - MAP_W))
    camera_y = max(0., min(camera_y, WORLD_H - MAP_H))

def minimap_to_world(x, y):
    wx = (x - MINIMAP_INNER.x) / MINIMAP_INNER.width * WORLD_W
    wy = (y - MINIMAP_INNER.y) / MINIMAP_INNER.height * WORLD_H
    return wx, wy

def visible_hex(pos, margin=R*2.5):
    x, y = screen_center(*pos)
    return -margin <= x <= MAP_W+margin and -margin <= y <= MAP_H+margin

def draw_minimap():
    # Prosta SCADA: brak tekstur, tylko miasta, linie, obiekty i kamera.
    pygame.draw.rect(screen, (12, 25, 39), MINIMAP, border_radius=6)
    pygame.draw.rect(screen, (83, 111, 132), MINIMAP, 1, border_radius=6)
    label = pygame.font.SysFont('arial', 12, bold=True).render('MAPA SIECI', True, (232, 204, 105))
    screen.blit(label, (MINIMAP.x + 8, MINIMAP.y + 4))
    def mini(pos):
        x, y = center(*pos)
        return (round(MINIMAP_INNER.x + x / WORLD_W * MINIMAP_INNER.width),
                round(MINIMAP_INNER.y + y / WORLD_H * MINIMAP_INNER.height))
    pygame.draw.rect(screen, (22, 40, 57), MINIMAP_INNER)
    for pos, kind in world.items():
        for other in adjacent(pos):
            if other in world and pos < other:
                pygame.draw.line(screen, (215, 183, 72), mini(pos), mini(other), 1)
    for pos, kind in world.items():
        color = ((112, 207, 234) if pos in connected else (55, 92, 115)) if kind == 'CITY' else ((224, 191, 80) if kind == 'LINE' else (171, 181, 192))
        pygame.draw.circle(screen, color, mini(pos), 2 if kind == 'CITY' else 2)
    view = pygame.Rect(round(MINIMAP_INNER.x + camera_x / WORLD_W * MINIMAP_INNER.width),
                       round(MINIMAP_INNER.y + camera_y / WORLD_H * MINIMAP_INNER.height),
                       max(2, round(MAP_W / WORLD_W * MINIMAP_INNER.width)),
                       max(2, round(MAP_H / WORLD_H * MINIMAP_INNER.height)))
    pygame.draw.rect(screen, (255, 90, 90), view, 2)

simulate(0)
start_music()
running = True
open_charts()
open_scada()
while running:
    dt = min(clock.tick(60)/1000., .05)
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if handle_music_key(event):
                continue
            if event.unicode in BUILD:
                selected = event.unicode
            elif event.key == pygame.K_SPACE:
                paused = not paused
            elif event.key == pygame.K_w:
                open_charts()
            elif event.key == pygame.K_s:
                open_scada()
            elif event.key == pygame.K_e:
                economy_model_window()
            elif event.key == pygame.K_b:
                network_settings()
                simulate(0)
            elif event.key == pygame.K_r:
                generate_world()
                if city_groups:
                    sx, sy = center(*city_groups[0][0])
                    camera_x, camera_y = sx - MAP_W/2, sy - MAP_H/2
                    clamp_camera()
                budget_history[:] = [(0, money)]
                final_day_history.clear()
                simulate(0)
                notice = 'Nowa mapa i nowe miasta!'
                update_charts()
                update_scada()
            elif event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                speed = min(16, speed*2)
            elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                speed = max(1, speed//2)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and MINIMAP.collidepoint(event.pos):
                wx, wy = minimap_to_world(*event.pos)
                camera_x, camera_y = wx - MAP_W/2, wy - MAP_H/2
                clamp_camera()
                continue
            if event.button == 1 and pygame.Rect(MAP_W+18, 372, PANEL-38, 51).collidepoint(event.pos):
                show_daily_report = not show_daily_report
                notice = ('Raport dzienny: wlaczony' if show_daily_report
                          else 'Raport dzienny: wylaczony — gra bez przerw')
                continue
            if event.button == 1:
                clicked_build = build_button_at(event.pos)
                if clicked_build is not None:
                    selected = clicked_build
                    notice = f'Wybrano {BUILD[selected][0]} — kliknij wolny heks.'
                    continue  # klik panelu NIE buduje na mapie
            if event.button == 1 and pygame.Rect(MAP_W+18,BESS_BUTTON_Y,PANEL-38,36).collidepoint(event.pos):
                network_settings()
                simulate(0)
                continue
            if event.button == 1 and pygame.Rect(MAP_W+18,ECON_BUTTON_Y,PANEL-38,34).collidepoint(event.pos):
                economy_model_window()
                continue
            pos = mouse_hex(*event.pos)
            if pos is None:
                continue
            if event.button == 1:
                if game_finished:
                    notice = 'Koniec gry. Nacisnij R, aby zaczac od nowa.'
                elif pos in world:
                    notice = 'Pole zajete (miast nie mozna zabudowac).'
                elif terrain[pos] != 'grass':
                    notice = 'Budowac mozna tylko na trawie.'
                else:
                    kind, cost, _ = BUILD[selected]
                    money -= cost
                    daily["investments"] += cost
                    world[pos] = kind
                    if kind == 'BESS':
                        bess_energy[pos] = 0.
                    notice = f'Zbudowano {kind}, koszt {cost} coins. Saldo: {money:,.0f} coins'
                    simulate(0)
                    notice += f' | CITY: {connected_city_count}/{len(city_tiles)}'
            elif event.button == 3 and pos in world and not game_finished:
                if pos in city_tiles:
                    notice = 'Miasta sa chronione przed rozbiorka!'
                else:
                    kind = world.pop(pos)
                    bess_energy.pop(pos, None)
                    refund = next(v[1] for v in BUILD.values() if v[0] == kind)*.25
                    money += refund
                    daily["refunds"] += refund
                    notice = f'Usunieto {kind} (zwrot {refund:,.1f} coins).'
                    simulate(0)
    pump_charts()
    if not paused and not report_open and not game_finished:
        elapsed += dt*speed
        while elapsed >= 1.:
            elapsed -= 1.
            simulate(1.)
            hour += 1
            if hour >= 24:
                # Przychod fabryk: raz po zakonczeniu doby, przed raportem i wykresem.
                factory_count = connected_factory_count
                factory_income = factory_count * FACTORY_DAILY_INCOME
                money += factory_income
                daily["factory_income"] += factory_income
                # Stala oplata OSD za kazdy heks odbiorczy: raz na dobe.
                customer_hexes = connected_city_count + connected_factory_count
                distribution_fixed = DISTRIBUTION_FIXED_FEE * customer_hexes
                money += distribution_fixed
                daily['distribution_fixed'] += distribution_fixed
                # Koszt eksploatacji: tylko heksy z wybudowanym obiektem LINE.
                line_count = sum(kind == 'LINE' for kind in world.values())
                maintenance = line_count * LINE_MAINTENANCE_DAILY
                money -= maintenance
                daily['line_maintenance'] += maintenance
                budget_history.append((day, money))
                # Zapisujemy wynik kazdej zakonczonej doby, rowniez gdy raporty sa wylaczone.
                final_day_history.append((day, money, score_green_hours,
                                          score_total_hours, daily['generation'], daily['demand']))
                hour = 0
                if day >= GAME_DAYS:
                    game_finished = True
                    notice = "KONIEC GRY — R: nowa rozgrywka"
                    show_final_report()  # Final zawsze, bez wzgledu na checkbox.
                elif show_daily_report:
                    daily_report()
                else:
                    advance_to_next_day()
                elapsed = 0.
                break
            update_charts()
            simulate(0)
    # Kamera dziala rowniez przy pauzie symulacji.
    keys = pygame.key.get_pressed()
    camera_x += (int(keys[pygame.K_RIGHT]) - int(keys[pygame.K_LEFT])) * CAMERA_SPEED * dt
    camera_y += (int(keys[pygame.K_DOWN]) - int(keys[pygame.K_UP])) * CAMERA_SPEED * dt
    clamp_camera()
    # Faza sprite'ow liczona z zegara renderowania (dziala takze podczas pauzy).
    frame_index = (pygame.time.get_ticks() // ANIMATION_FRAME_MS) % ANIMATION_COUNT
    # Ulamkowa godzina daje plynne przejscia przy kazdym tempie gry.
    visual_hour = hour + (min(1.0, elapsed) if not paused and not report_open and not game_finished else 0.0)
    screen.fill((20, 29, 38))
    # Jednolity zielony podklad: ewentualne 1-pikselowe szczeliny
    # miedzy skosnymi krawedziami PNG nie pokazuja jasnego tla.
    pygame.draw.rect(screen, (53, 93, 28), (0, 0, MAP_W, MAP_H))
    screen.set_clip(pygame.Rect(0, 0, MAP_W, MAP_H))
    for pos, kind in terrain.items():
        # Miasta rysujemy tylko raz, w petli city_tiles ponizej.
        if not visible_hex(pos) or kind == 'city' or pos in city_tiles:
            continue
        color = (65, 107, 54)  # wspolna zielen pod wszystkimi heksami
        pygame.draw.polygon(screen, color, hex_points(pos, R + 1.15))
        # Opcjonalny sprite terenu jest maskowany do heksagonu.
        terrain_sprite = terrain_sprite_at(pos, kind)
        if terrain_sprite is not None:
            x, y = screen_center(*pos)
            rect = terrain_sprite.get_rect(center=(round(x), round(y)))
            mask = pygame.Surface(terrain_sprite.get_size(), pygame.SRCALPHA)
            pts = [(px-rect.left, py-rect.top) for px, py in hex_points(pos, R + 1.15)]
            pygame.draw.polygon(mask, (255, 255, 255, 255), pts)
            tile = terrain_sprite.copy()
            tile.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(tile, rect)
        if kind == 'forest' and terrain_sprite is None:
            x, y = screen_center(*pos)
            pygame.draw.circle(screen, (26, 67, 39), (round(x), round(y)), 10)
    for p in city_tiles:
        if not visible_hex(p):
            continue
        pygame.draw.polygon(screen, (65, 107, 54), hex_points(p, R-1))
        x, y = screen_center(*p)
        # Small houses represent 500 consumers per city tile.
        if blit_hex_sprite(city_sprite_at(p, visual_hour), p):
            if p not in connected:
                pygame.draw.circle(screen, (225, 88, 88), (round(x+R*.45), round(y-R*.48)), 4)
            continue
        if p not in connected:
            pygame.draw.circle(screen, (225, 88, 88), (round(x+R*.45), round(y-R*.48)), 4)
        for dx, dy in ((-10,-5), (7,-9), (-2,9)):
            rect = pygame.Rect(round(x+dx-5), round(y+dy-3), 10, 9)
            pygame.draw.rect(screen, (238, 221, 183), rect)
            pygame.draw.polygon(screen, (157, 83, 64), [(rect.left-1,rect.top),
                (rect.centerx,rect.top-6),(rect.right+1,rect.top)])
    for pos, kind in world.items():
        if not visible_hex(pos) or kind == 'CITY':
            continue
        x, y = screen_center(*pos)
        color = next(v[2] for v in BUILD.values() if v[0] == kind)
        if blit_hex_sprite(animated_building_sprite(kind, frame_index), pos):
            continue
        pygame.draw.circle(screen, color, (round(x), round(y)), 13 if kind != 'LINE' else 8)
        if kind != 'LINE':
            symbol = {'PV':'P','WIND':'W','GAS':'G','BESS':'B','FACTORY':'F'}[kind]
            surf = small.render(symbol, True, (20, 30, 36))
            screen.blit(surf, surf.get_rect(center=(x, y)))
    # WARSTWA 2: kontury heksow na wierzchu terenu i budynkow.
    border_layer = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)
    for pos in terrain:
        if not visible_hex(pos):
            continue
        pygame.draw.polygon(border_layer, (*HEX_BORDER_COLOR, HEX_BORDER_ALPHA),
                            hex_points(pos, R), HEX_BORDER_WIDTH)
    screen.blit(border_layer, (0, 0))

    # WARSTWA 3: polaczenia sieciowe jako OSTATNIA warstwa mapy.
    # Rysujemy na SRCALPHA, poniewaz pygame.draw.line(screen, RGBA, ...)
    # nie miesza kanalu alfa z juz narysowanymi pikselami ekranu.
    line_layer = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)
    for pos, kind in world.items():
        if not visible_hex(pos):
            continue
        for other in adjacent(pos):
            if other in world and pos < other:
                active = pos in connected and other in connected
                color = (255, 219, 83) if active else (130, 132, 137)
                pygame.draw.line(line_layer, (*color, LINE_ALPHA),
                                 screen_center(*pos), screen_center(*other), 5 if active else 3)
    screen.blit(line_layer, (0, 0))

    mx, my = pygame.mouse.get_pos()
    hovered = mouse_hex(mx, my)
    if hovered:
        pygame.draw.polygon(screen, (255, 242, 149), hex_points(hovered), 3)
    # Noc nakladamy na cala mape PO budynkach i polaczeniach,
    # PRZED panelem bocznym (UI pozostaje jasny).
    darkness = night_alpha(visual_hour)
    if darkness:
        NIGHT_LAYER.fill((0, 0, 0, darkness))
        screen.blit(NIGHT_LAYER, (0, 0))
    draw_minimap()  # jasna minimapa SCADA nad warstwa nocy
    screen.set_clip(None)
    px = MAP_W+18
    draw_text('ENERGY MASTER', px, 12, (247, 210, 95), big)
    draw_text('ALPHA 1.6 - CONNECTED GRID / SCADA', px, 42, (163, 185, 196), small)
    draw_text(f'Budzet: {money:,.0f} coins', px, 66, (240, 105, 105) if money < 0 else (225, 235, 240))
    draw_text(f'Dzien: {day}/{GAME_DAYS}  Godz.: {hour:02d}:00  Tempo: x{speed}' + (' [PAUZA]' if paused else ''), px, 93, f=small)
    score_pct = 100.0 * score_green_hours / score_total_hours if score_total_hours else 0.0
    draw_text(f'SCORE: {score_pct:.1f}% ({score_green_hours}/{score_total_hours} h)',
              px, 525, (125, 229, 163), small)
    if game_finished:
        draw_text('KONIEC GRY! R - nowa gra', px+155, 558, (247, 210, 95), small)
    draw_text(f'Miasta: {len(city_groups)} | Heksy CITY: {connected_city_count}/{len(city_tiles)} podlaczone', px, 115, f=small)
    draw_text('BUDOWANIE - kliknij lub 1-6 (koszt / moc)', px, 143, (247, 210, 95), small)
    power_labels = {'PV':'20 MWp', 'WIND':'30 MW', 'GAS':'50 MW (stala)',
                    'BESS':'20 MW / 80 MWh', 'FACTORY':'18 MW (06–22), 5 MW (noc)', 'LINE':'limit 50 MW'}
    for i, (key, (name, cost, color)) in enumerate(BUILD.items()):
        yy = 167+i*31
        if key == selected:
            pygame.draw.rect(screen, (57, 78, 93), (px-5, yy-3, PANEL-32, 29), border_radius=4)
        pygame.draw.rect(screen, color, (px, yy+3, 14, 14))
        draw_text(f'{key} {name:<5} {cost:>4} coins', px+21, yy, f=small)
        draw_text(power_labels[name], px+168, yy, (180, 210, 224), small)
    draw_text('OPCJE ROZGRYWKI', px, 350, (247, 210, 95), small)
    # Checkbox rysowany w Pygame — bez dodatkowego okna Tkinter.
    pygame.draw.rect(screen, (38, 54, 65), REPORT_CHECKBOX, border_radius=3)
    pygame.draw.rect(screen, (124, 226, 161) if show_daily_report else (153, 173, 185),
                     REPORT_CHECKBOX, 2, border_radius=3)
    if show_daily_report:
        cx, cy = REPORT_CHECKBOX.topleft
        pygame.draw.lines(screen, (124, 226, 161), False,
                          [(cx+5, cy+12), (cx+10, cy+17), (cx+19, cy+6)], 3)
    draw_text('Pokaz raport dzienny', px+34, 388, f=small)
    draw_text('Raport po kazdej dobie' if show_daily_report else 'Gra bez przerw miedzy dobami',
              px+3, 429, (153, 185, 200), small)
    draw_text('Wyniki dobowe sa nadal rozliczane.', px+3, 455, (153, 185, 200), small)
    draw_text(f'BESS {charge_start:02d}-{discharge_start:02d} | OSD {DISTRIBUTION_FIXED_FEE:g}+{DISTRIBUTION_VARIABLE_FEE:g}/MWh', px, 558, f=small)
    bess_button = pygame.Rect(px, BESS_BUTTON_Y, PANEL-38, 36)
    pygame.draw.rect(screen,(70,96,112),bess_button,border_radius=6)
    draw_text('B - USTAWIENIA SIECI',px+20,BESS_BUTTON_Y+9,(245,240,210),small)
    econ_button = pygame.Rect(px, ECON_BUTTON_Y, PANEL-38, 34)
    pygame.draw.rect(screen,(70,96,112),econ_button,border_radius=6)
    draw_text('E - MODEL EKONOMII',px+20,ECON_BUTTON_Y+8,(245,240,210),small)
    # Jeden wiersz stopki: komunikat po lewej, sterowanie po prawej.
    controls = 'STRZALKI: kamera | minimapa: skok | 1-6/klik: buduj | R: mapa | B: siec | E: ekonomia | W: wykresy | S: SCADA | SPACE: pauza | +/-: tempo | M: muzyka | </>: glosnosc'
    controls_surface = chart_font.render(controls, True, (165, 185, 195))
    controls_x = WIDTH - controls_surface.get_width() - 12
    available_notice_width = max(0, controls_x - 30)
    short_notice = notice
    while short_notice and small.size(short_notice)[0] > available_notice_width:
        short_notice = short_notice[:-1]
    if short_notice != notice and len(short_notice) > 3:
        short_notice = short_notice[:-3] + '...'
    draw_text(short_notice, 12, HEIGHT-25, (234, 238, 241), small)
    screen.blit(controls_surface, (controls_x, HEIGHT-25))
    pygame.display.flip()
if MUSIC_AVAILABLE:
    pygame.mixer.music.stop()
if charts_root is not None:
    charts_root.destroy()
pygame.quit()

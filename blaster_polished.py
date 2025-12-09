import pygame
import sys
import random
import cv2
import mediapipe as mp
import math
import os 
import threading
import time

# --- Path Setup ---
if '__file__' in globals():
    game_folder = os.path.abspath(os.path.dirname(__file__))
else:
    game_folder = os.path.abspath(os.getcwd())
img_folder = os.path.join(game_folder, "img")
snd_folder = os.path.join(game_folder, "snd")
font_folder = os.path.join(game_folder, "fonts")
HIGH_SCORE_FILE = os.path.join(game_folder, "highscore.txt")

# --- Pengaturan Font Global ---
FONTS = {}
FONT_FILES = {
    'Oxanium': os.path.join(font_folder, 'Oxanium-Regular.ttf'),
    'Orbitron': os.path.join(font_folder, 'Orbitron-Regular.ttf'),
    'RussoOne': os.path.join(font_folder, 'RussoOne.ttf'),
}

def load_font(font_key, size):
    """Memuat custom font, fallback ke Arial jika gagal."""
    font_path = FONT_FILES.get(font_key)
    if font_path and os.path.exists(font_path):
        try:
            return pygame.font.Font(font_path, size)
        except pygame.error:
            pass 
    return pygame.font.Font(pygame.font.match_font('arial'), size)

# --- Fungsi Bantuan CV ---
def get_distance(p1, p2):
    return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)

def get_pixel_dist(center1, center2):
    return math.sqrt((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)

# --- Inisialisasi CV dan MediaPipe ---
cap = cv2.VideoCapture(0)
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    model_complexity=1,              
    max_num_hands=1,
    min_detection_confidence=0.5,    
    min_tracking_confidence=0.5)

camera_available = cap.isOpened()
cv_lock = threading.Lock()
cv_running = threading.Event()
cv_running.set()
latest_cv = {
    'results': None,
    'index_x_frac': 0.5,
    'pinch_distance': None,
    'index_folded': False,
    'middle_folded': False,
    'hand_present': False 
}

def camera_thread_loop():
    global latest_cv
    last_process = 0.0
    while cv_running.is_set():
        success, image = cap.read()
        if not success:
            time.sleep(0.05)
            continue
        
        image = cv2.flip(image, 1)
        now = time.time()
        
        if now - last_process < 0.05:
            time.sleep(0.01)
            continue
            
        last_process = now

        try:
            h, w = image.shape[:2]
            target_w = 320
            target_h = max(1, int(h * (target_w / float(w))))
            small = cv2.resize(image, (target_w, target_h))
            image_rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            results = hands.process(image_rgb)
        except Exception:
            results = None

        with cv_lock:
            latest_cv['results'] = results
            if results and results.multi_hand_landmarks:
                hand_landmarks = results.multi_hand_landmarks[0]
                thumb_tip = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
                index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                middle_tip = hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_TIP]
                wrist = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST]
                
                raw_x = index_tip.x 
                clamped_x = max(0.0, min(1.0, (raw_x - 0.1) / 0.8))
                latest_cv['index_x_frac'] = clamped_x
                
                latest_cv['pinch_distance'] = get_distance(thumb_tip, index_tip)
                latest_cv['index_folded'] = get_distance(index_tip, wrist) < get_distance(hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_MCP], wrist)
                latest_cv['middle_folded'] = get_distance(middle_tip, wrist) < get_distance(hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_MCP], wrist)
                latest_cv['hand_present'] = True 
            else:
                latest_cv['pinch_distance'] = None
                latest_cv['index_folded'] = False
                latest_cv['middle_folded'] = False
                latest_cv['hand_present'] = False 

camera_thread = None

# --- Inisialisasi Pygame ---
pygame.init()
pygame.mixer.init()

# --- Konstanta ---
WIDTH, HEIGHT = 960, 720 
FPS = 45
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
YELLOW = (255, 255, 0)
RED = (255, 0, 0)
NEON_BLUE = (0, 255, 255) 
ORANGE = (255, 165, 0)
UI_BG = (20, 20, 40, 220) 

# --- CLASSES ---

class Particle(pygame.sprite.Sprite):
    def __init__(self, x, y, color, size, velocity, lifetime):
        super().__init__()
        self.image = pygame.Surface((size, size))
        self.image.fill(color)
        self.rect = self.image.get_rect(center=(x, y))
        self.vel = velocity
        self.lifetime = lifetime
        self.original_lifetime = lifetime
        self.color = color
        self.size = size

    def update(self, *args):
        self.rect.x += self.vel[0]
        self.rect.y += self.vel[1]
        self.lifetime -= 1
        
        alpha = int((self.lifetime / self.original_lifetime) * 255)
        self.image.set_alpha(alpha)
        
        if self.lifetime <= 0:
            self.kill()

class FloatingText(pygame.sprite.Sprite):
    def __init__(self, x, y, text, color):
        super().__init__()
        font = load_font('Oxanium', 20)
        self.image = font.render(text, True, color)
        self.rect = self.image.get_rect(center=(x, y))
        self.vel_y = -2
        self.lifetime = 40

    def update(self, *args):
        self.rect.y += self.vel_y
        self.lifetime -= 1
        if self.lifetime <= 0:
            self.kill()

class Explosion(pygame.sprite.Sprite):
    def __init__(self, center, scale=1.0):
        super().__init__()
        self.raw_image = explosion_sheet.copy()
        if scale != 1.0:
            w = int(self.raw_image.get_width() * scale)
            h = int(self.raw_image.get_height() * scale)
            self.raw_image = pygame.transform.scale(self.raw_image, (w, h))
            
        self.frame_width = self.raw_image.get_width() // 8 
        self.frame_height = self.raw_image.get_height()
        self.images = []
        for i in range(8):
            frame = self.raw_image.subsurface(pygame.Rect(i * self.frame_width, 0, self.frame_width, self.frame_height))
            self.images.append(frame)
        self.image = self.images[0]
        self.rect = self.image.get_rect()
        self.rect.center = center
        self.frame = 0
        self.last_update = pygame.time.get_ticks()
        self.frame_rate = 50

    def update(self, *args):
        now = pygame.time.get_ticks()
        if now - self.last_update > self.frame_rate:
            self.last_update = now
            self.frame += 1
            if self.frame == len(self.images):
                self.kill()
            else:
                center = self.rect.center
                self.image = self.images[self.frame]
                self.rect = self.image.get_rect()
                self.rect.center = center

class PowerUp(pygame.sprite.Sprite):
    def __init__(self, center, type_str):
        super().__init__()
        self.type = type_str
        if self.type == 'double':
            self.image = pu_double_img
        elif self.type == 'spread':
            self.image = pu_spread_img
        elif self.type == 'missile':
            self.image = pu_missile_img
        elif self.type == 'shield':
            self.image = pygame.Surface((30, 30), pygame.SRCALPHA)
            pygame.draw.circle(self.image, (0, 255, 255), (15, 15), 15)
            pygame.draw.circle(self.image, WHITE, (15, 15), 13, 2)
            font = pygame.font.SysFont('arial', 20, bold=True)
            txt = font.render("P", True, BLACK)
            self.image.blit(txt, (15 - txt.get_width()//2, 15 - txt.get_height()//2))
        else:
            self.image = bomb_img 
            
        self.rect = self.image.get_rect()
        self.rect.center = center
        self.speed_y = 3
        
    def update(self, player_x=None, *args):
        if player_x is None: return 
        self.rect.y += self.speed_y
        if self.rect.top > HEIGHT:
            self.kill()

class Player(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.image_original = player_img.copy() 
        self.image = self.image_original
        self.image.set_colorkey(BLACK)
        self.rect = self.image.get_rect()
        self.radius = int(self.rect.width * .85 / 2)
        self.rect.centerx = WIDTH // 2
        self.rect.bottom = HEIGHT - 10
        
        self.default_delay = 250
        self.last_shot = pygame.time.get_ticks()
        self.lives = 3
        self.hidden = False
        self.hide_timer = pygame.time.get_ticks()
        
        self.powerup_type = 'normal' 
        self.invincible = False
        self.invincible_timer = pygame.time.get_ticks()
        self.invincible_duration = 3000 
        self.shield_active = False

    def powerup(self, p_type):
        if p_type == 'shield':
            self.shield_active = True
            self.invincible = True
            self.invincible_timer = pygame.time.get_ticks()
            self.invincible_duration = 5000 
        else:
            self.powerup_type = p_type

    def update(self, target_x=None, all_sprites=None, *args):
        if target_x is None: return 

        now = pygame.time.get_ticks()
        
        # Engine Trail Particles
        if not self.hidden and random.random() < 0.3 and all_sprites:
            p = Particle(self.rect.centerx, self.rect.bottom, (100, 200, 255), random.randint(2,5), (random.uniform(-1,1), random.uniform(1,3)), 20)
            all_sprites.add(p)

        if self.invincible:
            if now - self.invincible_timer > self.invincible_duration:
                self.invincible = False
                self.image.set_alpha(255) 
            else:
                alpha = 128 if (now // 100) % 2 == 0 else 255
                self.image.set_alpha(alpha)
        else:
            self.image.set_alpha(255)

        if self.hidden:
            if now - self.hide_timer > 1000:
                self.hidden = False
                self.rect.centerx = WIDTH // 2
                self.rect.bottom = HEIGHT - 10
                self.invincible = True 
                self.invincible_timer = now
                self.shield_active = True 
        
        if not self.hidden:
            dx = target_x - self.rect.centerx
            if abs(dx) <= 3:
                self.rect.centerx = int(target_x)
            else:
                self.rect.centerx += int(dx * 0.5) 
            
            if self.rect.right > WIDTH:
                self.rect.right = WIDTH
            if self.rect.left < 0:
                self.rect.left = 0

    def shoot(self, all_sprites, bullets_group):
        if not self.hidden:
            now = pygame.time.get_ticks()
            current_delay = self.default_delay
            if self.powerup_type == 'missile':
                current_delay = 500
            
            if now - self.last_shot > current_delay:
                self.last_shot = now
                shoot_sound.play()
                
                dmg_normal = 20   
                dmg_missile = 50  

                if self.powerup_type == 'normal':
                    bullet = Bullet(self.rect.centerx, self.rect.top, damage=dmg_normal)
                    all_sprites.add(bullet)
                    bullets_group.add(bullet)
                
                elif self.powerup_type == 'double':
                    b1 = Bullet(self.rect.left, self.rect.centery, img=bullet_double_img, damage=dmg_normal)
                    b2 = Bullet(self.rect.right, self.rect.centery, img=bullet_double_img, damage=dmg_normal)
                    all_sprites.add(b1, b2)
                    bullets_group.add(b1, b2)
                    
                elif self.powerup_type == 'spread':
                    b1 = Bullet(self.rect.centerx, self.rect.top, img=bullet_spread_img, damage=dmg_normal)
                    b2 = Bullet(self.rect.centerx, self.rect.top, -2, img=bullet_spread_img, damage=dmg_normal)
                    b3 = Bullet(self.rect.centerx, self.rect.top, 2, img=bullet_spread_img, damage=dmg_normal)
                    all_sprites.add(b1, b2, b3)
                    bullets_group.add(b1, b2, b3)
                    
                elif self.powerup_type == 'missile':
                    b = Bullet(self.rect.centerx, self.rect.top, img=bullet_missile_img, damage=dmg_missile, aoe_radius=150)
                    b.speed_y = -8 
                    all_sprites.add(b)
                    bullets_group.add(b)

    def hide(self):
        self.hidden = True
        self.shield_active = False
        self.powerup_type = 'normal'
        self.hide_timer = pygame.time.get_ticks()
        self.rect.center = (WIDTH / 2, HEIGHT + 200)

class Bullet(pygame.sprite.Sprite):
    def __init__(self, x, y, vx=0, img=None, damage=5, aoe_radius=0):
        super().__init__()
        self.image = img if img else bullet_img
        self.image.set_colorkey(BLACK)
        self.rect = self.image.get_rect()
        self.rect.centerx = x
        self.rect.bottom = y
        self.speed_y = -10
        self.speed_x = vx
        self.damage = damage
        self.aoe_radius = aoe_radius

    def update(self, *args):
        self.rect.y += self.speed_y
        self.rect.x += self.speed_x
        if self.rect.bottom < 0 or self.rect.left < 0 or self.rect.right > WIDTH:
            self.kill()

class EnemyBullet(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = pygame.transform.scale(boss_bullet_img, (15, 15)) 
        self.image.set_colorkey(BLACK)
        self.rect = self.image.get_rect()
        self.rect.centerx = x
        self.rect.top = y
        self.speed_y = 6

    def update(self, *args):
        self.rect.y += self.speed_y
        if self.rect.top > HEIGHT:
            self.kill()

# --- ENEMY CLASSES (VARIETY) ---

class Enemy(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.image = enemy_img.copy()
        self.image.set_colorkey(BLACK)
        self.rect = self.image.get_rect()
        self.radius = int(self.rect.width * .85 / 2)
        self.reset_pos()
        self.hp = 1 # Musuh biasa 1 hit mati
        self.score_val = 10
        self.hit_timer = 0

    def reset_pos(self):
        max_x = max(0, WIDTH - self.rect.width)
        self.rect.x = random.randrange(0, max_x) if max_x > 0 else 0
        self.rect.y = random.randrange(-150, -100)
        self.speed_y = random.randrange(2, 5)
        self.speed_x = random.randrange(-1, 2)

    def hit(self):
        self.hit_timer = pygame.time.get_ticks()
        self.image.set_alpha(150)

    def shoot(self, all_sprites, enemy_bullets):
        if random.random() < 0.005:
            eb = EnemyBullet(self.rect.centerx, self.rect.bottom)
            all_sprites.add(eb)
            enemy_bullets.add(eb)

    def update(self, *args):
        if self.hit_timer > 0 and pygame.time.get_ticks() - self.hit_timer > 100:
             self.image.set_alpha(255)
             self.hit_timer = 0

        self.rect.y += self.speed_y
        self.rect.x += self.speed_x
        if self.rect.top > HEIGHT + 10 or self.rect.left < -50 or self.rect.right > WIDTH + 50:
            self.reset_pos()

class ZigZagEnemy(Enemy):
    def __init__(self):
        super().__init__()
        # Tint warna hijau agar beda
        self.image.fill((50, 255, 50, 100), special_flags=pygame.BLEND_RGB_MULT)
        self.rect = self.image.get_rect()
        self.reset_pos()
        self.t = random.random() * 100
        self.score_val = 20
        self.speed_y = 3

    def update(self, *args):
        super().update()
        self.t += 0.1
        self.rect.x += int(math.sin(self.t) * 5) # Gerakan gelombang

class TankerEnemy(Enemy):
    def __init__(self):
        super().__init__()
        # Resize jadi lebih besar
        raw = pygame.transform.scale(enemy_img, (80, 64))
        self.image = raw
        self.image.set_colorkey(BLACK)
        # Tint warna merah agar terlihat kuat
        self.image.fill((255, 100, 100, 100), special_flags=pygame.BLEND_RGB_MULT)
        self.rect = self.image.get_rect()
        self.radius = int(self.rect.width * 0.4)
        self.reset_pos()
        self.hp = 5 # Butuh 5 hit
        self.speed_y = 1 # Lambat
        self.score_val = 50

    def update(self, *args):
        if self.hit_timer > 0 and pygame.time.get_ticks() - self.hit_timer > 100:
             self.image.set_alpha(255)
             self.hit_timer = 0
        
        self.rect.y += self.speed_y
        # Tidak ada gerakan horizontal random (speed_x) untuk tanker, dia lurus tapi mematikan
        if self.rect.top > HEIGHT + 10:
            self.reset_pos()

class KamikazeEnemy(Enemy):
    def __init__(self):
        super().__init__()
        # Warna kuning
        self.image.fill((255, 255, 0, 100), special_flags=pygame.BLEND_RGB_MULT)
        self.reset_pos()
        self.state = 'hover'
        self.timer = pygame.time.get_ticks()
        self.score_val = 30

    def update(self, *args):
        super().update() # Handle flash effect
        if self.state == 'hover':
            self.rect.y += 1
            if pygame.time.get_ticks() - self.timer > 1500: # Diam 1.5 detik
                self.state = 'dive'
                self.speed_y = 12 # Ngebut banget
        elif self.state == 'dive':
            self.rect.y += self.speed_y

# --- BOSS CLASS ---
class Boss(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.image = boss_img
        self.image.set_colorkey(BLACK)
        self.rect = self.image.get_rect()
        self.radius = int(self.rect.width * 0.4)
        self.rect.centerx = WIDTH // 2
        self.rect.y = -100
        
        self.max_hp = 2000
        self.hp = self.max_hp
        self.state = 'entering' 
        self.speed_x = 3
        
        self.last_shot = 0
        self.shoot_delay = 900
        self.wave_offset = 0

    def update(self, *args):
        if self.state == 'entering':
            self.rect.y += 2
            if self.rect.y >= 50:
                self.state = 'fight'

        elif self.state == 'fight':
            self.rect.x += self.speed_x
            if self.rect.right > WIDTH or self.rect.left < 0:
                self.speed_x *= -1

            if self.hp < self.max_hp * 0.25:
                self.speed_x = 5 if self.speed_x > 0 else -5
            else:
                self.speed_x = 3 if self.speed_x > 0 else -3

    def shoot(self):
        pass 

class BossBullet(pygame.sprite.Sprite):
    def __init__(self, x, y, vx=0, vy=6):
        super().__init__()
        self.image = boss_bullet_img
        self.image.set_colorkey(BLACK)
        self.rect = self.image.get_rect()
        self.rect.centerx = x
        self.rect.top = y
        self.speed_y = vy
        self.speed_x = vx

    def update(self, *args):
        self.rect.y += self.speed_y
        self.rect.x += self.speed_x
        if self.rect.top > HEIGHT or self.rect.bottom < 0 or self.rect.left < -50 or self.rect.right > WIDTH + 50:
            self.kill()

# --- Helper Functions UI ---

def draw_text(surf, text, size, x, y, color=WHITE, font_key='Oxanium'):
    font_key_size = f"{font_key}_{size}"
    if font_key_size not in FONTS:
        FONTS[font_key_size] = load_font(font_key, size)
    font = FONTS[font_key_size]
    text_surface = font.render(text, True, color)
    text_rect = text_surface.get_rect()
    text_rect.topleft = (x, y)
    surf.blit(text_surface, text_rect)

def draw_text_center(surf, text, size, cx, y, color=WHITE, font_key='Oxanium'):
    font_key_size = f"{font_key}_{size}"
    if font_key_size not in FONTS:
        FONTS[font_key_size] = load_font(font_key, size)
    font = FONTS[font_key_size]
    text_surface = font.render(text, True, color)
    rect = text_surface.get_rect()
    rect.centerx = cx
    rect.top = y
    surf.blit(text_surface, rect)

def draw_hud_panel_modern(surf, x, y, w, h, color):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill((0, 0, 0, 180)) 
    pygame.draw.rect(s, (255, 255, 255, 100), (0, 0, w, h), 1, border_radius=8)
    surf.blit(s, (x, y))

def draw_bar_modern(surf, x, y, w, h, current, maximum, color_start, color_end):
    frac = max(0.0, min(1.0, current / maximum)) if maximum else 0
    fill_w = int(frac * w)
    
    bg_color = (60, 0, 0) if color_start == (255, 50, 50) else (40, 40, 40)
    pygame.draw.rect(surf, bg_color, (x, y, w, h), border_radius=3)
    if fill_w > 0:
        for i in range(fill_w):
            r = color_start[0] + (color_end[0] - color_start[0]) * (i / w)
            g = color_start[1] + (color_end[1] - color_start[1]) * (i / w)
            b = color_start[2] + (color_end[2] - color_start[2]) * (i / w)
            pygame.draw.line(surf, (int(r), int(g), int(b)), (x + i, y), (x + i, y + h - 1))
    pygame.draw.rect(surf, WHITE, (x, y, w, h), 2, border_radius=3)


# --- MAIN ---
def main():
    global WIDTH, HEIGHT
    global background_img, player_img, player_mini_img, enemy_img, bullet_img, bomb_img, explosion_sheet
    global boss_img, boss_bullet_img, pu_double_img, pu_spread_img, pu_missile_img
    global bullet_double_img, bullet_spread_img, bullet_missile_img
    global shoot_sound, expl_sound, player_die_sound, bomb_sound, boss_shoot_sound
    global camera_thread
    global NEON_BLUE, UI_BG 

    # Setup Layar
    screen_w, screen_h = 800, 600
    try:
        import ctypes
        user32 = ctypes.windll.user32
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
    except:
        pass
    
    screen = pygame.display.set_mode((screen_w, screen_h), pygame.FULLSCREEN)
    pygame.display.set_caption("BLASTER CV GAME")
    GAME_W, GAME_H = 960, 720
    WIDTH, HEIGHT = GAME_W, GAME_H 
    game_surface = pygame.Surface((GAME_W, GAME_H))
    clock = pygame.time.Clock()
    display_info = pygame.display.Info()

    def blit_centered(shake_offset=(0,0)):
        try:
            scaled = pygame.transform.scale(game_surface, (display_info.current_w, display_info.current_h))
            screen.blit(scaled, shake_offset)
        except:
            screen.blit(game_surface, shake_offset)

    # --- Load Images ---
    def load_img(name, scale=None):
        path = os.path.join(img_folder, name)
        try:
            img = pygame.image.load(path).convert_alpha()
            if scale: img = pygame.transform.scale(img, scale)
            return img
        except:
            surf = pygame.Surface((30,30))
            surf.fill((255,0,255))
            return surf

    background_img = load_img("background.png", (GAME_W, GAME_H))
    player_img = load_img("player.png", (60, 48))
    player_mini_img = pygame.transform.scale(player_img, (25, 19))
    enemy_img = load_img("enemy.png", (50, 40))
    bullet_img = load_img("bullet.png")
    bomb_img = load_img("bomb_icon.png")
    explosion_sheet = load_img("explosion_spritesheet.png")
    
    boss_img = load_img("boss.png")
    boss_bullet_img = load_img("boss_bullet.png")
    
    pu_double_img = load_img("pu_double.png")
    pu_spread_img = load_img("pu_spread.png")
    pu_missile_img = load_img("pu_missile.png")
    
    bullet_double_img = load_img("bullet_double.png")
    bullet_spread_img = load_img("bullet_spread.png")
    bullet_missile_img = load_img("bullet_missile.png")

    # --- Load Sounds ---
    def load_snd(name):
        path = os.path.join(snd_folder, name)
        try:
            return pygame.mixer.Sound(path)
        except:
            return pygame.mixer.Sound(buffer=bytearray([0]*100))

    shoot_sound = load_snd("shoot.wav")
    expl_sound = load_snd("expl_enemy.wav")
    player_die_sound = load_snd("expl_player.wav")
    bomb_sound = load_snd("bomb_launch.wav")
    boss_shoot_sound = load_snd("boss_shoot.wav")

    # Music
    music_normal = os.path.join(snd_folder, "music.mp3")
    music_boss = os.path.join(snd_folder, "boss_music.wav")
    
    shoot_sound.set_volume(0.2)
    boss_shoot_sound.set_volume(0.4)
    expl_sound.set_volume(0.3)
    player_die_sound.set_volume(0.5) 

    # --- Game Variables ---
    score = 0
    highscore = 0
    try:
        with open(HIGH_SCORE_FILE, 'r') as f: highscore = int(f.read().strip())
    except: pass

    # Groups
    all_sprites = pygame.sprite.Group()
    enemies = pygame.sprite.Group()
    bullets = pygame.sprite.Group()
    enemy_bullets = pygame.sprite.Group() 
    powerups = pygame.sprite.Group()
    explosions = pygame.sprite.Group()
    floating_texts = pygame.sprite.Group()
    
    player = Player()
    
    boss = None
    boss_level_count = 0 

    # Parallax & Shake Variables
    bg_y = 0
    shake_intensity = 0

    def spawn_enemy():
        # Random pick enemy type
        r = random.random()
        if r < 0.6:
            e = Enemy() # 60% Basic
        elif r < 0.8:
            e = ZigZagEnemy() # 20% ZigZag
        elif r < 0.9:
            e = KamikazeEnemy() # 10% Kamikaze
        else:
            e = TankerEnemy() # 10% Tanker
            
        all_sprites.add(e)
        enemies.add(e)
    
    def spawn_floating_text(x, y, text, color=WHITE):
        ft = FloatingText(x, y, text, color)
        all_sprites.add(ft)
        floating_texts.add(ft)

    def reset_game():
        nonlocal score, ulti_meter, boss_level_count, boss, keyboard_control_active, next_boss_score, boss_active
        
        score = 0
        ulti_meter = 0
        boss_level_count = 0
        boss = None
        keyboard_control_active = True 
        next_boss_score = BOSS_SPAWN_SCORE
        boss_active = False
        
        all_sprites.empty()
        enemies.empty()
        bullets.empty()
        enemy_bullets.empty()
        powerups.empty()
        explosions.empty()
        floating_texts.empty()
        
        player.rect.centerx = WIDTH // 2
        player.rect.bottom = HEIGHT - 10
        player.lives = 3
        player.powerup_type = 'normal'
        player.shield_active = False # Reset shield
        player.hidden = False
        player.invincible = False 
        player.image.set_alpha(255)
        all_sprites.add(player)
        
        for _ in range(6): 
            spawn_enemy()
            
        play_music(music_normal)

    def play_music(path):
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(0.4)
            pygame.mixer.music.play(-1)
        except: pass

    if camera_available:
        camera_thread = threading.Thread(target=camera_thread_loop, daemon=True)
        camera_thread.start()
        
    play_music(music_normal)
    game_state = 'start' 
    running = True
    camera_on = False 
    player_target_x = GAME_W // 2
    ulti_meter = 0
    ULTI_THRESHOLD = 20 
    keyboard_control_active = True 
    current_gesture = "DIAM"
    
    BOSS_SPAWN_SCORE = 500
    next_boss_score = BOSS_SPAWN_SCORE
    boss_active = False
    
    # Fungsi Ulti
    def execute_ulti():
        nonlocal score, ulti_meter, next_boss_score, boss_active, boss, shake_intensity
        
        if ulti_meter < ULTI_THRESHOLD:
            return 
            
        bomb_sound.play() 
        ulti_meter = 0
        shake_intensity = 20 # Shake saat Ulti
        
        target_group = list(enemies)
        if boss_active and boss:
            target_group.append(boss)
            boss.hp -= 200 
            spawn_floating_text(boss.rect.centerx, boss.rect.y, "200", RED)

        cnt = len(target_group)
        for target in target_group:
            expl = Explosion(target.rect.center, scale=1.2)
            all_sprites.add(expl)
            expl_sound.play() 
            
            if target != boss:
                target.kill() 
        
        if boss_active:
            if boss.hp <= 0:
                score += 100
                next_boss_score += BOSS_SPAWN_SCORE
                boss_active = False
                boss.kill()
                boss = None
                play_music(music_normal)
                for bb in enemy_bullets: bb.kill()
                for _ in range(6): spawn_enemy()
        else:
            score += (cnt * 10)
            for _ in range(cnt): spawn_enemy()


    # --- Loop Utama ---
    while running:
        clock.tick(FPS)
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_k and camera_available:
                    camera_on = not camera_on
                    if not camera_on:
                         keyboard_control_active = True
                    else:
                         keyboard_control_active = False

                if game_state == 'start':
                    if event.key == pygame.K_RETURN:
                        reset_game()
                        game_state = 'play'
                    if event.key == pygame.K_q:
                        running = False

                elif game_state == 'play':
                    if event.key == pygame.K_p or event.key == pygame.K_ESCAPE:
                        game_state = 'pause'
                        pygame.mixer.music.pause()
                        
                    if event.key == pygame.K_b:
                        execute_ulti() 

                elif game_state == 'pause':
                    if event.key == pygame.K_RETURN:
                        game_state = 'play'
                        pygame.mixer.music.unpause()
                    if event.key == pygame.K_q:
                        game_state = 'start'
                        pygame.mixer.music.stop()
                        
                elif game_state == 'gameover':
                    if event.key == pygame.K_RETURN:
                        reset_game()
                        game_state = 'play'

        if game_state == 'play':
            current_gesture = "DIAM"
            keys = pygame.key.get_pressed()
            move_speed = 8 
            
            keyboard_input_this_frame = keys[pygame.K_LEFT] or keys[pygame.K_RIGHT]
            
            # 1. Kontrol Keyboard (Movement)
            if keys[pygame.K_LEFT]: 
                player_target_x = max(player_target_x - move_speed, player.rect.width // 2)
                keyboard_control_active = True
            if keys[pygame.K_RIGHT]: 
                player_target_x = min(player_target_x + move_speed, GAME_W - player.rect.width // 2)
                keyboard_control_active = True
            
            if keys[pygame.K_LEFT] or keys[pygame.K_RIGHT]:
                current_gesture = "BERGERAK"

            if keys[pygame.K_SPACE]:
                 player.shoot(all_sprites, bullets)
                 keyboard_control_active = True
                 current_gesture = "TEMBAK" 
            
            if keys[pygame.K_b] and ulti_meter >= ULTI_THRESHOLD:
                current_gesture = "ULTI"

            if not keyboard_input_this_frame and not keys[pygame.K_SPACE] and camera_on:
                 keyboard_control_active = False 

            # 2. Kontrol CV
            if camera_on and camera_available:
                with cv_lock:
                    frac = latest_cv.get('index_x_frac')
                    pinch = latest_cv.get('pinch_distance')
                    folded = latest_cv.get('index_folded') and latest_cv.get('middle_folded')
                    hand_present = latest_cv.get('hand_present')
                
                if hand_present: 
                    if not keyboard_control_active:
                        target = int(frac * GAME_W)
                        player_target_x = int(player_target_x * 0.2 + target * 0.8) 
                        
                        if current_gesture == "DIAM":
                             current_gesture = "BERGERAK" 
                    else:
                        if current_gesture == "DIAM":
                            current_gesture = "KEYBOARD PINNED"

                    if pinch is not None and pinch < 0.05:
                        player.shoot(all_sprites, bullets)
                        current_gesture = "TEMBAK"
                    
                    elif folded:
                        execute_ulti()
                        current_gesture = "ULTI"
                
                elif not hand_present and not keyboard_control_active:
                    current_gesture = "TANGAN TIDAK TERDETEKSI"
            
            player.update(player_target_x, all_sprites) 
            all_sprites.update() 
            powerups.update(player.rect.centerx)

            # --- Update Enemy Shooting ---
            for enemy in enemies:
                enemy.shoot(all_sprites, enemy_bullets)

            # --- BOSS SPAWN & LOGIC ---
            if score >= next_boss_score and not boss_active:
                for en in enemies: en.kill()
                boss = Boss()
                all_sprites.add(boss)
                boss_active = True
                shake_intensity = 15 # Shake saat Boss muncul
                play_music(music_boss)
            
            if boss_active and boss:
                now = pygame.time.get_ticks()
                if boss.state == 'fight':
                    
                    if now - boss.last_shot >= boss.shoot_delay:
                        boss.last_shot = now
                        boss_shoot_sound.play()

                        if boss.hp > boss.max_hp * 0.5:
                            boss.shoot_delay = 900 
                            bb = BossBullet(boss.rect.centerx, boss.rect.bottom, vy=6)
                            all_sprites.add(bb)
                            enemy_bullets.add(bb)

                        elif boss.hp > boss.max_hp * 0.25:
                            boss.shoot_delay = 700 
                            b1 = BossBullet(boss.rect.centerx, boss.rect.bottom, vy=7)
                            b2 = BossBullet(boss.rect.centerx - 20, boss.rect.bottom, vx=-2, vy=6)
                            b3 = BossBullet(boss.rect.centerx + 20, boss.rect.bottom, vx=2, vy=6)
                            all_sprites.add(b1, b2, b3)
                            enemy_bullets.add(b1, b2, b3)

                        else:
                            boss.shoot_delay = 400 
                            boss.wave_offset += 0.5
                            bullet_vx = math.sin(boss.wave_offset) * 3 
                            b_wave = BossBullet(boss.rect.centerx, boss.rect.bottom, vx=bullet_vx, vy=7)
                            all_sprites.add(b_wave)
                            enemy_bullets.add(b_wave)

                hits = pygame.sprite.spritecollide(boss, bullets, True)
                for hit in hits:
                    boss.hp -= hit.damage
                    expl_sound.play()
                    expl = Explosion(hit.rect.center)
                    all_sprites.add(expl)
                    spawn_floating_text(boss.rect.centerx, boss.rect.y + 50, str(hit.damage), ORANGE)

                    if boss.hp <= 0:
                        score += 100
                        next_boss_score += BOSS_SPAWN_SCORE
                        boss.kill()
                        boss = None
                        boss_active = False
                        ulti_meter = ULTI_THRESHOLD
                        shake_intensity = 30 # Mega shake saat boss mati
                        play_music(music_normal)

                        for _ in range(5):
                            ex = Explosion((random.randint(200,600), random.randint(100,300)))
                            all_sprites.add(ex)

                        for bb in enemy_bullets: bb.kill()
                        for _ in range(6): spawn_enemy()
                        break

            else:
                if len(enemies) < 6:
                    spawn_enemy()

            # --- COLLISIONS ---
            hits = pygame.sprite.groupcollide(bullets, enemies, True, False) # False agar tidak langsung mati (utk Tanker)
            for bullet, enemy_list in hits.items():
                bullet.kill()
                for en in enemy_list:
                    en.hp -= 1
                    en.hit() # Flash effect
                    spawn_floating_text(en.rect.centerx, en.rect.top, str(bullet.damage))
                    
                    # Spawn Hit Particles
                    for _ in range(3):
                        p = Particle(en.rect.centerx, en.rect.centery, YELLOW, 3, (random.uniform(-2,2), random.uniform(-2,2)), 10)
                        all_sprites.add(p)

                    if en.hp <= 0:
                        score += en.score_val
                        expl_sound.play()
                        expl = Explosion(en.rect.center)
                        all_sprites.add(expl)
                        ulti_meter = min(ULTI_THRESHOLD, ulti_meter + 1)
                        
                        if bullet.aoe_radius > 0:
                            aoe_expl = Explosion(en.rect.center, scale=2.0)
                            all_sprites.add(aoe_expl)
                            shake_intensity = 5 # Shake dikit
                            nearby_enemies = []
                            for other_en in enemies:
                                if get_pixel_dist(en.rect.center, other_en.rect.center) < bullet.aoe_radius and other_en not in enemy_list: 
                                    nearby_enemies.append(other_en)
                            for near_en in nearby_enemies:
                                near_en.kill()
                                score += 10
                                ulti_meter = min(ULTI_THRESHOLD, ulti_meter + 1)
                                ex = Explosion(near_en.rect.center)
                                all_sprites.add(ex)

                        if random.random() < 0.1:
                            ptype = random.choice(['double', 'spread', 'missile', 'shield'])
                            pu = PowerUp(en.rect.center, ptype)
                            all_sprites.add(pu)
                            powerups.add(pu)
                        
                        en.kill()

            hits = pygame.sprite.spritecollide(player, powerups, True)
            for pu in hits:
                bomb_sound.play()
                player.powerup(pu.type)
                spawn_floating_text(player.rect.centerx, player.rect.top - 20, pu.type.upper(), (0, 255, 255))

            if not player.invincible:
                hits_bullets = pygame.sprite.spritecollide(player, enemy_bullets, True, pygame.sprite.collide_circle)
                hits_enemies = pygame.sprite.spritecollide(player, enemies, True, pygame.sprite.collide_circle)
            
                if hits_bullets or hits_enemies:
                    if player.shield_active:
                         player.shield_active = False
                         player.invincible = True
                         player.invincible_timer = pygame.time.get_ticks()
                         player.invincible_duration = 2000 
                         expl_sound.play() 
                    else:
                        player_die_sound.play()
                        all_sprites.add(Explosion(player.rect.center))
                        player.lives -= 1
                        player.hide()
                        shake_intensity = 20 
                        player_target_x = WIDTH // 2 
                        if player.lives <= 0: game_state = 'gameover'
        
        # 3. Drawing
        # Parallax Background Logic
        bg_y += 2
        rel_y = bg_y % background_img.get_height()
        game_surface.blit(background_img, (0, rel_y - background_img.get_height()))
        if rel_y < HEIGHT:
            game_surface.blit(background_img, (0, rel_y))
        
        if player.invincible:
            temp_sprites = all_sprites.copy()
            temp_sprites.remove(player)
            temp_sprites.draw(game_surface)
            game_surface.blit(player.image, player.rect)
        else:
            all_sprites.draw(game_surface)
            
        # Gambar Lingkaran Shield
        if player.shield_active and not player.hidden:
             pygame.draw.circle(game_surface, (0, 255, 255), player.rect.center, player.radius + 10, 2)


        if game_state == 'play':
            # --- Panel HUD Kiri Atas ---
            draw_hud_panel_modern(game_surface, 10, 10, 250, 100, UI_BG)
            draw_text(game_surface, f"SCORE: {score}", 24, 20, 20, NEON_BLUE, font_key='Orbitron')
            draw_text(game_surface, f"BEST: {highscore}", 18, 20, 50, WHITE, font_key='Orbitron')
            draw_text(game_surface, "ULTI METER (B/Lipat Jari)", 12, 20, 80, font_key='Oxanium')
            draw_bar_modern(game_surface, 20, 93, 220, 10, ulti_meter, ULTI_THRESHOLD, (0, 200, 255), (0, 100, 255))
            
            # --- Panel HUD Kanan Atas ---
            draw_hud_panel_modern(game_surface, WIDTH - 350, 10, 340, 100, UI_BG) 
            draw_text(game_surface, "LIVES:", 18, WIDTH - 340, 18, WHITE, font_key='Oxanium')
            x = WIDTH - 200
            for i in range(player.lives):
                x -= 30
                game_surface.blit(player_mini_img, (x, 15))
            
            weapon_text = "SHIELD" if player.shield_active else player.powerup_type.upper()
            w_color = (0, 255, 255) if player.shield_active else YELLOW
            draw_text(game_surface, f"WEAPON: {weapon_text}", 18, WIDTH - 340, 45, w_color, font_key='Oxanium')
            
            mode_status = "KEYBOARD"
            mode_color = NEON_BLUE
            if camera_available:
                if camera_on:
                    mode_status = "TANGAN" 
                    mode_color = (0, 255, 0)
                else:
                    mode_status = "KEYBOARD" 
            else:
                mode_status = "KEYBOARD" 
            
            draw_text(game_surface, f"MODE: {mode_status}", 18, WIDTH - 180, 18, mode_color, font_key='Oxanium')
            action_text = f"Gerakan: {current_gesture}"
            draw_text(game_surface, action_text, 18, WIDTH - 180, 45, WHITE, font_key='Oxanium')

            if boss_active and boss:
                bar_w = 400
                bar_h = 20
                hp_percent = boss.hp / boss.max_hp
                if hp_percent > 0.50: 
                    hp_label = "BOSS PHASE 1: NORMAL PATTERN"
                    bar_color_start = (0, 200, 0) 
                    bar_color_end = (0, 150, 0)
                elif hp_percent > 0.25:
                    hp_label = "BOSS PHASE 2: AGGRESSIVE PATTERN"
                    bar_color_start = (255, 150, 0)
                    bar_color_end = (200, 100, 0)
                else:
                    hp_label = "BOSS PHASE 3: ENRAGED!"
                    bar_color_start = (255, 0, 255)
                    bar_color_end = (150, 0, 200)

                draw_text_center(game_surface, hp_label, 14, WIDTH//2, 102, WHITE, font_key='Oxanium')
                draw_bar_modern(game_surface, WIDTH//2 - bar_w//2, 120, bar_w, bar_h, boss.hp, boss.max_hp, bar_color_start, bar_color_end)
                hp_value_text = f"HP: {int(boss.hp)} / {boss.max_hp}"
                draw_text_center(game_surface, hp_value_text, 16, WIDTH//2, 122, BLACK, font_key='Oxanium')
                
            cursor_color = (0, 255, 0) if current_gesture == "TEMBAK" else (255, 0, 0) if current_gesture == "ULTI" else WHITE
            if not player.hidden:
                pygame.draw.circle(game_surface, cursor_color, (int(player_target_x), player.rect.centery), 10, 2)
                
            hint_cv = "Jari Telunjuk/Panah"
            hint_shoot = "Cubit/Spasi"
            hint_ulti = "Lipat Jari/B"
            draw_text_center(game_surface, f"Gerak: {hint_cv} | Tembak: {hint_shoot} | Ulti: {hint_ulti} | Pause: P/Esc", 18, WIDTH//2, HEIGHT - 30, WHITE, font_key='Oxanium')

        elif game_state == 'start':
            game_surface.fill(BLACK)
            # Parallax di menu start juga
            bg_y += 1
            rel_y = bg_y % background_img.get_height()
            game_surface.blit(background_img, (0, rel_y - background_img.get_height()))
            if rel_y < HEIGHT:
                game_surface.blit(background_img, (0, rel_y))

            draw_text_center(game_surface, "BLASTER CV", 64, GAME_W//2, GAME_H//4, NEON_BLUE, font_key='RussoOne')
            draw_text_center(game_surface, f"High Score: {highscore}", 24, GAME_W//2, GAME_H//2 - 20, WHITE, font_key='Orbitron')
            draw_text_center(game_surface, "Tekan ENTER untuk Mulai", 30, GAME_W//2, GAME_H * 4/5, YELLOW, font_key='Oxanium')
            draw_text_center(game_surface, "Tekan Q untuk Keluar Game", 24, GAME_W//2, GAME_H * 4/5 + 40, RED, font_key='Oxanium')
            
            mode_text = "MODE KONTROL: KEYBOARD"
            toggle_text = "Tekan K untuk Uji Coba Kamera"
            mode_color = NEON_BLUE
            if not camera_available:
                toggle_text = "Kamera Tidak Terdeteksi"
                mode_color = RED
            
            draw_hud_panel_modern(game_surface, GAME_W - 300, 10, 290, 70, UI_BG)
            draw_text(game_surface, mode_text, 18, GAME_W - 280, 20, mode_color, font_key='Oxanium')
            draw_text(game_surface, toggle_text, 18, GAME_W - 280, 45, YELLOW, font_key='Oxanium')
        
        elif game_state == 'pause':
            trans_surface = pygame.Surface((GAME_W, GAME_H), pygame.SRCALPHA)
            trans_surface.fill((0, 0, 0, 150)) 
            game_surface.blit(trans_surface, (0, 0))
            draw_text_center(game_surface, "PAUSED", 60, GAME_W//2, GAME_H//2 - 100, YELLOW, font_key='RussoOne')
            draw_text_center(game_surface, "Tekan ENTER untuk Lanjutkan", 30, GAME_W//2, GAME_H//2, WHITE, font_key='Oxanium')
            draw_text_center(game_surface, "Tekan Q untuk Kembali ke Start Screen", 30, GAME_W//2, GAME_H//2 + 60, RED, font_key='Oxanium')

        elif game_state == 'gameover':
            trans_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            trans_surface.fill((0, 0, 0, 180)) 
            game_surface.blit(trans_surface, (0, 0))
            draw_text_center(game_surface, "GAME OVER", 50, GAME_W//2, GAME_H//2, (255, 50, 50), font_key='RussoOne')
            draw_text_center(game_surface, f"FINAL SCORE: {score}", 30, GAME_W//2, GAME_H//2 + 60, WHITE, font_key='Orbitron')
            draw_text_center(game_surface, "Tekan ENTER untuk Restart", 30, GAME_W//2, GAME_H//2 + 120, YELLOW, font_key='Oxanium')

        if score > highscore:
            highscore = score
            with open(HIGH_SCORE_FILE, 'w') as f: f.write(str(highscore))

        # Update Shake Logic
        shake_offset = (0, 0)
        if shake_intensity > 0:
             shake_intensity -= 1
             shake_offset = (random.randint(-int(shake_intensity), int(shake_intensity)), random.randint(-int(shake_intensity), int(shake_intensity)))

        blit_centered(shake_offset)
        pygame.display.flip()

    cv_running.clear()
    if camera_thread is not None and camera_thread.is_alive():
        camera_thread.join(timeout=1.0)
    try: cap.release()
    except: pass
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
import pygame
import os
import math
import random
import struct
import wave

# --- Konfigurasi Path ---
# Script ini akan membuat folder img dan snd di lokasi script ini berada
game_folder = os.path.dirname(os.path.abspath(__file__))
img_folder = os.path.join(game_folder, "img")
snd_folder = os.path.join(game_folder, "snd")

os.makedirs(img_folder, exist_ok=True)
os.makedirs(snd_folder, exist_ok=True)

pygame.init()

def save_surf(surf, filename):
    path = os.path.join(img_folder, filename)
    pygame.image.save(surf, path)
    print(f"[IMG] Berhasil membuat: {filename}")

# ==========================================
# 1. GENERATOR GAMBAR (PNG)
# ==========================================

# --- A. BOSS (boss.png) ---
# Bentuk: Kapal induk alien besar warna ungu gelap dengan inti merah
boss_w, boss_h = 160, 100
boss_surf = pygame.Surface((boss_w, boss_h), pygame.SRCALPHA)
# Sayap utama
pygame.draw.polygon(boss_surf, (70, 0, 70), [
    (0, 20), (boss_w//2, 0), (boss_w, 20), 
    (boss_w - 20, boss_h), (20, boss_h)
])
# Detail metalik
pygame.draw.rect(boss_surf, (100, 100, 120), (40, 40, 80, 40))
# Inti Energi (Mata Boss)
pygame.draw.circle(boss_surf, (200, 0, 0), (boss_w//2, boss_h//2), 15)
pygame.draw.circle(boss_surf, (255, 100, 100), (boss_w//2, boss_h//2), 8)
save_surf(boss_surf, "boss.png")

# --- B. PELURU BOSS (boss_bullet.png) ---
# Bentuk: Bola energi merah berputar
bb_size = 24
bb_surf = pygame.Surface((bb_size, bb_size), pygame.SRCALPHA)
pygame.draw.circle(bb_surf, (100, 0, 0), (bb_size//2, bb_size//2), bb_size//2)
pygame.draw.circle(bb_surf, (255, 50, 0), (bb_size//2, bb_size//2), bb_size//2 - 4)
save_surf(bb_surf, "boss_bullet.png")

# --- C. ICON POWER UP (Drop Items) ---
def create_icon(color, letter, filename):
    s = 32
    surf = pygame.Surface((s, s), pygame.SRCALPHA)
    # Kotak bersinar
    pygame.draw.rect(surf, color, (2, 2, s-4, s-4), border_radius=6)
    pygame.draw.rect(surf, (255, 255, 255), (2, 2, s-4, s-4), 2, border_radius=6)
    # Huruf
    font = pygame.font.SysFont("arial", 22, bold=True)
    txt = font.render(letter, True, (255, 255, 255))
    surf.blit(txt, (s//2 - txt.get_width()//2, s//2 - txt.get_height()//2))
    save_surf(surf, filename)

create_icon((0, 150, 255), "D", "pu_double.png")   # Biru: Double
create_icon((0, 200, 50), "S", "pu_spread.png")    # Hijau: Spread
create_icon((255, 100, 0), "M", "pu_missile.png")  # Oranye: Missile

# --- D. PELURU PLAYER BARU ---

# 1. Bullet Double (Mirip laser biru)
bd_surf = pygame.Surface((10, 24), pygame.SRCALPHA)
pygame.draw.rect(bd_surf, (0, 200, 255), (0, 0, 10, 24), border_radius=4)
pygame.draw.rect(bd_surf, (200, 255, 255), (3, 3, 4, 18), border_radius=2)
save_surf(bd_surf, "bullet_double.png")

# 2. Bullet Spread (Bola kecil hijau tajam)
bs_surf = pygame.Surface((14, 14), pygame.SRCALPHA)
pygame.draw.circle(bs_surf, (50, 255, 50), (7, 7), 6)
save_surf(bs_surf, "bullet_spread.png")

# 3. Bullet Missile (Roket Oranye Besar)
bm_w, bm_h = 18, 36
bm_surf = pygame.Surface((bm_w, bm_h), pygame.SRCALPHA)
# Body
pygame.draw.rect(bm_surf, (200, 200, 200), (4, 4, 10, 24))
# Moncong (Warhead)
pygame.draw.polygon(bm_surf, (255, 50, 0), [(4, 4), (14, 4), (9, 0)])
# Sirip
pygame.draw.polygon(bm_surf, (100, 100, 100), [(4, 20), (0, 30), (4, 28)]) # Sirip kiri
pygame.draw.polygon(bm_surf, (100, 100, 100), [(14, 20), (18, 30), (14, 28)]) # Sirip kanan
# Api ekor
pygame.draw.circle(bm_surf, (255, 200, 0), (9, 32), 4)
save_surf(bm_surf, "bullet_missile.png")


# ==========================================
# 2. GENERATOR SUARA (WAV)
# ==========================================

def save_wav(filename, data, rate=22050):
    path = os.path.join(snd_folder, filename)
    with wave.open(path, 'w') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(data)
    print(f"[SND] Berhasil membuat: {filename}")

def generate_wave(freq_start, freq_end, duration, vol=0.5, type='saw'):
    rate = 22050
    frames = int(rate * duration)
    data = bytearray()
    
    for i in range(frames):
        t = i / frames
        freq = freq_start + (freq_end - freq_start) * t
        
        # Generator gelombang manual
        phase = (i * freq / rate) * 2 * math.pi
        
        if type == 'sin':
            value = math.sin(phase)
        elif type == 'square':
            value = 1.0 if math.sin(phase) > 0 else -1.0
        elif type == 'saw':
            value = (phase % (2 * math.pi)) / math.pi - 1
        elif type == 'noise':
            value = random.uniform(-1, 1)
            
        # Envelope (Fade out)
        if t > 0.8:
            value *= (1.0 - t) * 5
            
        # Konversi ke 16-bit integer
        packed = struct.pack('<h', int(value * 32767 * vol))
        data += packed
    return data

# --- A. Suara Tembakan Boss (Berat & Rendah) ---
# Suara sawtooth menurun pitch-nya
boss_shoot_data = generate_wave(200, 50, 0.6, vol=0.6, type='saw')
save_wav("boss_shoot.wav", boss_shoot_data)

# --- B. Musik Boss (Loop Pendek Menegangkan) ---
# Kita buat sequence nada sederhana
music_data = bytearray()
rate = 22050
bpm = 120
beat_len = 60 / bpm
# Nada bass: A2, A2, C3, A2 (Frekuensi rendah)
notes = [110, 110, 0, 130, 110, 0, 98, 98] 

for note in notes * 4: # Loop 4 bar
    if note == 0:
        chunk = generate_wave(0, 0, beat_len/2, vol=0, type='sin')
    else:
        chunk = generate_wave(note, note, beat_len/2, vol=0.3, type='square')
    music_data += chunk

save_wav("boss_music.wav", music_data)

print("\n--- SELESAI! ASET DIBUAT ---")
print("Sekarang jalankan file game utama (blaster_polished.py).")
pygame.quit()
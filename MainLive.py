import cv2
from ultralytics import YOLO
import numpy as np
import sqlite3
import time
from datetime import datetime
from collections import Counter

# ==========================================
# CONFIGURARE
# ==========================================
VEHICLE_CLASSES = [2, 3, 5, 7] 
COOLDOWN_TIMP = 5.0 # Timpul în care bariera stă "deschisă" și nu mai citește

# PUNE AICI NUMELE VIDEO-ULUI TĂU (sau 0 pentru Webcam)
VIDEO_SOURCE = "test_video1.mp4" 

dict_litera_in_cifra = {
    'O': '0', 'I': '1', 'J': '1', 'L': '1', 
    'Z': '7', 'S': '5', 'G': '6', 'B': '8', 
    'D': '0', 'Q': '0', 'T': '7', 'Y': '7',
    'U': '0', 'A': '4'
}

dict_cifra_in_litera = {
    '0': 'O', '1': 'I', '2': 'Z', '5': 'S', 
    '6': 'G', '8': 'B', '4': 'A', '7': 'Z'
}

# ==========================================
# FUNCȚII CULOARE & FORMAT
# ==========================================
def detecteaza_culoare_placuta(img_placuta):
    if img_placuta is None or img_placuta.size == 0: return 'NEGRU'
    hsv = cv2.cvtColor(img_placuta, cv2.COLOR_BGR2HSV)
    
    mask_red = cv2.inRange(hsv, np.array([0, 70, 50]), np.array([10, 255, 255])) + \
               cv2.inRange(hsv, np.array([160, 70, 50]), np.array([180, 255, 255]))
    mask_green = cv2.inRange(hsv, np.array([35, 50, 50]), np.array([85, 255, 255]))
    
    total_pixels = img_placuta.shape[0] * img_placuta.shape[1]
    if total_pixels == 0: return 'NEGRU'
    
    if (cv2.countNonZero(mask_red) / total_pixels) > 0.025: return 'ROSU'
    if (cv2.countNonZero(mask_green) / total_pixels) > 0.025: return 'VERDE'
    return 'NEGRU'

def aplica_format_romanesc(text_brut, tip_culoare='NEGRU'):
    text = "".join([c for c in text_brut.upper() if c.isalnum()])
    for p in ["RO", "R0", "80", "BO", "RQ", "RB"]: 
        if text.startswith(p): text = text[2:]; break
    if len(text) < 4: return text 
    text_list = list(text)
    if text_list[0] == 'J': text_list[0] = 'T'
    
    e_bucuresti = (text_list[0] == 'B') and (len(text_list) > 1 and (text_list[1].isdigit() or text_list[1] in dict_cifra_in_litera))
    limit = 1 if e_bucuresti else 2
    
    for i in range(min(limit, len(text_list))):
        if text_list[i].isdigit() and text_list[i] in dict_cifra_in_litera:
            text_list[i] = dict_cifra_in_litera[text_list[i]]
            
    if tip_culoare == 'ROSU':
        for i in range(limit, len(text_list)):
            if text_list[i].isalpha() and text_list[i] in dict_litera_in_cifra:
                text_list[i] = dict_litera_in_cifra[text_list[i]]
    else:
        for i in range(len(text_list)-3, len(text_list)):
            if i < len(text_list) and text_list[i].isdigit():
                text_list[i] = dict_cifra_in_litera.get(text_list[i], text_list[i])
        for i in range(limit, len(text_list)-3):
            if i < len(text_list):
                if text_list[i] == 'Z': text_list[i] = '7' if "".join(text_list).startswith("SB") else '2'
                elif text_list[i].isalpha(): text_list[i] = dict_litera_in_cifra.get(text_list[i], text_list[i])
                
    return "".join(text_list)

# ==========================================
# FUNCȚII DB & GEOMETRIE
# ==========================================
def log_eveniment(numar, actiune):
    try:
        conn = sqlite3.connect('parcare.db')
        cursor = conn.cursor()
        acum = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO istoric (numar, actiune, data_ora) VALUES (?, ?, ?)", (numar, actiune, acum))
        conn.commit()
        conn.close()
    except: pass

def verifica_acces(numar_placuta, tip_culoare='NEGRU'):
    acum_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        conn_db = sqlite3.connect('parcare.db')
        cursor = conn_db.cursor()
        
        # 1. Verificăm dacă mașina se află deja în parcare
        cursor.execute("SELECT * FROM parcare_curenta WHERE numar = ?", (numar_placuta,))
        stare_parcare = cursor.fetchone()
        
        # ==========================================
        # LOGICA DE INTRARE (Mașina NU este în parcare)
        # ==========================================
        if not stare_parcare:
            # Verificăm dacă are abonament valid
            cursor.execute("SELECT data_expirare FROM autorizati WHERE numar = ?", (numar_placuta,))
            rez_abonat = cursor.fetchone()
            
            is_abonat_valid = False
            if rez_abonat:
                data_exp = datetime.strptime(rez_abonat[0], "%Y-%m-%d")
                if datetime.now() < data_exp:
                    is_abonat_valid = True
            
            if is_abonat_valid or tip_culoare == 'VERDE':
                # Intră ca Abonat / Auto Electric
                cursor.execute("INSERT INTO parcare_curenta (numar, ora_intrare, tip, status_plata) VALUES (?, ?, 'ABONAMENT', 1)", (numar_placuta, acum_str))
                cursor.execute("INSERT INTO istoric (numar, actiune, data_ora) VALUES (?, 'INTRARE ABONAT', ?)", (numar_placuta, acum_str))
                conn_db.commit()
                conn_db.close()
                return True, "Bariera se ridică - INTRARE ABONAT"
            else:
                # Intră ca Vizitator (Trebuie să plătească la ieșire)
                cursor.execute("INSERT INTO parcare_curenta (numar, ora_intrare, tip, status_plata) VALUES (?, ?, 'VIZITATOR', 0)", (numar_placuta, acum_str))
                cursor.execute("INSERT INTO istoric (numar, actiune, data_ora) VALUES (?, 'INTRARE VIZITATOR', ?)", (numar_placuta, acum_str))
                conn_db.commit()
                conn_db.close()
                return True, "Bariera se ridică - INTRARE VIZITATOR"

        # ==========================================
        # LOGICA DE IEȘIRE (Mașina ESTE deja în parcare)
        # ==========================================
        else:
            tip_client = stare_parcare[2] # 'ABONAMENT' sau 'VIZITATOR'
            status_plata = stare_parcare[3] # 0 sau 1
            ora_limita_str = stare_parcare[4]
            
            if tip_client == 'ABONAMENT':
                # Abonații ies oricând gratuit
                cursor.execute("DELETE FROM parcare_curenta WHERE numar = ?", (numar_placuta,))
                cursor.execute("INSERT INTO istoric (numar, actiune, data_ora) VALUES (?, 'IESIRE ABONAT', ?)", (numar_placuta, acum_str))
                conn_db.commit()
                conn_db.close()
                return True, "Drum bun! - IESIRE ABONAT"
            else:
                # Vizitatorii pot ieși doar dacă au plătit și sunt în intervalul de 5 minute
                if status_plata == 1 and ora_limita_str:
                    ora_limita = datetime.strptime(ora_limita_str, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() <= ora_limita:
                        cursor.execute("DELETE FROM parcare_curenta WHERE numar = ?", (numar_placuta,))
                        cursor.execute("INSERT INTO istoric (numar, actiune, data_ora) VALUES (?, 'IESIRE VIZITATOR', ?)", (numar_placuta, acum_str))
                        conn_db.commit()
                        conn_db.close()
                        return True, "Drum bun! - IESIRE VIZITATOR"
                    else:
                        # A plătit dar a depășit cele 5 minute
                        cursor.execute("UPDATE parcare_curenta SET status_plata = 0 WHERE numar = ?", (numar_placuta,))
                        cursor.execute("INSERT INTO istoric (numar, actiune, data_ora) VALUES (?, 'IESIRE RESPINSA (TIMP EXPIRAT)', ?)", (numar_placuta, acum_str))
                        conn_db.commit()
                        conn_db.close()
                        return False, "PLATA EXPIRATA (A depasit 5 min)"
                else:
                    # Nu a plătit deloc
                    cursor.execute("INSERT INTO istoric (numar, actiune, data_ora) VALUES (?, 'IESIRE RESPINSA (NEPLATIT)', ?)", (numar_placuta, acum_str))
                    conn_db.commit()
                    conn_db.close()
                    return False, "ACCES RESPINS! Necesită plată la terminal."
                    
    except Exception as e:
        return False, f"EROARE SISTEM: {e}"

def resize_pentru_afisare(img, target_width=960):
    if img is None: return None
    h, w = img.shape[:2]
    if w <= target_width: return img
    factor = target_width / w
    new_h = int(h * factor)
    return cv2.resize(img, (target_width, new_h), interpolation=cv2.INTER_AREA)

def indreapta_dupa_litere(img, model_chars):
    if img is None or img.size == 0: return img
    h, w = img.shape[:2]
    img_detect = cv2.resize(img, (640, int(h * (640 / w))))
    results = model_chars(img_detect, conf=0.15, verbose=False)
    chars = []
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            chars.append({'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})
    if len(chars) < 2: return img_detect
    chars.sort(key=lambda k: k['x1'])
    if len(chars) > 2 and (chars[1]['x1'] - chars[0]['x2']) > (chars[1]['x2'] - chars[1]['x1']) * 2: chars.pop(0)
    first, last = chars[0], chars[-1]
    scale_x, scale_y = w / 640, h / img_detect.shape[0]
    pad_x, pad_y = 25 * scale_x, 35 * scale_y
    src_pts = np.float32([
        [first['x1']*scale_x - pad_x, first['y1']*scale_y - pad_y], 
        [last['x2']*scale_x + pad_x,  last['y1']*scale_y - pad_y],  
        [last['x2']*scale_x + pad_x,  last['y2']*scale_y + pad_y],  
        [first['x1']*scale_x - pad_x, first['y2']*scale_y + pad_y]
    ])
    dst_w, dst_h = int(120 * 4.2), 120
    dst_pts = np.float32([[0, 0], [dst_w, 0], [dst_w, dst_h], [0, dst_h]])
    try:
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(img, M, (dst_w, dst_h))
        return cv2.resize(warped, (640, int(640 * (dst_h/dst_w))), interpolation=cv2.INTER_CUBIC)
    except: return img_detect

# ==========================================
# MAIN LIVE (VOTING SYSTEM)
# ==========================================
def main():
    print(f"--- RULARE PE VIDEO: {VIDEO_SOURCE} (Sistem Expert RAW & Votare) ---")
    
    model_auto = YOLO('yolov8n.pt')
    try: 
        model_plate = YOLO('placute.pt')
        model_chars = YOLO('caractere.pt')
    except Exception as e: 
        print(f"EROARE: Lipsesc modelele! Detalii: {e}")
        return

    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        print(f"EROARE: Nu pot deschide '{VIDEO_SOURCE}'.")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0: fps = 30 
    delay_ms = int(1000 / fps) 

    last_read = 0
    display_msg = "SCANARE..."
    display_col = (200, 200, 200)
    
    istoric_voturi = [] # MEMORIA PENTRU SISTEMUL DE VOTARE

    while True:
        ret, frame = cap.read()
        if not ret: 
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        # ---> LOGICA DE COOLDOWN (Bariera Deschisă) <---
        if time.time() - last_read < COOLDOWN_TIMP:
            istoric_voturi.clear() # Cât bariera e deschisă, golim memoria
            cv2.rectangle(frame, (0,0), (frame.shape[1], 60), display_col, -1)
            cv2.putText(frame, display_msg, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2)
            rem = int(COOLDOWN_TIMP - (time.time() - last_read))
            cv2.putText(frame, f"Wait: {rem}s", (frame.shape[1]-150, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 1)
            
            frame_display = resize_pentru_afisare(frame)
            cv2.imshow("Parcare Video Live", frame_display)
            if cv2.waitKey(delay_ms) == ord('q'): break
            continue

        # ---> 1. DETECȚIE VEHICULE <---
        results = model_auto(frame, conf=0.5, verbose=False)
        vehicule_detectate = []
        
        for r in results:
            for box in r.boxes:
                if int(box.cls[0]) in VEHICLE_CLASSES:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    aria = (x2-x1)*(y2-y1)
                    vehicule_detectate.append({'box': (x1, y1, x2, y2), 'aria': aria})

        # ---> 2. FILTRARE CEA MAI MARE MAȘINĂ <---
        masina_tinta = None
        if vehicule_detectate:
            vehicule_detectate.sort(key=lambda k: k['aria'], reverse=True)
            masina_tinta = vehicule_detectate[0] 

        detected_flag = False

        if masina_tinta:
            x1, y1, x2, y2 = masina_tinta['box']
            aria = masina_tinta['aria']
            
            cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,255), 2)

            if aria > 20000: # Procesăm doar dacă mașina a ajuns destul de aproape de barieră
                detected_flag = True
                crop_auto = frame[y1:y2, x1:x2]
                
                # ---> 3. DETECȚIE PLĂCUȚĂ <---
                rez_p = model_plate(crop_auto, conf=0.25, verbose=False)
                for rp in rez_p:
                    if len(rp.boxes) > 0:
                        boxes_sorted = sorted(rp.boxes, key=lambda b: b.conf[0], reverse=True)
                        px1, py1, px2, py2 = map(int, boxes_sorted[0].xyxy[0])
                        crop_p = crop_auto[py1:py2, px1:px2]
                        
                        tip_culoare = detecteaza_culoare_placuta(crop_p)
                        p_proc = indreapta_dupa_litere(crop_p, model_chars)
                        
                        # ---> 4. OCR & EXCLUDERE BANDA UE <---
                        rc = model_chars(p_proc, conf=0.20, verbose=False)
                        
                        dets_brute = []
                        w_placuta = p_proc.shape[1]
                        zona_albastra = w_placuta * 0.12 # Limita pentru banda UE
                        
                        for b in rc[0].boxes:
                            cx1_c, cy1_c, cx2_c, cy2_c = map(int, b.xyxy[0])
                            centru_x = (cx1_c + cx2_c) / 2
                            
                            if centru_x > zona_albastra:
                                dets_brute.append({
                                    'litera': model_chars.names[int(b.cls[0])],
                                    'x': cx1_c, 'w': cx2_c-cx1_c, 'h': cy2_c-cy1_c,
                                    'cy': (cy1_c+cy2_c)//2, 'conf': float(b.conf[0])
                                })
                        
                        dets_filtrate_y = []
                        if len(dets_brute) > 0:
                            medie_h = np.mean([d['h'] for d in dets_brute])
                            medie_cy = np.mean([d['cy'] for d in dets_brute])
                            prag_y = medie_h * 0.5
                            for det in dets_brute:
                                if abs(det['cy'] - medie_cy) < prag_y:
                                    dets_filtrate_y.append(det)
                        else: 
                            dets_filtrate_y = dets_brute
                            
                        dets_filtrate_y.sort(key=lambda k: k['x'])

                        final = []
                        for d in dets_filtrate_y:
                            if not final: final.append(d); continue
                            if (d['x'] - final[-1]['x']) < min(d['w'], final[-1]['w']) * 0.3:
                                if d['conf'] > final[-1]['conf']: final[-1] = d
                            else: final.append(d)
                        
                        text_brut = "".join([x['litera'] for x in final])
                        text = aplica_format_romanesc(text_brut, tip_culoare)
                        
                        # ---> 5. SISTEMUL DE VOTARE <---
                        if len(text) >= 5: # Un număr RO valid are minim 5 caractere
                            istoric_voturi.append({'numar': text, 'culoare': tip_culoare})
                            
                            # Păstrăm în memorie doar ultimele 15 detecții (o jumătate de secundă de video)
                            if len(istoric_voturi) > 15:
                                istoric_voturi.pop(0)
                                
                            # Căutăm cel mai frecvent număr din memorie
                            counter = Counter([v['numar'] for v in istoric_voturi])
                            cel_mai_frecvent, frecventa = counter.most_common(1)[0]
                            
                            # Dacă sistemul l-a văzut la fel de 5 ori, luăm decizia finală
                            if frecventa >= 5:
                                culoare_castigatoare = next(v['culoare'] for v in reversed(istoric_voturi) if v['numar'] == cel_mai_frecvent)
                                acces, info = verifica_acces(cel_mai_frecvent, culoare_castigatoare)
                                
                                prefix = "[ECO] " if culoare_castigatoare == 'VERDE' else "[PROV] " if culoare_castigatoare == 'ROSU' else ""
                                display_msg = f"{prefix}{cel_mai_frecvent} - {info}"
                                display_col = (0, 180, 0) if acces else (0, 0, 200)
                                
                                last_read = time.time() # Declanșăm bariera
                                print(f"[LOG DB] {display_msg} (Confirmat din {frecventa} cadre)")

                                # Salvăm o captură de ecran cu momentul deciziei
                                frame_snapshot = frame.copy()
                                cv2.rectangle(frame_snapshot, (x1,y1), (x2,y2), display_col, 4)
                                cv2.putText(frame_snapshot, display_msg, (x1, y1-20), cv2.FONT_HERSHEY_SIMPLEX, 1.0, display_col, 3)
                                
                                snapshot_display = resize_pentru_afisare(frame_snapshot)
                                cv2.imshow("CAPTURA DECIZIE", snapshot_display)
                                
                                istoric_voturi.clear() # Golim memoria

        if not detected_flag:
            # Dacă mașina pleacă din cadru (sau nu e destul de aproape), golim memoria
            istoric_voturi.clear() 
            cv2.putText(frame, "CAUTARE VEHICUL...", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)

        frame_display = resize_pentru_afisare(frame)
        cv2.imshow("Parcare Video Live", frame_display)
        
        if cv2.waitKey(delay_ms) == ord('q'): break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
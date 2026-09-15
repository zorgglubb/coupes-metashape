"""
coupe_bloc_pdf.py  v1.1
=============================================================
Script Anaconda — Planche PDF A3 Portrait pour bloc d'architecture.

Mise en page A3 Portrait (29.7 x 42 cm) :

  ┌────────────────┬──────────────────────┐
  │  [VUE DE FACE] │  [VUE DE DESSUS]     │
  ├────────────────┼──────────────────────┤
  │  [V.GAUCHE]    │  [COUPE — hachures]  │
  ├────────────────┼──────────────────────┤
  │  [V.DROITE]    │  [VUE DE DOS]        │
  │                ├──────────────────────┤
  │                │  [VUE DE DESSOUS]    │
  └────────────────┴──────────────────────┘
  ─── Titre / echelle / date ─────────────

Coupe : fond blanc, hachures noires 45 deg, contour noir.
Mires : 4 divisions normalisees en cm pour chaque vue.
Echelle unique pour toutes les vues (laterale + plan).

Usage :
    python coupe_bloc_pdf.py <fichier.meta.txt>
    Sans argument : dialogue tkinter
"""

import os, sys, traceback


def find_meta_path():
    if len(sys.argv) > 1:
        return sys.argv[1]
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw()
        path = filedialog.askopenfilename(
            title="Choisir le fichier .meta.txt",
            filetypes=[("Meta", "*.meta.txt"), ("Tous", "*.*")])
        root.destroy()
        return path or None
    except Exception:
        return None


def meta_base(p):
    b = p
    for ext in ('.meta.txt', '.meta', '.txt'):
        if b.lower().endswith(ext):
            b = b[:-len(ext)]; break
    return b


def read_meta(path):
    d = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '=' in line:
                k, v = line.split('=', 1)
                d[k.strip()] = v.strip()
    return d


# ===========================================================================
def run(meta_path, log):

    def pr(s=''):
        print(s); log.write(s + '\n'); log.flush()

    pr("=" * 60)
    pr("coupe_bloc_pdf.py  v1.1  —  A3 Portrait, hachures")
    pr("meta : " + meta_path)
    pr("=" * 60)

    try:
        import math
        pr("  stdlib OK")
    except Exception as e:
        pr("ERREUR : " + str(e)); raise

    try:
        import numpy as np
        pr("  numpy  " + np.__version__)
    except ImportError:
        pr("ERREUR numpy manquant.  pip install numpy"); raise

    try:
        import cv2
        pr("  opencv " + cv2.__version__)
    except ImportError:
        pr("ERREUR opencv manquant. pip install opencv-python"); raise

    try:
        from PIL import Image
        import PIL
        pr("  Pillow " + PIL.__version__)
    except ImportError:
        pr("ERREUR Pillow manquant.  pip install Pillow"); raise

    try:
        from reportlab.lib.pagesizes import A3
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.units import cm
        from reportlab.lib.utils import ImageReader
        import reportlab
        pr("  reportlab " + reportlab.Version)
    except ImportError:
        pr("ERREUR reportlab manquant. pip install reportlab"); raise

    pr("")

    # -------------------------------------------------------------------
    # Constantes page
    # -------------------------------------------------------------------
    PW = 29.7   # cm  (A3 Portrait largeur)
    PH = 42.0   # cm  (A3 Portrait hauteur)
    MAR  = 1.0
    GAP  = 0.45
    TTL  = 0.85   # bandeau titre
    MIR  = 1.45   # zone mire
    LBL  = 0.38   # zone label

    SCALES = [1,2,3,4,5,10,20,50,100,200,500,1000]

    def yp(y):
        return (PH - y) * cm

    def auto_scale(real_m, max_cm):
        if max_cm <= 0 or real_m <= 0:
            return 1.0, 1
        for d in SCALES:
            if real_m / d * 100.0 <= max_cm:
                return 1.0/d, d
        r = max_cm / (real_m * 100.0)
        return r, max(1, int(round(1.0/r)))

    def pcm(real_m, ratio):   # metres -> cm papier
        return real_m * 100.0 * ratio

    # -------------------------------------------------------------------
    # Lecture meta
    # -------------------------------------------------------------------
    pr("Lecture meta...")
    meta = read_meta(meta_path)

    def mf(k, dv=0.1):
        try: return float(meta.get(k, dv))
        except: return float(dv)

    def ms(k, dv=''):
        return meta.get(k, dv) or dv

    mode_rendu = ms('mode', 'ortho')   # 'ortho' ou 'dessin'
    pr("  mode     : " + mode_rendu)

    svg_path    = ms('svg_path')
    section_w   = mf('section_w_m', 0.5)
    section_h   = mf('section_h_m', 0.3)
    bloc_w      = mf('bloc_w_m',    0.5)
    bloc_d      = mf('bloc_d_m',    0.5)
    bloc_h      = mf('bloc_h_m',    0.5)

    KEYS = ['coupe','face','dos','gauche','droite','dessus','dessous']
    tiffs = {}
    for k in KEYS:
        p = ms('tiff_' + k)
        tiffs[k] = p if (p and os.path.exists(p) and os.path.getsize(p) > 0) else None

    pr("  section : {0:.3f} x {1:.3f} m".format(section_w, section_h))
    pr("  bloc    : {0:.3f} x {1:.3f} x {2:.3f} m".format(bloc_w, bloc_d, bloc_h))
    for k in KEYS:
        pr("  {0:<8}: {1}".format(k, tiffs[k] or '(absent)'))

    # -------------------------------------------------------------------
    # Dimensions reelles (m) de chaque TIFF depuis son TFW ou ses pixels
    # -------------------------------------------------------------------
    def _tiff_real_dims(tif_path):
        """
        Retourne (real_w_m, real_h_m) en metres pour un TIFF ortho.
        Priorite : TFW  (resolution * px)  >  fallback meta dim_xxx.
        Si rien n'est disponible, retourne None, None.
        """
        if not tif_path or not os.path.exists(tif_path):
            return None, None
        # 1. TFW
        tfw = os.path.splitext(tif_path)[0] + '.tfw'
        if os.path.exists(tfw):
            try:
                lines = open(tfw).read().strip().splitlines()
                res = abs(float(lines[0]))   # m/pixel (ligne 1)
                # Lire px_w, px_h depuis l'image
                from PIL import Image as _PIL
                with _PIL.open(tif_path) as im:
                    px_w2, px_h2 = im.size
                rw = res * px_w2
                rh = res * px_h2
                return rw, rh
            except Exception as e:
                pr("  TFW lecture erreur {0} : {1}".format(tfw, e))
        # 2. Pixels seuls (sans TFW) : lire px_w, px_h
        try:
            from PIL import Image as _PIL2
            with _PIL2.open(tif_path) as im:
                px_w2, px_h2 = im.size
            # Essayer de lire la resolution depuis les meta TIFF (XResolution tag)
            import struct
            res = None
            try:
                tif_info = im.tag_v2 if hasattr(im, 'tag_v2') else {}
                # Tag 282=XResolution, 283=YResolution, 296=ResolutionUnit
                xres = tif_info.get(282)
                unit = tif_info.get(296, 2)  # 2=inch, 3=cm
                if xres:
                    if isinstance(xres, tuple): xres = xres[0] / xres[1]
                    if unit == 2:   res = 0.0254 / xres   # inch -> m/px
                    elif unit == 3: res = 0.01  / xres    # cm -> m/px
            except Exception:
                pass
            if res and res > 0:
                return res * px_w2, res * px_h2
        except Exception:
            pass
        return None, None

    # Charger les dimensions reelles de chaque vue
    tiff_real = {}
    for k in KEYS:
        rw, rh = _tiff_real_dims(tiffs.get(k))
        tiff_real[k] = (rw, rh)
        if rw:
            pr("  dim_{0}: {1:.4f} x {2:.4f} m (depuis TIFF/TFW)".format(k, rw, rh))
        else:
            pr("  dim_{0}: (non disponible — fallback bbox)".format(k))

    if not os.path.exists(svg_path):
        pr("ERREUR : SVG introuvable : " + svg_path)
        raise FileNotFoundError(svg_path)

    pdf_path = meta_base(meta_path) + '.pdf'
    pr("  pdf     : " + pdf_path)

    # -------------------------------------------------------------------
    # Calcul des zones
    #
    # Nouvelle disposition A3 Portrait :
    #
    #  Col gauche (3 rangees) | Col droite (4 rangees)
    #  ─────────────────────────────────────────────────
    #  [FACE]                 | [DESSUS]
    #  [GAUCHE]               | [COUPE]
    #  [DROITE]               | [DOS]
    #                         | [DESSOUS]
    #
    # Echelle UNIQUE pour toutes les vues (maximale qui fait tenir tout).
    # -------------------------------------------------------------------
    ZW = PW - 2*MAR
    ZH = PH - 2*MAR - TTL

    # Fractions colonnes : col gauche un peu plus large (face + vues lat)
    col_l_frac = 0.44
    col_r_frac = 1.0 - col_l_frac
    col_l_max  = ZW * col_l_frac - GAP/2
    col_r_max  = ZW * col_r_frac - GAP/2

    # Hauteur rangees
    row_h_l = (ZH - 2*GAP) / 3.0     # col gauche : 3 rangees
    row_h_r = (ZH - 3*GAP) / 4.0     # col droite : 4 rangees
    draw_l   = row_h_l - LBL - MIR
    draw_r   = row_h_r - LBL - MIR

    # Echelle UNIQUE : contrainte par toutes les vues dans leurs cellules
    # Dimensions reelles :
    #   face/dos : bloc_w x bloc_h      dans col gauche row_h_l / col droite row_h_r
    #   gauche/droite : bloc_d x bloc_h dans col gauche row_h_l
    #   coupe    : section_w x section_h dans col droite row_h_r
    #   dessus/dessous : bloc_w x bloc_d dans col droite row_h_r

    def best_scale_unified():
        """
        Cherche le denominateur d'echelle unique qui fait tenir
        toutes les vues dans leurs cellules respectives.
        Utilise les dimensions reelles des TIFF (tiff_real) quand disponibles,
        sinon les dimensions de la bounding box du mesh.
        """
        def rw(k, fallback_w, fallback_h):
            """Retourne (w_m, h_m) reels pour la vue k."""
            tw, th = tiff_real.get(k, (None, None))
            return (tw if tw else fallback_w,
                    th if th else fallback_h)

        # (dim_w_m, max_paper_w_cm, dim_h_m, max_paper_h_cm)
        fw, fh = rw('face',    bloc_w, bloc_h)
        gw, gh = rw('gauche',  bloc_d, bloc_h)
        dw2,dh2= rw('droite',  bloc_d, bloc_h)
        sw, sh = rw('dessus',  bloc_w, bloc_d)
        sow,soh= rw('dessous', bloc_w, bloc_d)
        cow,coh= rw('coupe',   section_w, section_h)
        dow,doh= rw('dos',     bloc_w, bloc_h)

        contraintes = [
            (fw,  col_l_max - 0.3, fh,  draw_l - 0.1),   # face   (col g)
            (gw,  col_l_max - 0.3, gh,  draw_l - 0.1),   # gauche (col g)
            (dw2, col_l_max - 0.3, dh2, draw_l - 0.1),   # droite (col g)
            (sw,  col_r_max - 0.3, sh,  draw_r - 0.1),   # dessus (col d)
            (sow, col_r_max - 0.3, soh, draw_r - 0.1),   # dessous(col d)
            (cow, col_r_max - 0.3, coh, draw_r - 0.1),   # coupe  (col d)
            (dow, col_r_max - 0.3, doh, draw_r - 0.1),   # dos    (col d)
        ]
        for d in SCALES:
            r = 1.0 / d
            ok = True
            for (dimw, mw, dimh, mh) in contraintes:
                if dimw * r * 100.0 > mw or dimh * r * 100.0 > mh:
                    ok = False; break
            if ok:
                return r, d
        # Fallback ratio libre
        min_r = 999.0
        for (dimw, mw, dimh, mh) in contraintes:
            if dimw > 0: min_r = min(min_r, mw / (dimw * 100.0))
            if dimh > 0: min_r = min(min_r, mh / (dimh * 100.0))
        d_approx = max(1, int(math.ceil(1.0 / min_r)))
        return 1.0 / d_approx, d_approx

    SR, SD = best_scale_unified()
    pr("Echelle unique   : 1:{0}".format(SD))
    SRL = SR; SDL = SD
    SRP = SR; SDP = SD

    # Positions colonnes
    col_l_x = MAR
    col_l_w = ZW * col_l_frac - GAP/2
    col_r_x = MAR + col_l_w + GAP
    col_r_w = ZW * col_r_frac - GAP/2

    # Positions Y col gauche (3 rangees : face, gauche, droite)
    y_face_l = MAR
    y_gauch  = MAR + row_h_l + GAP
    y_droit  = MAR + 2*(row_h_l + GAP)

    # Positions Y col droite (4 rangees : dessus, coupe, dos, dessous)
    y_rows = [MAR + i*(row_h_r + GAP) for i in range(4)]
    # 0=dessus, 1=coupe, 2=dos, 3=dessous

    # ---------------------------------------------------------------
    # Dimensions papier = dimensions REELLES du TIFF a l'echelle SR
    # Si le TFW n'est pas disponible, fallback sur bbox.
    # ---------------------------------------------------------------
    def _pw_ph(key, fallback_w_m, fallback_h_m):
        """Retourne (pw_cm, ph_cm) a l'echelle SR depuis les dims reelles du TIFF."""
        tw, th = tiff_real.get(key, (None, None))
        w_m = tw if tw else fallback_w_m
        h_m = th if th else fallback_h_m
        return pcm(w_m, SR), pcm(h_m, SR)

    face_pw,  face_ph  = _pw_ph('face',    bloc_w,    bloc_h)
    lat_g_pw, lat_g_ph = _pw_ph('gauche',  bloc_d,    bloc_h)
    lat_d_pw, lat_d_ph = _pw_ph('droite',  bloc_d,    bloc_h)
    plan_s_pw,plan_s_ph= _pw_ph('dessus',  bloc_w,    bloc_d)
    plan_i_pw,plan_i_ph= _pw_ph('dessous', bloc_w,    bloc_d)
    coup_pw,  coup_ph  = _pw_ph('coupe',   section_w, section_h)
    dos_pw,   dos_ph   = _pw_ph('dos',     bloc_w,    bloc_h)

    pr("  Dims papier (cm) face:{0:.1f}x{1:.1f}  gauche:{2:.1f}x{3:.1f}  "
       "dessus:{4:.1f}x{5:.1f}".format(
        face_pw, face_ph, lat_g_pw, lat_g_ph, plan_s_pw, plan_s_ph))

    # -------------------------------------------------------------------
    # Fonctions rendu
    # -------------------------------------------------------------------

    def best_mire(ratio):
        N = 4
        max_paper = 5.2    # cm maxi de mire sur papier
        max_reel  = max_paper / 100.0 / ratio if ratio > 0 else 0.01
        for u in [2.0,1.0,0.5,0.2,0.1,0.05,0.02,0.01,0.005,0.002,0.001]:
            if N * u <= max_reel:
                return N, u, N*u
        return 1, 0.001, 0.001

    def draw_mire(c, cx, top_y, ratio, denom, bar_h=0.26, fpt=5.8):
        n, um, tm = best_mire(ratio)
        tp   = tm * 100.0 * ratio       # taille papier en cm
        seg  = tp / n
        x0   = cx - tp / 2.0
        bt   = yp(top_y)
        bh   = bar_h * cm
        c.setLineWidth(0.28)
        c.setStrokeColorRGB(0,0,0)
        for i in range(n):
            x1 = (x0 + i*seg) * cm
            x2 = (x0 + (i+1)*seg) * cm
            c.setFillColorRGB(0,0,0) if i%2==0 else c.setFillColorRGB(1,1,1)
            c.rect(x1, bt-bh, x2-x1, bh, fill=1, stroke=1)
        c.setFillColorRGB(0,0,0)
        c.setFont("Helvetica", fpt)
        tk = 0.07*cm
        for i in range(n+1):
            xg = (x0 + i*seg) * cm
            c.line(xg, bt, xg, bt+tk)
            vc = i * um * 100.0
            s  = "{0:.0f}".format(vc) if vc==int(vc) else "{0:.1f}".format(vc)
            c.drawCentredString(xg, bt+tk+0.018*cm, s+"cm" if i==n else s)
        sc = "1:{0}".format(denom) if denom>1 else "1:1"
        c.setFont("Helvetica", fpt)
        c.drawCentredString(cx*cm, bt-bh-0.18*cm, sc)

    def lbl(c, x, y, txt, fs=5.2):
        c.setFont("Helvetica-Bold", fs)
        c.setFillColorRGB(0.1,0.1,0.1)
        c.drawString(x*cm, yp(y+0.30), txt)

    def nodata(c, cx, cy):
        c.setFont("Helvetica-Oblique", 5.2)
        c.setFillColorRGB(.55,.55,.55)
        c.drawCentredString(cx*cm, yp(cy), "(non disponible)")

    def _draw_cut_line_cm(c_obj, cx1, cy1, cx2, cy2):
        """
        Trace l'axe de coupe entre deux points (coords cm, Y croissant vers le bas).
        - Ligne tirets passant par les 2 marqueurs, prolongee de chaque cote
        - Traits epais (eperons) aux deux extremites, perpendiculaires a la ligne
        Identique au style coupe_ceramique7_pdf.py.
        """
        dx = cx2 - cx1;  dy = cy2 - cy1
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return
        ux = dx / length;  uy = dy / length

        EXTEND_CM = 0.7   # prolongement de la ligne au-dela des marqueurs
        TICK_CM   = 0.6   # longueur des eperons

        ax = cx1 - ux * EXTEND_CM;  ay = cy1 - uy * EXTEND_CM
        bx = cx2 + ux * EXTEND_CM;  by = cy2 + uy * EXTEND_CM

        # Ligne tirets
        c_obj.setStrokeColorRGB(0, 0, 0)
        c_obj.setLineWidth(0.55)
        c_obj.setDash([0.22 * cm, 0.13 * cm])
        c_obj.line(ax * cm, yp(ay), bx * cm, yp(by))
        c_obj.setDash()

        # Eperons epais aux extremites
        c_obj.setLineWidth(2.0)
        c_obj.setLineCap(2)
        c_obj.line((ax - ux*TICK_CM)*cm, yp(ay - uy*TICK_CM), ax*cm, yp(ay))
        c_obj.line( bx*cm, yp(by), (bx + ux*TICK_CM)*cm, yp(by + uy*TICK_CM))
        c_obj.setLineCap(0)

    def draw_cut_line_on_vue(c_obj, vue_key,
                             zone_x, zone_y, zone_w, zone_h,
                             paper_w, paper_h):
        """
        Trace le trait de coupe sur une vue raster (dessus ou dessous).
        Lit les fracs m1/m2 depuis meta, convertit en cm papier.
        """
        import math as _m2
        k1x = mf('m1_frac_{0}_x'.format(vue_key), float('nan'))
        k1y = mf('m1_frac_{0}_y'.format(vue_key), float('nan'))
        k2x = mf('m2_frac_{0}_x'.format(vue_key), float('nan'))
        k2y = mf('m2_frac_{0}_y'.format(vue_key), float('nan'))
        if any(_m2.isnan(v) for v in (k1x, k1y, k2x, k2y)):
            return   # fractions absentes du meta

        # Offset de l'image centree dans la zone (identique a draw_raster)
        ox = zone_x + (zone_w - paper_w) / 2
        oy = zone_y + (zone_h - paper_h) / 2

        # Fractions -> cm papier
        cx1 = ox + k1x * paper_w
        cy1 = oy + k1y * paper_h
        cx2 = ox + k2x * paper_w
        cy2 = oy + k2y * paper_h

        _draw_cut_line_cm(c_obj, cx1, cy1, cx2, cy2)

    def draw_raster(c, tif, zx, zy, zw, zh, pw, ph):
        import io as _io
        ox = zx + (zw-pw)/2
        oy = zy + (zh-ph)/2
        src = Image.open(tif)
        if src.mode == 'RGBA':
            bg = Image.new('RGB', src.size, (255,255,255))
            bg.paste(src, mask=src.split()[3])
            img = bg
        else:
            img = src.convert('RGB')
        buf = _io.BytesIO()
        img.save(buf, format='PNG'); buf.seek(0)
        c.drawImage(ImageReader(buf), ox*cm, yp(oy+ph), pw*cm, ph*cm)

    # -----------------------------------------------------------------------
    # Pipeline dessin archeologique (mode 'dessin') — identique coupe_ceramique7_pdf
    # -----------------------------------------------------------------------

    def _process_dessin(tif_path):
        """
        Traitement CLAHE / contour / motifs de gris sur un TIFF ortho.
        Retourne (dessin_np, cont_pts, zones_motifs, px_w, px_h) ou None.
        """
        try:
            img = cv2.imread(tif_path, cv2.IMREAD_UNCHANGED)
            if img is None:
                img = np.array(Image.open(tif_path))
            alpha_mask = None
            if img.ndim == 3 and img.shape[2] == 4:
                alpha_mask = img[:, :, 3]
                rgb  = img[:, :, :3].astype(np.float32)
                a    = alpha_mask.astype(np.float32) / 255.0
                white= np.ones_like(rgb) * 255.0
                comp = (rgb * a[..., None] + white*(1-a[..., None])).astype(np.uint8)
                gray = cv2.cvtColor(comp, cv2.COLOR_RGB2GRAY)
            elif img.ndim == 3 and img.shape[2] == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            else:
                gray = img
            if gray.dtype != np.uint8:
                mn2, mx2 = gray.min(), gray.max()
                gray = ((gray-mn2)/(mx2-mn2)*255).astype(np.uint8) if mx2>mn2 \
                       else np.zeros_like(gray, dtype=np.uint8)
            ph2, pw2 = gray.shape

            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8,8))
            enh   = clahe.apply(gray)
            _, binary = cv2.threshold(enh, 0, 255,
                                      cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7,7))
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kern, iterations=3)
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN,  kern, iterations=2)
            cnts, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
            if not cnts:
                return None
            main_cnt = max(cnts, key=cv2.contourArea)
            mask = np.zeros_like(gray)
            cv2.drawContours(mask, [main_cnt], -1, 255, -1)
            if alpha_mask is not None:
                mask = np.where(alpha_mask > 10, np.uint8(255), np.uint8(0))
                ca, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                         cv2.CHAIN_APPROX_SIMPLE)
                if ca:
                    main_cnt = max(ca, key=cv2.contourArea)

            contrasted  = cv2.convertScaleAbs(enh, alpha=1.8, beta=-80)
            dessin_np2  = np.ones_like(gray) * 255
            dessin_np2[mask > 0] = contrasted[mask > 0]
            cv2.drawContours(dessin_np2, [main_cnt], -1, 0, 2, cv2.LINE_AA)

            simp = cv2.approxPolyDP(main_cnt, 0.5, True)
            cont_pts2 = simp.reshape(-1, 2).tolist()

            return (dessin_np2, pw2, ph2)
        except Exception as e:
            pr("  AVERT dessin {0} : {1}".format(tif_path, e))
            return None

    def draw_raster_dessin(c_obj, tif_path, zx, zy, zw, zh, pw, ph):
        """
        Rendu mode dessin : uniquement le raster CLAHE traite (equivalent Q2
        de coupe_ceramique7_pdf — niveaux de gris ameliores + contour integre
        dans l'image raster). Pas de motifs vecteur superposes.
        Fallback sur ortho brute si le traitement echoue.
        """
        import tempfile as _tmp2

        result = _process_dessin(tif_path)
        if result is None:
            draw_raster(c_obj, tif_path, zx, zy, zw, zh, pw, ph)
            return

        dessin_np2, px_w2, px_h2 = result
        # Afficher uniquement le raster traite (dessin_np2)
        # Le contour est deja integre dans dessin_np2 par cv2.drawContours(... 0, 2)
        tmp = _tmp2.mktemp(suffix='.png')
        try:
            Image.fromarray(dessin_np2).convert('RGB').save(tmp)
            draw_raster(c_obj, tmp, zx, zy, zw, zh, pw, ph)
        finally:
            try: os.remove(tmp)
            except: pass

    def vue(c, key, zx, zy, zw, zh, pw, ph, ratio, denom, label):
        """Rend une vue : label + ortho (ou dessin archeo) + mire."""
        lbl(c, zx, zy, label)
        dy = zy + LBL
        dh = zh - LBL - MIR
        cx = zx + zw/2
        t  = tiffs.get(key)
        if t:
            try:
                if mode_rendu == 'dessin':
                    draw_raster_dessin(c, t, zx, dy, zw, dh, pw, ph)
                else:
                    draw_raster(c, t, zx, dy, zw, dh, pw, ph)
            except Exception as e:
                pr("  AVERT {0}: {1}".format(key, e))
                nodata(c, cx, dy+dh/2)
        else:
            nodata(c, cx, dy+dh/2)
        draw_mire(c, cx, dy+dh+MIR*0.20, ratio, denom)

    # -------------------------------------------------------------------
    # Rendu coupe SVG — hachures ReportLab
    # -------------------------------------------------------------------
    def _tok(d):
        toks=[]; i=0
        while i<len(d):
            ch=d[i]
            if ch in 'MmLlHhVvCcSsQqTtAaZz':
                toks.append(ch); i+=1
            elif ch in '0123456789.+-':
                if ch in '+-' and (i+1>=len(d) or d[i+1] not in '0123456789.'):
                    i+=1; continue
                j=i
                if d[j] in '+-': j+=1
                while j<len(d) and d[j] in '0123456789': j+=1
                if j<len(d) and d[j]=='.':
                    j+=1
                    while j<len(d) and d[j] in '0123456789': j+=1
                if j<len(d) and d[j] in 'eE':
                    j+=1
                    if j<len(d) and d[j] in '+-': j+=1
                    while j<len(d) and d[j].isdigit(): j+=1
                try: toks.append(float(d[i:j]))
                except ValueError: pass
                i=j
            else: i+=1
        return toks

    def read_svg_contour():
        import xml.etree.ElementTree as ET
        NS = 'http://www.w3.org/2000/svg'
        tree = ET.parse(svg_path)
        root = tree.getroot()
        def sn(t): return t.replace('{'+NS+'}','')
        def pdim(s):
            s=s.strip()
            if s.endswith('mm'): return float(s[:-2])/1000
            if s.endswith('cm'): return float(s[:-2])/100
            if s.endswith('m') and not s.endswith('mm'): return float(s[:-1])
            try: return float(s)/100
            except: return 0.1
        rw = pdim(root.get('width','0.5m'))
        rh = pdim(root.get('height','0.3m'))
        vb = root.get('viewBox','').replace(',',' ').split()
        x0 = float(vb[0]) if len(vb)==4 else 0.0
        y0 = float(vb[1]) if len(vb)==4 else 0.0

        # Lire tous les path, garder celui avec le plus de points
        best_pts = []
        for el in root.iter():
            if sn(el.tag) != 'path': continue
            d_str = el.get('d','')
            toks  = _tok(d_str)
            pts=[]; cx2=cy2=0.0; cmd='M'; idx=0
            while idx<len(toks):
                t=toks[idx]
                if isinstance(t,str):
                    cmd=t; idx+=1; continue
                if cmd in ('M','L'):
                    cx2,cy2=t,toks[idx+1]; idx+=2; pts.append((cx2,cy2))
                elif cmd in ('m','l'):
                    cx2+=t; cy2+=toks[idx+1]; idx+=2; pts.append((cx2,cy2))
                elif cmd in ('Z','z'): pass
                else: idx+=1
            if len(pts)>len(best_pts):
                best_pts=pts
        return best_pts, rw, rh, x0, y0

    def render_coupe(c, zx, zy, zw, zh):
        """Coupe hachures : fond blanc, hachures noires 45deg, contour noir."""
        try:
            pts, rw, rh, x0, y0 = read_svg_contour()
        except Exception as e:
            pr("ERREUR SVG : "+str(e))
            nodata(c, zx+zw/2, zy+zh/2); return

        if not pts:
            nodata(c, zx+zw/2, zy+zh/2); return

        spt   = SRL * 100.0 * cm          # m -> pt
        pw_c  = rw * 100.0 * SRL          # largeur papier coupe (cm)
        ph_c  = rh * 100.0 * SRL          # hauteur papier coupe (cm)
        ox    = zx + (zw - pw_c) / 2      # offset X (cm)
        oy    = zy + (zh - ph_c) / 2      # offset Y (cm)
        lft   = ox * cm                   # bord gauche en pt
        bot   = yp(oy + ph_c)             # bas en pt RL

        def w2r(xw, yw):
            """Monde (m) -> ReportLab (pt)."""
            return lft + (xw-x0)*spt, bot + (yw-y0)*spt

        # Fond blanc
        c.setFillColorRGB(1,1,1)
        c.rect(lft, bot, pw_c*cm, ph_c*cm, fill=1, stroke=0)

        # --- Clip + hachures ---
        c.saveState()
        pth = c.beginPath()
        px0, py0 = w2r(pts[0][0], pts[0][1])
        pth.moveTo(px0, py0)
        for xw, yw in pts[1:]:
            pth.lineTo(*w2r(xw, yw))
        pth.close()
        c.clipPath(pth, stroke=0, fill=0)

        # Hachures en pts ReportLab
        xs_c = [p[0] for p in pts]; ys_c = [p[1] for p in pts]
        bx0_r, by0_r = w2r(min(xs_c), min(ys_c))
        bx1_r, by1_r = w2r(max(xs_c), max(ys_c))
        cxr = (bx0_r+bx1_r)/2; cyr = (by0_r+by1_r)/2
        diag = math.hypot(bx1_r-bx0_r, by1_r-by0_r) * 1.5
        gap  = max(3.5, pw_c*cm*0.016)      # espacement hachures en pt
        sw_h = max(0.3, pw_c*cm*0.004)

        c.setStrokeColorRGB(0,0,0)
        c.setLineWidth(sw_h)
        t_val = -diag
        while t_val <= diag:
            ox_h = cxr + t_val*(-0.7071)
            oy_h = cyr + t_val*0.7071
            c.line(ox_h-diag*0.7071, oy_h-diag*0.7071,
                   ox_h+diag*0.7071, oy_h+diag*0.7071)
            t_val += gap
        c.restoreState()

        # Contour extérieur
        sw_c = max(0.5, pw_c*cm*0.007)
        c.setStrokeColorRGB(0,0,0)
        c.setLineWidth(sw_c)
        p2 = c.beginPath()
        p2.moveTo(px0, py0)
        for xw, yw in pts[1:]:
            p2.lineTo(*w2r(xw, yw))
        p2.close()
        c.drawPath(p2, stroke=1, fill=0)

    # -------------------------------------------------------------------
    # Canvas
    # -------------------------------------------------------------------
    pr("Creation du PDF...")
    from datetime import datetime
    date_str = datetime.now().strftime("%d/%m/%Y")

    c = rl_canvas.Canvas(pdf_path, pagesize=(PW*cm, PH*cm))
    c.setFillColorRGB(1,1,1)
    c.rect(0, 0, PW*cm, PH*cm, fill=1, stroke=0)

    import math

    # Titre bas de page
    c.setFont("Helvetica-Bold", 7)
    c.setFillColorRGB(0,0,0)
    mode_lbl = "Dessin archeo" if mode_rendu == 'dessin' else "Orthomosaique"
    c.drawCentredString(PW/2*cm, yp(PH-0.58),
        "Coupe Bloc   |   {0}   |   Echelle 1:{1}   |   {2}".format(
            mode_lbl, SD, date_str))
    c.setStrokeColorRGB(0.65,0.65,0.65); c.setLineWidth(0.3)
    c.line(MAR*cm, yp(PH-MAR-TTL), (PW-MAR)*cm, yp(PH-MAR-TTL))

    # Separateur vertical colonnes
    sep_x = col_r_x - GAP/2
    c.setStrokeColorRGB(0.72,0.72,0.72); c.setLineWidth(0.22)
    c.line(sep_x*cm, yp(MAR), sep_x*cm, yp(MAR+ZH))

    # ==== COLONNE GAUCHE : face (haut) + gauche (milieu) + droite (bas) ====
    vue(c,'face',   col_l_x, y_face_l, col_l_w, row_h_l,
        face_pw, face_ph, SR, SD, "Vue de face")

    c.setStrokeColorRGB(0.75,0.75,0.75); c.setLineWidth(0.20)
    c.line(col_l_x*cm, yp(y_face_l+row_h_l+GAP/2),
           (col_l_x+col_l_w)*cm, yp(y_face_l+row_h_l+GAP/2))

    vue(c,'gauche', col_l_x, y_gauch, col_l_w, row_h_l,
        lat_g_pw, lat_g_ph, SR, SD, "Vue gauche")

    c.setStrokeColorRGB(0.75,0.75,0.75); c.setLineWidth(0.20)
    c.line(col_l_x*cm, yp(y_gauch+row_h_l+GAP/2),
           (col_l_x+col_l_w)*cm, yp(y_gauch+row_h_l+GAP/2))

    vue(c,'droite', col_l_x, y_droit, col_l_w, row_h_l,
        lat_d_pw, lat_d_ph, SR, SD, "Vue droite")

    # ==== COLONNE DROITE : dessus (haut) + coupe + dos + dessous (bas) ====
    vue(c,'dessus',  col_r_x, y_rows[0], col_r_w, row_h_r,
        plan_s_pw, plan_s_ph, SR, SD, "Vue de dessus")
    draw_cut_line_on_vue(c, 'dessus',
        col_r_x, y_rows[0]+LBL, col_r_w, row_h_r-LBL-MIR,
        plan_s_pw, plan_s_ph)

    # --- Coupe SVG ---
    lbl(c, col_r_x, y_rows[1], "Coupe — hachures" if mode_rendu == 'dessin' else "Coupe — profil")
    cy0 = y_rows[1] + LBL
    cdh = row_h_r - LBL - MIR
    render_coupe(c, col_r_x, cy0, col_r_w, cdh)
    draw_mire(c, col_r_x+col_r_w/2, cy0+cdh+MIR*0.20, SR, SD)

    vue(c,'dos',     col_r_x, y_rows[2], col_r_w, row_h_r,
        dos_pw, dos_ph, SR, SD, "Vue de dos")

    vue(c,'dessous', col_r_x, y_rows[3], col_r_w, row_h_r,
        plan_i_pw, plan_i_ph, SR, SD, "Vue de dessous")
    draw_cut_line_on_vue(c, 'dessous',
        col_r_x, y_rows[3]+LBL, col_r_w, row_h_r-LBL-MIR,
        plan_i_pw, plan_i_ph)

    # Separateurs horizontaux col droite
    c.setStrokeColorRGB(0.75,0.75,0.75); c.setLineWidth(0.20)
    for i in range(3):
        sy = y_rows[i] + row_h_r + GAP/2
        c.line(col_r_x*cm, yp(sy), (col_r_x+col_r_w)*cm, yp(sy))

    c.save()
    pr("PDF cree : " + pdf_path)
    return pdf_path


# ===========================================================================
if __name__ == '__main__':
    meta_path = None
    try:
        meta_path = find_meta_path()
    except Exception as e:
        sys.stderr.write(str(e)+"\n"); sys.exit(1)
    if not meta_path:
        sys.stderr.write("Aucun fichier meta.\n"); sys.exit(1)

    log_path = meta_base(meta_path) + '_pdf_log.txt'
    try:
        log = open(log_path, 'w', encoding='utf-8', errors='replace')
    except Exception:
        import tempfile as _t
        log_path = os.path.join(_t.gettempdir(), 'coupe_bloc_pdf_log.txt')
        log = open(log_path, 'w', encoding='utf-8', errors='replace')

    exit_code = 0
    try:
        run(meta_path, log)
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else 1
        log.write("Exit({0})\n".format(exit_code))
    except Exception:
        log.write("\n!!! ERREUR FATALE !!!\n" + traceback.format_exc())
        log.flush(); exit_code = 1
    finally:
        log.write("\nLog : " + log_path + "\n")
        log.close()
    sys.exit(exit_code)

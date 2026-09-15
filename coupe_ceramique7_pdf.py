"""
coupe_ceramique7_pdf.py  v7.2
=============================================================
Script Anaconda — PDF A4 en 4 quadrants, meme echelle.

Dependances : pip install reportlab Pillow opencv-python numpy

Mise en page :
  haut-gauche : Ortho photo (raster TIFF)
  haut-droite : Ortho dessine (raster + vecteur)
  bas-gauche  : Coupe ceramique (vecteur SVG)
  bas-droite  : Dessin vecteur pur

Toutes les vues partagent la meme echelle normalisee (1:1, 1:2...).
Mire : 5 divisions noir/blanc, largeur = largeur reelle de l'objet.

Usage :
    python coupe_ceramique7_pdf.py <fichier.meta.txt>
    Sans argument : dialogue tkinter pour choisir le .meta.txt
"""

# NOTE : les imports lourds (cv2, numpy, reportlab) sont DANS main()
# pour que les erreurs d'import soient capturees dans le fichier log.

import os
import sys
import traceback


# ===========================================================================
# UTILITAIRES DE BASE (imports stdlib uniquement)
# ===========================================================================

def find_meta_path():
    """Retourne le chemin du .meta.txt (argument CLI ou dialogue tkinter)."""
    if len(sys.argv) > 1:
        return sys.argv[1]
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="Choisir le fichier .meta.txt",
            filetypes=[("Meta", "*.meta.txt"), ("Tous", "*.*")])
        root.destroy()
        return path or None
    except Exception:
        return None


def meta_base(meta_path):
    """Retourne le chemin sans extension .meta.txt / .meta / .txt."""
    b = meta_path
    for ext in ('.meta.txt', '.meta', '.txt'):
        if b.lower().endswith(ext):
            b = b[:-len(ext)]
            break
    return b


def read_meta(path):
    data = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '=' in line:
                k, v = line.split('=', 1)
                data[k.strip()] = v.strip()
    return data


# ===========================================================================
# TOUT LE RESTE EST DANS run() — importe ses modules localement
# ===========================================================================

def run(meta_path, log):
    """Corps principal. log est un fichier ouvert en ecriture."""

    def pr(s=''):
        print(s)
        log.write(s + '\n')
        log.flush()

    pr("=" * 60)
    pr("coupe_ceramique7_pdf.py  v7.2")
    pr("Python : " + sys.version)
    pr("meta   : " + meta_path)
    pr("=" * 60)

    # --- Imports ---
    pr("Import des modules...")
    try:
        import math
        import tempfile
        import xml.etree.ElementTree as ET
        from datetime import datetime
        pr("  stdlib         OK")
    except Exception as e:
        pr("ERREUR stdlib : " + str(e)); raise

    try:
        import numpy as np
        pr("  numpy          OK  " + np.__version__)
    except ImportError:
        pr("ERREUR : numpy non installe.  pip install numpy"); raise

    try:
        import cv2
        pr("  opencv         OK  " + cv2.__version__)
    except ImportError:
        pr("ERREUR : opencv non installe.  pip install opencv-python"); raise

    try:
        from PIL import Image
        import PIL
        pr("  Pillow         OK  " + PIL.__version__)
    except ImportError:
        pr("ERREUR : Pillow non installe.  pip install Pillow"); raise

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.units import cm
        import reportlab
        pr("  reportlab      OK  " + reportlab.Version)
    except ImportError:
        pr("ERREUR : reportlab non installe.  pip install reportlab"); raise

    pr("")

    # -----------------------------------------------------------------------
    # Constantes de mise en page
    # -----------------------------------------------------------------------
    A4_W_cm = 21.0
    A4_H_cm = 29.7
    MARGIN  = 1.2
    GAP     = 0.5
    TITLE_H = 1.0
    LABEL_H = 0.55
    MIRE_H  = 1.8

    NORMALIZED_SCALES = [1,2,3,4,5,10,20,40,50,100,200,500,1000]

    def yp(y_top_cm):
        return (A4_H_cm - y_top_cm) * cm

    def choose_scale(real_dim_m, max_paper_cm):
        for d in NORMALIZED_SCALES:
            r = 1.0 / d
            if real_dim_m * r * 100.0 <= max_paper_cm:
                return r, d
        r = max_paper_cm / (real_dim_m * 100.0)
        return r, int(round(1.0 / r))

    def fmt_val(v):
        return "{0:.0f}".format(v) if v == int(v) else "{0:.3g}".format(v)

    # -----------------------------------------------------------------------
    # Lecture meta
    # -----------------------------------------------------------------------
    pr("Lecture meta...")
    meta      = read_meta(meta_path)
    svg_path  = meta.get('svg_path', '')
    ortho_tif = meta.get('ortho_tiff', '') or None
    real_w_m  = float(meta.get('real_w_m', 0.1))
    real_h_m  = float(meta.get('real_h_m', 0.05))
    mire_m    = float(meta.get('mire_m', 0.01))
    mire_val  = float(meta.get('mire_val', 1.0))
    mire_unit = meta.get('mire_unit', 'cm')
    ortho_res = float(meta.get('ortho_res_m', 0.0))

    import math as _math

    # Lire les fractions (0..1) de position des marqueurs dans l'ortho
    # col = frac_x * px_w,  row = frac_y * px_h  (apres chargement de l'image)
    marker1_frac_x = float(meta.get('marker1_frac_x', 'nan'))
    marker1_frac_y = float(meta.get('marker1_frac_y', 'nan'))
    marker2_frac_x = float(meta.get('marker2_frac_x', 'nan'))
    marker2_frac_y = float(meta.get('marker2_frac_y', 'nan'))
    # marker1_col/row sera calcule apres chargement de l'image (px_w, px_h connus)
    marker1_col = float('nan')
    marker1_row = float('nan')
    marker2_col = float('nan')
    marker2_row = float('nan')
    have_markers = not (_math.isnan(marker1_frac_x) or _math.isnan(marker2_frac_x))

    pr("  svg_path  : " + svg_path)
    pr("  ortho_tif : " + str(ortho_tif))
    pr("  real      : {0:.4f} m x {1:.4f} m".format(real_w_m, real_h_m))
    pr("  mire      : {0} {1}  ({2:.6f} m)".format(
        fmt_val(mire_val), mire_unit, mire_m))
    pr("  markers   : " + ("frac ({0:.4f},{1:.4f}) / ({2:.4f},{3:.4f})".format(
        marker1_frac_x, marker1_frac_y,
        marker2_frac_x, marker2_frac_y) if have_markers else "ABSENTS"))

    if not os.path.exists(svg_path):
        pr("ERREUR : SVG introuvable : " + svg_path)
        raise FileNotFoundError("SVG introuvable : " + svg_path)

    pdf_path = meta_base(meta_path) + '.pdf'
    pr("  pdf_path  : " + pdf_path)

    # -----------------------------------------------------------------------
    # Mise en page : 4 quadrants egaux
    # -----------------------------------------------------------------------
    total_w = A4_W_cm - 2 * MARGIN
    total_h = A4_H_cm - 2 * MARGIN - TITLE_H
    qw = (total_w - GAP) / 2
    qh = (total_h - GAP) / 2
    draw_h = qh - LABEL_H - MIRE_H

    q_left  = MARGIN
    q_right = MARGIN + qw + GAP
    q_top   = MARGIN + TITLE_H
    q_bot   = q_top + qh + GAP

    # Echelle normalisee basee sur la hauteur de la coupe SVG (real_h_m).
    # Si la coupe fait <= 10cm -> echelle 1:1.
    # Si > 10cm -> reduire avec une echelle normalisee (1:2, 1:3, 1:4, 1:5, 1:10...).
    # Q1 Q2 Q4 utilisent exactement la meme echelle.
    SEUIL_1_1_M = 0.10  # 10cm : seuil au-dela duquel on reduit
    if real_h_m <= SEUIL_1_1_M:
        scale_ratio, scale_denom = 1.0, 1
    else:
        scale_ratio, scale_denom = choose_scale(real_h_m, draw_h - 0.2)

    scale_m_to_pt = scale_ratio * 100.0 * cm
    coupe_paper_w = real_w_m * 100.0 * scale_ratio
    coupe_paper_h = real_h_m * 100.0 * scale_ratio

    # Mire : choisir une longueur entiere qui tient dans la zone mire
    # et qui est coherente avec l'echelle choisie.
    MIRE_MAX_CM = 4.5   # largeur max de la mire sur le papier
    # Longueur reelle representee par MIRE_MAX_CM a cette echelle
    mire_reel_max_m = MIRE_MAX_CM / 100.0 / scale_ratio
    # Choisir une valeur ronde (mire_val en mire_unit)
    # On recalcule mire_val et mire_unit pour coller a l'echelle
    def best_mire(max_m):
        """Toujours 4 divisions. Choisit la plus grande unite ronde (en cm)
        telle que 4 * unit_m <= max_m.
        Retourne (4, 'cm', unit_m, total_m).
        """
        N = 4
        # Unites candidates en metres, du plus grand au plus petit
        units_m = [1.0, 0.50, 0.20, 0.10, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001]
        for u_m in units_m:
            if N * u_m <= max_m:
                return N, 'cm', u_m, N * u_m
        # Fallback : 1 division de la plus petite unite
        return 1, 'cm', 0.001, 0.001

    mire_ndiv, mire_unit_disp, mire_unit_m, mire_m_disp = best_mire(mire_reel_max_m)
    mire_paper_cm = mire_m_disp * 100.0 * scale_ratio
    mire_label    = "{0} {1}".format(mire_ndiv, mire_unit_disp)

    pr("Echelle 1:{0}  |  {1:.2f} cm x {2:.2f} cm papier".format(
        scale_denom, coupe_paper_w, coupe_paper_h))
    pr("Mire : {0}x{1}{2}  ({3:.2f} cm papier)".format(mire_ndiv, int(mire_unit_m*1000) if mire_unit_disp=='mm' else int(mire_unit_m*100), mire_unit_disp, mire_paper_cm))

    # -----------------------------------------------------------------------
    # Dessin archeo depuis TIFF
    # -----------------------------------------------------------------------
    have_ortho     = bool(ortho_tif and os.path.exists(ortho_tif))
    px_w = px_h    = 1
    contour_pts    = []
    zones_motifs   = []
    px_to_cm_paper = 1.0
    ortho_paper_w  = coupe_paper_w
    ortho_paper_h  = coupe_paper_h
    dessin_np      = None

    if have_ortho:
        pr("Chargement ortho : " + ortho_tif)
        try:
            # Chargement image
            img = cv2.imread(ortho_tif, cv2.IMREAD_UNCHANGED)
            if img is None:
                pr("  cv2.imread retourne None, essai PIL...")
                img = np.array(Image.open(ortho_tif))
            pr("  shape brut : " + str(img.shape) + "  dtype : " + str(img.dtype))

            # Si RGBA : utiliser alpha pour composer sur fond blanc
            alpha_mask = None
            if img.ndim == 3 and img.shape[2] == 4:
                alpha_mask = img[:, :, 3]
                rgb = img[:, :, :3].astype(np.float32)
                a   = alpha_mask.astype(np.float32) / 255.0
                white = np.ones_like(rgb) * 255.0
                composed = (rgb * a[..., None] + white * (1 - a[..., None])).astype(np.uint8)
                img = cv2.cvtColor(composed, cv2.COLOR_RGB2GRAY)
            elif img.ndim == 3 and img.shape[2] == 3:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            if img.dtype != np.uint8:
                mn, mx = img.min(), img.max()
                img = ((img - mn) / (mx - mn) * 255).astype(np.uint8) \
                      if mx > mn else np.zeros_like(img, dtype=np.uint8)

            img_gray = img
            px_h, px_w = img_gray.shape
            pr("  gris : {0} x {1} px".format(px_w, px_h))
            # Calculer col/row des marqueurs maintenant que px_w/px_h sont connus
            if have_markers:
                marker1_col = marker1_frac_x * px_w
                marker1_row = marker1_frac_y * px_h
                marker2_col = marker2_frac_x * px_w
                marker2_row = marker2_frac_y * px_h
                pr("  markers px: col={0:.1f},row={1:.1f} / col={2:.1f},row={3:.1f}".format(
                    marker1_col, marker1_row, marker2_col, marker2_row))

            # Calibrer l'echelle depuis la distance reelle M1-M2 et leur distance
            # en pixels dans l'ortho. C'est la source de verite la plus fiable :
            # on connait la distance 3D reelle (real_h_m) et les pixels correspondants.
            import math as _math2
            dpx = 0.0
            if have_markers:
                dpx = _math2.sqrt((marker2_col - marker1_col)**2 +
                                  (marker2_row - marker1_row)**2)
                if dpx > 0:
                    pixel_cm_reel = real_h_m * 100.0 / dpx * scale_ratio
                    pr("  pixel_cm_reel = {0:.6f}  (calibre M1-M2 {1:.1f}px)".format(
                        pixel_cm_reel, dpx))
                else:
                    pixel_cm_reel = ortho_res * 100.0 * scale_ratio
                    pr("  pixel_cm_reel = {0:.6f}  (ortho_res)".format(pixel_cm_reel))
            else:
                # Sans marqueurs : utiliser ortho_res calibre par scale_ratio
                pixel_cm_reel = ortho_res * 100.0 * scale_ratio
                pr("  pixel_cm_reel = {0:.6f}  (ortho_res, pas de marqueurs)".format(
                    pixel_cm_reel))

            px_to_cm_paper = pixel_cm_reel
            ortho_paper_w  = px_w * px_to_cm_paper
            ortho_paper_h  = px_h * px_to_cm_paper

            # Si l'ortho est plus grande que le quadrant, trouver l'echelle
            # normalisee suivante et recalculer tout coheremment.
            if ortho_paper_w > qw or ortho_paper_h > draw_h:
                # Dimension reelle de l'ortho en metres
                ortho_real_w_m = px_w * pixel_cm_reel / 100.0 / scale_ratio
                ortho_real_h_m = px_h * pixel_cm_reel / 100.0 / scale_ratio
                ortho_real_max = max(ortho_real_w_m, ortho_real_h_m)
                # Choisir echelle pour que l'ortho tienne dans le quadrant
                sr_new, sd_new = choose_scale(ortho_real_max, min(qw, draw_h) - 0.2)
                pr("  ortho trop grande -> echelle 1:{0}".format(sd_new))
                # Recalculer tout a la nouvelle echelle
                scale_ratio    = sr_new
                scale_denom    = sd_new
                scale_m_to_pt  = scale_ratio * 100.0 * cm
                coupe_paper_w  = real_w_m * 100.0 * scale_ratio
                coupe_paper_h  = real_h_m * 100.0 * scale_ratio
                pixel_cm_reel  = real_h_m * 100.0 / dpx * scale_ratio if (have_markers and dpx > 0) else ortho_res * 100.0 * scale_ratio
                px_to_cm_paper = pixel_cm_reel
                ortho_paper_w  = px_w * px_to_cm_paper
                ortho_paper_h  = px_h * px_to_cm_paper
                # Recalculer la mire pour la nouvelle echelle
                mire_reel_max_m2 = MIRE_MAX_CM / 100.0 / scale_ratio
                mire_ndiv, mire_unit_disp, mire_unit_m, mire_m_disp = best_mire(mire_reel_max_m2)
                mire_paper_cm  = mire_m_disp * 100.0 * scale_ratio
                mire_label     = "{0} {1}".format(mire_ndiv, mire_unit_disp)

            pr("  ortho papier : {0:.2f} cm x {1:.2f} cm".format(
                ortho_paper_w, ortho_paper_h))

            # Extraction contour + dessin
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            enh = clahe.apply(img_gray)
            _, binary = cv2.threshold(enh, 0, 255,
                                      cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=3)
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN,  kernel, iterations=2)
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL,
                                            cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                raise RuntimeError("Aucun contour detecte dans l'ortho")
            main_cnt = max(contours, key=cv2.contourArea)
            mask = np.zeros_like(img_gray)
            cv2.drawContours(mask, [main_cnt], -1, 255, -1)
            # Si RGBA : remplacer le masque Otsu par le canal alpha (exact)
            if alpha_mask is not None:
                mask = np.where(alpha_mask > 10, np.uint8(255), np.uint8(0))
                cnts_a, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if cnts_a:
                    main_cnt = max(cnts_a, key=cv2.contourArea)

            contrasted = cv2.convertScaleAbs(enh, alpha=1.8, beta=-80)
            dessin_np = np.ones_like(img_gray) * 255
            dessin_np[mask > 0] = contrasted[mask > 0]
            cv2.drawContours(dessin_np, [main_cnt], -1, 0, 2, cv2.LINE_AA)

            simp = cv2.approxPolyDP(main_cnt, 0.5, True)
            contour_pts = simp.reshape(-1, 2).tolist()

            k20 = np.ones((20, 20), np.uint8)
            mask_int = cv2.erode(mask, k20, iterations=1)
            interior = np.ones_like(dessin_np) * 255
            interior[mask_int > 0] = dessin_np[mask_int > 0]
            niveaux = [(0,80,0.25),(80,130,0.40),(130,180,0.55),(180,220,0.70)]
            zones_motifs = []
            for mn2, mx2, col in niveaux:
                msk2 = cv2.inRange(interior, mn2, mx2)
                msk2 = cv2.bitwise_and(msk2, msk2, mask=mask_int)
                k2 = np.ones((2, 2), np.uint8)
                msk2 = cv2.morphologyEx(msk2, cv2.MORPH_CLOSE, k2)
                msk2 = cv2.morphologyEx(msk2, cv2.MORPH_OPEN,  k2)
                cnts2, _ = cv2.findContours(msk2, cv2.RETR_EXTERNAL,
                                              cv2.CHAIN_APPROX_SIMPLE)
                lvl = []
                for cnt2 in cnts2:
                    if cv2.contourArea(cnt2) > 5:
                        s2 = cv2.approxPolyDP(cnt2, 0.3, True)
                        if len(s2) >= 3:
                            lvl.append({'points': s2.reshape(-1, 2).tolist(),
                                        'couleur': col})
                zones_motifs.append(lvl)

            pr("  contour : {0} pts  |  motifs : {1} niveaux".format(
                len(contour_pts),
                sum(len(z) for z in zones_motifs)))

        except Exception as e:
            pr("AVERTISSEMENT ortho : " + str(e))
            pr(traceback.format_exc())
            have_ortho = False

    # -----------------------------------------------------------------------
    # Fonctions de rendu (imbriquees pour acceder a yp, cm, etc.)
    # -----------------------------------------------------------------------

    def _px_to_paper_cm(col, row, zone_x, zone_y, zone_w, zone_h, paper_w, paper_h):
        """
        Convertit des coordonnees pixel ortho en coordonnees cm papier.
        Meme formule que render_raster :
          ox = zone_x + (zone_w - paper_w) / 2
          oy = zone_y + (zone_h - paper_h) / 2
          x_cm = ox + col * px_to_cm_paper
          y_cm = oy + row * px_to_cm_paper
        Y cm croissant vers le bas (yp() convertit ensuite en ReportLab pt).
        """
        ox = zone_x + (zone_w - paper_w) / 2
        oy = zone_y + (zone_h - paper_h) / 2
        x_cm = ox + col * px_to_cm_paper
        y_cm = oy + row * px_to_cm_paper
        return x_cm, y_cm

    def draw_cut_line(zone_x, zone_y, zone_w, zone_h, paper_w, paper_h):
        """
        Trace l'axe de coupe sur un quadrant (Q1, Q2 ou Q4).
        Utilise marker1_col/row et marker2_col/row (coords pixel ortho).
        Conversion via _px_to_paper_cm, identique a render_raster.
        """
        cx1, cy1 = _px_to_paper_cm(marker1_col, marker1_row,
                                    zone_x, zone_y, zone_w, zone_h, paper_w, paper_h)
        cx2, cy2 = _px_to_paper_cm(marker2_col, marker2_row,
                                    zone_x, zone_y, zone_w, zone_h, paper_w, paper_h)
        _draw_cut_line_cm(cx1, cy1, cx2, cy2)

    def _draw_cut_line_cm(cx1, cy1, cx2, cy2):
        """
        Trace l'axe de coupe entre deux points (cm, Y croissant vers le bas).
        - Ligne tirets passant par les 2 marqueurs, prolongee de EXTEND_CM de chaque cote
        - Traits epais dans le prolongement de l'axe aux deux extremites
        """
        import math as _m
        dx = cx2 - cx1
        dy = cy2 - cy1
        length = _m.sqrt(dx*dx + dy*dy)
        if length < 1e-9:
            return
        ux = dx / length
        uy = dy / length

        EXTEND_CM = 0.8
        TICK_CM   = 0.7

        ax = cx1 - ux * EXTEND_CM;  ay = cy1 - uy * EXTEND_CM
        bx = cx2 + ux * EXTEND_CM;  by = cy2 + uy * EXTEND_CM

        # Ligne tirets
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.6)
        c.setDash([0.25 * cm, 0.15 * cm])
        c.line(ax * cm, yp(ay), bx * cm, yp(by))
        c.setDash()

        # Traits epais dans le prolongement de l'axe
        c.setLineWidth(2.0)
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineCap(2)
        c.line((ax - ux * TICK_CM) * cm, yp(ay - uy * TICK_CM), ax * cm, yp(ay))
        c.line(bx * cm, yp(by), (bx + ux * TICK_CM) * cm, yp(by + uy * TICK_CM))
        c.setLineCap(0)

    def draw_mire(cx_cm, top_y_cm, mire_m_val, mire_unit_str, scale_d,
                  bar_h_cm=0.35, font_pt=7.5, show_scale=False):
        """Mire a toujours 4 divisions.
        mire_m_val  : valeur REELLE totale en metres (ex: 0.40 pour 40cm reel)
        Les graduations indiquent la valeur reelle en cm a chaque division.
        Exemple : mire_m_val=0.40 au 1/10 -> 4cm papier, labels 0,10,20,30,40cm
        """
        N = 4
        total_reel_cm = mire_m_val * 100.0        # valeur reelle totale en cm
        unit_reel_cm  = total_reel_cm / N         # valeur reelle d'une division en cm
        total_paper_cm = mire_m_val * 100.0 * scale_ratio  # taille papier en cm
        seg = total_paper_cm / N
        x0  = cx_cm - total_paper_cm / 2.0
        bar_top_pt = yp(top_y_cm)
        bar_h_pt   = bar_h_cm * cm
        c.setLineWidth(0.4)
        c.setStrokeColorRGB(0, 0, 0)
        for i in range(N):
            x1_pt = (x0 + i * seg) * cm
            x2_pt = (x0 + (i + 1) * seg) * cm
            if i % 2 == 0: c.setFillColorRGB(0, 0, 0)
            else:           c.setFillColorRGB(1, 1, 1)
            c.rect(x1_pt, bar_top_pt - bar_h_pt, x2_pt - x1_pt, bar_h_pt,
                   fill=1, stroke=1)
        c.setStrokeColorRGB(0, 0, 0)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", font_pt)
        tick_h = 0.12 * cm
        for i in range(N + 1):
            xg = (x0 + i * seg) * cm
            c.line(xg, bar_top_pt, xg, bar_top_pt + tick_h)
            val_cm = i * unit_reel_cm
            if val_cm == int(val_cm):
                val_str = "{0:.0f}".format(val_cm)
            else:
                val_str = "{0:.1f}".format(val_cm)
            label = "{0}cm".format(val_str) if i == N else val_str
            c.drawCentredString(xg, bar_top_pt + tick_h + 0.03 * cm, label)
        if show_scale:
            scale_str = "Echelle 1:{0}".format(scale_d) if scale_d > 1 else "Echelle 1:1"
            c.setFont("Helvetica", font_pt)
            c.drawCentredString(cx_cm * cm, bar_top_pt - bar_h_pt - 0.25 * cm, scale_str)

    def render_raster(img_path, zone_x, zone_y, zone_w, zone_h,
                      paper_w, paper_h):
        from reportlab.lib.utils import ImageReader
        import io
        ox = zone_x + (zone_w - paper_w) / 2
        oy = zone_y + (zone_h - paper_h) / 2
        # TIFF RGBA : composer sur fond blanc (alpha=0 -> blanc, pas noir)
        src = Image.open(img_path)
        if src.mode == 'RGBA':
            fond = Image.new('RGB', src.size, (255, 255, 255))
            fond.paste(src, mask=src.split()[3])  # canal alpha comme masque
            pil_img = fond
        else:
            pil_img = src.convert('RGB')
        buf = io.BytesIO()
        pil_img.save(buf, format='PNG')
        buf.seek(0)
        c.drawImage(ImageReader(buf),
                    ox * cm, yp(oy + paper_h),
                    width=paper_w * cm, height=paper_h * cm)

    def render_vecteur_archeo(zone_x, zone_y, zone_w, zone_h,
                               paper_w, paper_h):
        if not contour_pts: return
        off_x  = zone_x + (zone_w - paper_w) / 2
        off_y  = zone_y + (zone_h - paper_h) / 2
        bot_pt = yp(off_y + paper_h)
        lft_pt = off_x * cm
        s      = px_to_cm_paper * cm

        def tp(px, py):
            return lft_pt + px * s, bot_pt + (px_h - py) * s

        # Fond blanc forme contour
        c.setFillColorRGB(1, 1, 1); c.setStrokeColorRGB(1, 1, 1)
        p = c.beginPath()
        x0, y0 = tp(contour_pts[0][0], contour_pts[0][1])
        p.moveTo(x0, y0)
        for px2, py2 in contour_pts[1:]: p.lineTo(*tp(px2, py2))
        p.close(); c.drawPath(p, fill=1, stroke=0)

        # Motifs
        for lvl in zones_motifs:
            if not lvl: continue
            col = lvl[0]['couleur']
            c.setFillColorRGB(col, col, col)
            c.setStrokeColorRGB(col, col, col)
            c.setLineWidth(0.4)
            for zone in lvl:
                pts = zone['points']
                if len(pts) < 3: continue
                pz = c.beginPath()
                x0, y0 = tp(pts[0][0], pts[0][1])
                pz.moveTo(x0, y0)
                for px2, py2 in pts[1:]: pz.lineTo(*tp(px2, py2))
                pz.close(); c.drawPath(pz, fill=1, stroke=1)

        # Contour noir
        c.setStrokeColorRGB(0, 0, 0); c.setLineWidth(0.9)
        c.setLineCap(1); c.setLineJoin(1)
        pc = c.beginPath()
        x0, y0 = tp(contour_pts[0][0], contour_pts[0][1])
        pc.moveTo(x0, y0)
        for px2, py2 in contour_pts[1:]: pc.lineTo(*tp(px2, py2))
        pc.close(); c.drawPath(pc, fill=0, stroke=1)

        # --- Parsing SVG et rendu coupe ---
    SVG_NS = 'http://www.w3.org/2000/svg'

    def parse_svg():
        import xml.etree.ElementTree as ET2
        import re as _re
        tree = ET2.parse(svg_path)
        root = tree.getroot()
        def sn(t): return t.replace('{' + SVG_NS + '}', '')
        def pdim(s):
            s = s.strip()
            if s.endswith('mm'): return float(s[:-2]) / 1000
            if s.endswith('cm'): return float(s[:-2]) / 100
            if s.endswith('m'):  return float(s[:-1])
            return float(s)
        w = pdim(root.get('width', '0.1m'))
        h = pdim(root.get('height', '0.05m'))
        paths = []
        for el in root.iter():
            tag = sn(el.tag)
            if tag == 'path':
                paths.append({
                    'd':      el.get('d', ''),
                    'stroke': el.get('stroke', 'black'),
                    'sw_m':   float(el.get('stroke-width', str(w * 0.003))),
                    'dash':   el.get('stroke-dasharray', None)})
            elif tag == 'line':
                x1, y1 = float(el.get('x1', 0)), float(el.get('y1', 0))
                x2, y2 = float(el.get('x2', 0)), float(el.get('y2', 0))
                paths.append({
                    'd':      'M {0} {1} L {2} {3}'.format(x1, y1, x2, y2),
                    'stroke': el.get('stroke', 'black'),
                    'sw_m':   float(el.get('stroke-width', str(w * 0.003))),
                    'dash':   None})
        # Les dimensions reelles viennent de width/height du SVG (en m apres pdim).
        # write_svg ecrit width=real_w_cm et height=real_h_m (distance 3D M1-M2).
        # On calcule x0/y0 depuis le viewBox pour positionner correctement les paths.
        real_w = w
        real_h = h
        vb = root.get('viewBox', '')
        vb_parts = vb.replace(',', ' ').split()
        if len(vb_parts) == 4:
            real_x0 = float(vb_parts[0])
            real_y0 = float(vb_parts[1])
        else:
            # Fallback : bornes depuis les points
            all_x, all_y = [], []
            num_pat = r'[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?'
            pair_pat = _re.compile(num_pat + r',' + num_pat)
            for pi in paths:
                for pair in pair_pat.findall(pi['d']):
                    xv, yv = pair.split(',')
                    all_x.append(float(xv)); all_y.append(float(yv))
            real_x0 = min(all_x) if all_x else 0.0
            real_y0 = min(all_y) if all_y else 0.0
        return paths, real_w, real_h, real_x0, real_y0

    def _tok(d):
        """Tokenizer SVG robuste : gere les nombres negatifs apres virgule."""
        tokens = []; i = 0
        while i < len(d):
            ch = d[i]
            if ch in 'MmLlHhVvCcSsQqTtAaZz':
                tokens.append(ch); i += 1
            elif ch in '0123456789.' or ch in '+-':
                # Reconnaitre '-'/'+' comme debut de nombre ssi suivi de chiffre ou '.'
                if ch in '+-' and (i+1 >= len(d) or d[i+1] not in '0123456789.'):
                    i += 1; continue
                j = i
                if d[j] in '+-': j += 1
                while j < len(d) and d[j] in '0123456789': j += 1
                if j < len(d) and d[j] == '.':
                    j += 1
                    while j < len(d) and d[j] in '0123456789': j += 1
                if j < len(d) and d[j] in 'eE':
                    j += 1
                    if j < len(d) and d[j] in '+-': j += 1
                    while j < len(d) and d[j].isdigit(): j += 1
                try: tokens.append(float(d[i:j]))
                except ValueError: pass
                i = j
            else:
                i += 1
        return tokens

    def path_ops_svg_offset(d_str, left_pt, bot_pt, spt, flip_pt, x0_m, y0_m):
        """Parse un path SVG et retourne les ops ReportLab.
        Le SVG produit par write_svg a les Y deja inverses (flip-y),
        donc Y_svg croissant = vers le haut = sens ReportLab correct.
        bot_pt = yp(off_y + coupe_h_cm) = coordonnee ReportLab du bas de la zone.
        """
        tokens = _tok(d_str)
        ops = []; cx2 = cy2 = 0.0; cmd = 'M'; idx = 0

        def tp2(x, y):
            # Y SVG ici est deja flippe (flip-y dans write_svg), identique sens ReportLab
            return left_pt + (x - x0_m) * spt, bot_pt + (y - y0_m) * spt

        def eat(n):
            nonlocal idx
            v = [float(tokens[idx + i]) for i in range(n)]
            idx += n; return v

        while idx < len(tokens):
            t = tokens[idx]
            if isinstance(t, str): cmd = t; idx += 1; continue
            if   cmd == 'M': x, y = eat(2); cx2, cy2 = x, y; ops.append(('m', *tp2(cx2, cy2))); cmd = 'L'
            elif cmd == 'm': dx, dy = eat(2); cx2 += dx; cy2 += dy; ops.append(('m', *tp2(cx2, cy2))); cmd = 'l'
            elif cmd == 'L': x, y = eat(2); cx2, cy2 = x, y; ops.append(('l', *tp2(cx2, cy2)))
            elif cmd == 'l': dx, dy = eat(2); cx2 += dx; cy2 += dy; ops.append(('l', *tp2(cx2, cy2)))
            elif cmd == 'H': x = eat(1)[0]; cx2 = x; ops.append(('l', *tp2(cx2, cy2)))
            elif cmd == 'h': dx = eat(1)[0]; cx2 += dx; ops.append(('l', *tp2(cx2, cy2)))
            elif cmd == 'V': y = eat(1)[0]; cy2 = y; ops.append(('l', *tp2(cx2, cy2)))
            elif cmd == 'v': dy = eat(1)[0]; cy2 += dy; ops.append(('l', *tp2(cx2, cy2)))
            elif cmd == 'C':
                x1, y1, x2, y2, x, y = eat(6); cx2, cy2 = x, y
                ops.append(('c', *tp2(x1, y1), *tp2(x2, y2), *tp2(x, y)))
            elif cmd == 'c':
                dx1, dy1, dx2, dy2, dx, dy = eat(6)
                ops.append(('c', *tp2(cx2+dx1, cy2+dy1),
                                 *tp2(cx2+dx2, cy2+dy2),
                                 *tp2(cx2+dx,  cy2+dy)))
                cx2 += dx; cy2 += dy
            elif cmd in ('Z', 'z'): ops.append(('z',)); break
            else: idx += 1
        return ops

    def path_ops_svg(d_str, left_pt, bot_pt, spt, flip_pt):
        tokens = _tok(d_str)
        ops = []; cx2 = cy2 = 0.0; cmd = 'M'; idx = 0

        def tp2(x, y):
            return left_pt + x * spt, bot_pt + flip_pt - y * spt

        def eat(n):
            nonlocal idx
            v = [float(tokens[idx + i]) for i in range(n)]
            idx += n
            return v

        while idx < len(tokens):
            t = tokens[idx]
            if isinstance(t, str):
                cmd = t; idx += 1; continue
            if   cmd == 'M': x, y = eat(2); cx2, cy2 = x, y; ops.append(('m', *tp2(cx2, cy2))); cmd = 'L'
            elif cmd == 'm': dx, dy = eat(2); cx2 += dx; cy2 += dy; ops.append(('m', *tp2(cx2, cy2))); cmd = 'l'
            elif cmd == 'L': x, y = eat(2); cx2, cy2 = x, y; ops.append(('l', *tp2(cx2, cy2)))
            elif cmd == 'l': dx, dy = eat(2); cx2 += dx; cy2 += dy; ops.append(('l', *tp2(cx2, cy2)))
            elif cmd == 'H': x = eat(1)[0]; cx2 = x; ops.append(('l', *tp2(cx2, cy2)))
            elif cmd == 'h': dx = eat(1)[0]; cx2 += dx; ops.append(('l', *tp2(cx2, cy2)))
            elif cmd == 'V': y = eat(1)[0]; cy2 = y; ops.append(('l', *tp2(cx2, cy2)))
            elif cmd == 'v': dy = eat(1)[0]; cy2 += dy; ops.append(('l', *tp2(cx2, cy2)))
            elif cmd == 'C':
                x1, y1, x2, y2, x, y = eat(6); cx2, cy2 = x, y
                ops.append(('c', *tp2(x1, y1), *tp2(x2, y2), *tp2(x, y)))
            elif cmd == 'c':
                dx1, dy1, dx2, dy2, dx, dy = eat(6)
                ops.append(('c', *tp2(cx2+dx1, cy2+dy1),
                                 *tp2(cx2+dx2, cy2+dy2),
                                 *tp2(cx2+dx, cy2+dy)))
                cx2 += dx; cy2 += dy
            elif cmd in ('Z', 'z'):
                ops.append(('z',)); break
            else:
                idx += 1
        return ops

    def hex_rgb(s):
        named = {'black':(0,0,0),'white':(1,1,1),
                 'gray':(.5,.5,.5),'grey':(.5,.5,.5),'none':None}
        sl = s.lower()
        if sl in named: return named[sl]
        if s.startswith('#'):
            h = s[1:]
            if len(h) == 3: h = h[0]*2 + h[1]*2 + h[2]*2
            return (int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255)
        return (0, 0, 0)

    def draw_ops(ops, rgb, lw, dash=None, spt=1.0):
        if rgb is None: return
        r, g, b = rgb
        c.setStrokeColorRGB(r, g, b)
        c.setLineWidth(max(lw, 0.3))
        if dash:
            parts = [float(x) * spt for x in dash.replace(',', ' ').split()]
            if len(parts) == 1: parts = parts * 2
            c.setDash(parts)
        else:
            c.setDash()
        p = c.beginPath()
        for op in ops:
            k = op[0]
            if   k == 'm': p.moveTo(op[1], op[2])
            elif k == 'l': p.lineTo(op[1], op[2])
            elif k == 'c': p.curveTo(op[1],op[2],op[3],op[4],op[5],op[6])
            elif k == 'z': p.close()
        c.drawPath(p, stroke=1, fill=0)
        c.setDash()

    def render_coupe(zone_x, zone_y, zone_w, zone_h):
        paths, real_w_m, real_h_m, x0_m, y0_m = parse_svg()
        # Dimensions papier de la coupe a l'echelle
        coupe_w_cm = real_w_m * 100.0 * scale_ratio
        coupe_h_cm = real_h_m * 100.0 * scale_ratio
        # Centrer dans la zone
        off_x = zone_x + (zone_w - coupe_w_cm) / 2
        off_y = zone_y + (zone_h - coupe_h_cm) / 2
        bot_pt  = yp(off_y + coupe_h_cm)   # ReportLab y du bas de la coupe
        top_pt  = yp(off_y)                 # ReportLab y du haut (non utilise ici)
        left_pt = off_x * cm
        flip_pt = real_h_m * scale_m_to_pt
        for pi in paths:
            rgb = hex_rgb(pi['stroke'])
            # bot_pt est le bas ReportLab ; SVG Y deja flippe -> utiliser bot_pt
            ops = path_ops_svg_offset(pi['d'], left_pt, bot_pt,
                                      scale_m_to_pt, flip_pt,
                                      x0_m, y0_m)
            draw_ops(ops, rgb, pi['sw_m'] * scale_m_to_pt,
                     dash=pi['dash'], spt=scale_m_to_pt)

    def quad_label(x_cm, y_cm, text):
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(x_cm * cm, yp(y_cm + 0.42), text)

    def no_data(cx_cm, cy_cm):
        c.setFont("Helvetica-Oblique", 7)
        c.setFillColorRGB(.5, .5, .5)
        c.drawCentredString(cx_cm * cm, yp(cy_cm), "(non disponible)")

    # -----------------------------------------------------------------------
    # Canvas ReportLab
    # -----------------------------------------------------------------------
    # Si pas d'ortho mais marqueurs disponibles : calculer position des marqueurs
    # en coordonnees cm directement (pas de pixels intermediaires).
    # On reuse la meme logique _px_to_paper_cm en traitant col/row comme des cm.
    if not have_ortho and have_markers:
        # Les fractions se rapportent aux dimensions de la coupe papier
        marker1_col = marker1_frac_x * coupe_paper_w  # cm dans l'image
        marker1_row = marker1_frac_y * coupe_paper_h
        marker2_col = marker2_frac_x * coupe_paper_w
        marker2_row = marker2_frac_y * coupe_paper_h
        # px_to_cm_paper = 1 car les "pixels" sont deja en cm
        px_to_cm_paper = 1.0
        ortho_paper_w  = coupe_paper_w
        ortho_paper_h  = coupe_paper_h
        pr("  markers (sans ortho): col={0:.2f}cm,row={1:.2f}cm / col={2:.2f}cm,row={3:.2f}cm".format(
            marker1_col, marker1_row, marker2_col, marker2_row))

    pr("Creation du PDF...")
    c = rl_canvas.Canvas(pdf_path, pagesize=(A4_W_cm * cm, A4_H_cm * cm))
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, A4_W_cm * cm, A4_H_cm * cm, fill=1, stroke=0)

    date_str = datetime.now().strftime("%d/%m/%Y")

    # Titre
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0, 0, 0)
    c.drawCentredString(A4_W_cm / 2 * cm, yp(MARGIN + 0.65),
                        "Echelle 1:{0}   -   {1}".format(scale_denom, date_str))

    # Separateurs quadrants
    c.setStrokeColorRGB(0.72, 0.72, 0.72); c.setLineWidth(0.25)
    sep_x = MARGIN + qw + GAP / 2
    sep_y = q_top  + qh + GAP / 2
    c.line(sep_x * cm, yp(q_top), sep_x * cm, yp(q_bot + qh))
    c.line(MARGIN * cm, yp(sep_y), (MARGIN + total_w) * cm, yp(sep_y))

    cx_left  = q_left  + qw / 2
    cx_right = q_right + qw / 2
    mire_top_y = q_top + LABEL_H + draw_h + MIRE_H * 0.3
    mire_bot_y = q_bot + LABEL_H + draw_h + MIRE_H * 0.3

    # === HAUT-GAUCHE : Photo ortho ===
    pr("  Q1 - photo ortho...")
    quad_label(q_left, q_top, "Orthomosaique (photo)")
    if have_ortho:
        render_raster(ortho_tif,
                      q_left, q_top + LABEL_H, qw, draw_h,
                      ortho_paper_w, ortho_paper_h)
        if have_markers:
            draw_cut_line(q_left, q_top + LABEL_H, qw, draw_h,
                          ortho_paper_w, ortho_paper_h)
        draw_mire(cx_left, mire_top_y, mire_m_disp, mire_unit_disp, scale_denom)
    else:
        no_data(cx_left, q_top + qh / 2)

    # === HAUT-DROITE : Dessin archeo raster ===
    pr("  Q2 - dessin raster...")
    quad_label(q_right, q_top, "Dessin archeologique (raster)")
    if have_ortho and dessin_np is not None:
        tmp = tempfile.mktemp(suffix='.png')
        try:
            Image.fromarray(dessin_np).convert('RGB').save(tmp)
            render_raster(tmp,
                          q_right, q_top + LABEL_H, qw, draw_h,
                          ortho_paper_w, ortho_paper_h)
        finally:
            if os.path.exists(tmp): os.remove(tmp)
        if have_markers:
            draw_cut_line(q_right, q_top + LABEL_H, qw, draw_h,
                          ortho_paper_w, ortho_paper_h)
        draw_mire(cx_right, mire_top_y, mire_m_disp, mire_unit_disp, scale_denom)
    else:
        no_data(cx_right, q_top + qh / 2)

    # === BAS-GAUCHE : Coupe SVG ===
    pr("  Q3 - coupe vecteur...")
    quad_label(q_left, q_bot, "Coupe ceramique (vecteur)")
    render_coupe(q_left, q_bot + LABEL_H, qw, draw_h)
    draw_mire(cx_left, mire_bot_y, mire_m_disp, mire_unit_disp, scale_denom, show_scale=True)

    # === BAS-DROITE : Dessin vecteur ===
    pr("  Q4 - dessin vecteur...")
    quad_label(q_right, q_bot, "Dessin archeologique (vecteur)")
    if have_ortho and contour_pts:
        render_vecteur_archeo(q_right, q_bot + LABEL_H, qw, draw_h,
                               ortho_paper_w, ortho_paper_h)
        if have_markers:
            draw_cut_line(q_right, q_bot + LABEL_H, qw, draw_h,
                          ortho_paper_w, ortho_paper_h)
        draw_mire(cx_right, mire_bot_y, mire_m_disp, mire_unit_disp, scale_denom)
    else:
        no_data(cx_right, q_bot + qh / 2)

    # Pied de page
    c.setFont("Helvetica", 5.5); c.setFillColorRGB(.4, .4, .4)
    c.drawString(MARGIN * cm, yp(A4_H_cm - 0.55),
                 "coupe_ceramique7   |   {0}   |   Mire = {1}   |   "
                 "{2:.1f} cm x {3:.1f} cm".format(
                     date_str, mire_label,
                     real_w_m * 100, real_h_m * 100))

    c.save()
    pr("PDF cree : " + pdf_path)
    return pdf_path


# ===========================================================================
# POINT D'ENTREE — log ouvert EN PREMIER, avant tout import lourd
# ===========================================================================

if __name__ == '__main__':

    # 1. Trouver le meta_path (peut planter si tkinter absent -> on rattrape)
    meta_path = None
    log_path  = None
    try:
        meta_path = find_meta_path()
    except Exception as e:
        # Pas encore de log, ecrire sur stderr
        sys.stderr.write("Erreur find_meta_path : " + str(e) + "\n")
        sys.exit(1)

    if not meta_path:
        sys.stderr.write("Aucun fichier meta selectionne.\n")
        sys.exit(1)

    # 2. Ouvrir le log (meme si meta introuvable, on logue)
    log_path = meta_base(meta_path) + '_pdf_log.txt'
    try:
        log = open(log_path, 'w', encoding='utf-8', errors='replace')
    except Exception:
        # Fallback : log dans le dossier temp
        import tempfile as _tmp
        log_path = os.path.join(_tmp.gettempdir(), 'coupe_ceramique7_pdf_log.txt')
        log = open(log_path, 'w', encoding='utf-8', errors='replace')

    # 3. Executer
    exit_code = 0
    try:
        run(meta_path, log)
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else 1
        log.write("Exit({0})\n".format(exit_code))
    except Exception:
        log.write("\n!!! ERREUR FATALE !!!\n")
        log.write(traceback.format_exc())
        log.flush()
        exit_code = 1
    finally:
        log.write("\nLog : " + log_path + "\n")
        log.close()

    sys.exit(exit_code)

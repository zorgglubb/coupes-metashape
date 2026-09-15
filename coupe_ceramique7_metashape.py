"""
coupe_ceramique7_metashape.py
=============================================================
Script Metashape 1.5.x et 2.x - AUCUNE dependance externe.
Version Metashape detectee automatiquement au lancement.

Logique de coupe IDENTIQUE au script v5 original :
  - sort_points_along_path (voisin le plus proche)
  - douglas_peucker (tolerance 0.01% de la dimension max)
  - rotation 90deg horaire : (x,y) -> (y, -x)
  - detection ferme/ouvert par couverture angulaire > 80%
  - modele ferme : tri par angle depuis le centre
  - modele ouvert : cote gauche trie par Y + create_inner_contour_right
  - extension jusqu'aux marqueurs

Produit :
  - coupe.svg  (coordonnees en metres reels, 1 unite SVG = 1 m)
  - coupe_ortho.tif
  - coupe.meta.txt  -> lu par coupe_ceramique7_pdf.py
"""

import Metashape
import math
import os

# ---------------------------------------------------------------------------
# Detection version Metashape (1.x vs 2.x)
# ---------------------------------------------------------------------------
def _metashape_major():
    """Retourne le numero de version majeure (1 ou 2)."""
    try:
        v = Metashape.app.version          # ex: "1.5.2" ou "2.1.3"
        return int(str(v).split(".")[0])
    except Exception:
        return 1  # fallback 1.x

MS_MAJOR = _metashape_major()
print("Metashape version : {0}  (API majeure : {1})".format(
    Metashape.app.version, MS_MAJOR))

# ---------------------------------------------------------------------------
NORMALIZED_SCALES = [1,2,3,4,5,10,20,25,50,100,200,250,500,1000]

def choose_scale(real_dim_m, max_paper_cm):
    for d in NORMALIZED_SCALES:
        r = 1.0/d
        if real_dim_m*r*100.0 <= max_paper_cm:
            return r, d
    r = max_paper_cm/(real_dim_m*100.0)
    return r, int(round(1.0/r))

def best_unit(dim_m):
    if dim_m >= 1.0:  return "m",  1.0
    if dim_m >= 0.01: return "cm", 100.0
    return                   "mm", 1000.0

def round_to_nice_number(value):
    """Identique v5"""
    if value <= 0: return 0.001
    magnitude = math.floor(math.log10(value))
    normalized = value / (10**magnitude)
    if normalized < 1.5:   nice = 1
    elif normalized < 3:   nice = 2
    elif normalized < 7:   nice = 5
    else:                  nice = 10
    return nice * (10**magnitude)

# ---------------------------------------------------------------------------
# Utilitaires vectoriels
# ---------------------------------------------------------------------------
def vector_cross(v1, v2):
    return Metashape.Vector([
        v1.y*v2.z - v1.z*v2.y,
        v1.z*v2.x - v1.x*v2.z,
        v1.x*v2.y - v1.y*v2.x
    ])

def vector_normalize(v):
    norm = math.sqrt(v.x**2+v.y**2+v.z**2)
    if norm > 0:
        return Metashape.Vector([v.x/norm, v.y/norm, v.z/norm])
    return v

def vector_dot(v1, v2):
    return v1.x*v2.x + v1.y*v2.y + v1.z*v2.z

# ---------------------------------------------------------------------------
# Marqueurs
# ---------------------------------------------------------------------------
def get_user_points(chunk):
    marker_list = [m for m in (chunk.markers or []) if m.position]
    if len(marker_list) < 2:
        Metashape.app.messageBox("Placez au moins 2 marqueurs avec une position 3D.")
        return None, None
    names = "\n".join("{0}: {1}".format(i, m.label) for i,m in enumerate(marker_list))
    result = Metashape.app.getString(
        "Marqueurs disponibles:\n{0}\n\nEntrez les indices (ex: 0,1):".format(names))
    if not result: return None, None
    try:
        indices = [int(x.strip()) for x in result.split(',')]
        if len(indices) != 2:
            Metashape.app.messageBox("Entrez exactement 2 indices!")
            return None, None
        return marker_list[indices[0]].position, marker_list[indices[1]].position
    except (ValueError, IndexError):
        Metashape.app.messageBox("Indices invalides!")
        return None, None

# ---------------------------------------------------------------------------
# Plan de coupe (identique v5)
# ---------------------------------------------------------------------------
def create_cutting_plane(point1, point2):
    axis_vector = Metashape.Vector([point2.x-point1.x, point2.y-point1.y, point2.z-point1.z])
    axis_length = math.sqrt(axis_vector.x**2+axis_vector.y**2+axis_vector.z**2)
    axis_normalized = vector_normalize(axis_vector)
    if abs(axis_normalized.z) < 0.9:
        up_vector = Metashape.Vector([0,0,1])
    else:
        up_vector = Metashape.Vector([1,0,0])
    normal   = vector_normalize(vector_cross(axis_normalized, up_vector))
    binormal = vector_normalize(vector_cross(axis_normalized, normal))
    center   = Metashape.Vector([(point1.x+point2.x)/2,
                                   (point1.y+point2.y)/2,
                                   (point1.z+point2.z)/2])
    return {
        'center': center, 'normal': normal,
        'axis': axis_normalized, 'binormal': binormal,
        'length': axis_length, 'point1': point1, 'point2': point2
    }

# ---------------------------------------------------------------------------
# Section 3D (identique v5)
# ---------------------------------------------------------------------------
def extract_section_points(chunk, plane_info):
    model = get_model(chunk)
    if not model or not model.faces: return []
    vertices = model.vertices
    section_points = []
    for face in model.faces:
        v_indices  = [face.vertices[i] for i in range(3)]
        tri_verts  = [vertices[i].coord for i in v_indices]
        for i in range(3):
            v1 = tri_verts[i]
            v2 = tri_verts[(i+1)%3]
            vec1 = Metashape.Vector([v1.x-plane_info['center'].x,
                                      v1.y-plane_info['center'].y,
                                      v1.z-plane_info['center'].z])
            d1 = vector_dot(plane_info['normal'], vec1)
            vec2 = Metashape.Vector([v2.x-plane_info['center'].x,
                                      v2.y-plane_info['center'].y,
                                      v2.z-plane_info['center'].z])
            d2 = vector_dot(plane_info['normal'], vec2)
            if d1*d2 < 0:
                t = d1/(d1-d2)
                section_points.append(Metashape.Vector([
                    v1.x+t*(v2.x-v1.x),
                    v1.y+t*(v2.y-v1.y),
                    v1.z+t*(v2.z-v1.z)]))
    return section_points

def project_to_2d(points_3d, plane_info):
    points_2d = []
    for point in points_3d:
        vec = Metashape.Vector([point.x-plane_info['center'].x,
                                 point.y-plane_info['center'].y,
                                 point.z-plane_info['center'].z])
        x = vector_dot(vec, plane_info['axis'])
        y = vector_dot(vec, plane_info['binormal'])
        points_2d.append((x, y))
    return points_2d

# ---------------------------------------------------------------------------
# Simplification (identique v5 : sort_along_path + douglas_peucker)
# ---------------------------------------------------------------------------
def sort_points_along_path(points):
    if len(points) < 2: return points
    sorted_points = [points[0]]
    remaining = list(points[1:])
    while remaining:
        last = sorted_points[-1]
        min_dist = float('inf')
        closest_idx = 0
        for i, pt in enumerate(remaining):
            d = math.sqrt((pt[0]-last[0])**2+(pt[1]-last[1])**2)
            if d < min_dist:
                min_dist = d; closest_idx = i
        sorted_points.append(remaining.pop(closest_idx))
    return sorted_points

def point_line_distance(point, line_start, line_end):
    px,py = point; x1,y1 = line_start; x2,y2 = line_end
    lsq = (x2-x1)**2+(y2-y1)**2
    if lsq == 0:
        return math.sqrt((px-x1)**2+(py-y1)**2)
    t = max(0, min(1, ((px-x1)*(x2-x1)+(py-y1)*(y2-y1))/lsq))
    return math.sqrt((px-x1-t*(x2-x1))**2+(py-y1-t*(y2-y1))**2)

def douglas_peucker(points, tolerance):
    if len(points) < 3: return points
    first = points[0]; last = points[-1]
    max_dist = 0; max_idx = 0
    for i in range(1, len(points)-1):
        d = point_line_distance(points[i], first, last)
        if d > max_dist: max_dist = d; max_idx = i
    if max_dist > tolerance:
        left  = douglas_peucker(points[:max_idx+1], tolerance)
        right = douglas_peucker(points[max_idx:],   tolerance)
        return left[:-1]+right
    return [first, last]

def simplify_contour(points, tolerance):
    if len(points) < 3: return points
    return douglas_peucker(sort_points_along_path(points), tolerance)

# ---------------------------------------------------------------------------
# Contour interieur vers la droite (copie exacte v5 create_inner_contour_right)
# ---------------------------------------------------------------------------
def create_inner_contour_right(points, thickness=0.005):
    if len(points) < 2: return []
    inner_points = []
    for i in range(len(points)):
        p1 = points[i]
        if i == 0:
            p2 = points[i+1]
            dx = p2[0]-p1[0]; dy = p2[1]-p1[1]
            length = math.sqrt(dx**2+dy**2)
            if length > 0:
                nx = dy/length; ny = -dx/length
            else: continue
        elif i == len(points)-1:
            p0 = points[i-1]
            dx = p1[0]-p0[0]; dy = p1[1]-p0[1]
            length = math.sqrt(dx**2+dy**2)
            if length > 0:
                nx = dy/length; ny = -dx/length
            else: continue
        else:
            p0 = points[i-1]; p2 = points[i+1]
            dx1=p1[0]-p0[0]; dy1=p1[1]-p0[1]; l1=math.sqrt(dx1**2+dy1**2)
            dx2=p2[0]-p1[0]; dy2=p2[1]-p1[1]; l2=math.sqrt(dx2**2+dy2**2)
            if l1>0 and l2>0:
                nx1=dy1/l1; ny1=-dx1/l1
                nx2=dy2/l2; ny2=-dx2/l2
                nx=(nx1+nx2)/2; ny=(ny1+ny2)/2
                ln=math.sqrt(nx**2+ny**2)
                if ln>0: nx/=ln; ny/=ln
            else: continue
        inner_points.append((p1[0]+nx*thickness, p1[1]+ny*thickness))
    return inner_points

# ---------------------------------------------------------------------------
# Preparation coupe (logique EXACTE v5 save_section_svg)
# ---------------------------------------------------------------------------
def prepare_section_v5(points_2d, plane_info, scale_factor):
    """
    Reproduit exactement la logique de save_section_svg du v5.
    Retourne dict avec tous les elements pour le rendu.
    """
    # 1. Convertir en metres
    pts_m = [(x*scale_factor, y*scale_factor) for x,y in points_2d]

    # 2. Etendre jusqu'aux marqueurs (identique v5)
    xs_all = [p[0] for p in pts_m]
    axis_length   = plane_info['length'] * scale_factor
    x_axis_min    = -axis_length/2
    x_axis_max    =  axis_length/2
    x_min_model   = min(xs_all)
    x_max_model   = max(xs_all)

    if x_min_model > x_axis_min:
        close = [(x,y) for x,y in pts_m if x < x_min_model+0.001]
        if close:
            avg_y = sum(p[1] for p in close)/len(close)
            pts_m.append((x_axis_min, avg_y))
    if x_max_model < x_axis_max:
        close = [(x,y) for x,y in pts_m if x > x_max_model-0.001]
        if close:
            avg_y = sum(p[1] for p in close)/len(close)
            pts_m.append((x_axis_max, avg_y))

    # 3. Simplification tolerance 0.01%
    xs_t=[p[0] for p in pts_m]; ys_t=[p[1] for p in pts_m]
    max_dim = max(max(xs_t)-min(xs_t), max(ys_t)-min(ys_t))
    tolerance = max_dim * 0.0001
    pts_s = simplify_contour(pts_m, tolerance)

    # 4. Rotation 90deg horaire : (x,y) -> (y, -x)  [identique v5]
    pts_r = [(y, -x) for x,y in pts_s]

    # 5. Detection ferme/ouvert (identique v5)
    xs3=[p[0] for p in pts_r]; ys3=[p[1] for p in pts_r]
    x_min_all=min(xs3); x_max_all=max(xs3)
    x_median=(x_min_all+x_max_all)/2

    center_x = sum(xs3)/len(xs3)
    center_y = sum(ys3)/len(ys3)

    def angle_from_center(pt):
        return math.atan2(pt[1]-center_y, pt[0]-center_x)

    pts_by_angle = sorted(pts_r, key=angle_from_center)
    angles = [angle_from_center(p) for p in pts_by_angle]
    angle_gaps = []
    for i in range(len(angles)):
        gap = angles[(i+1)%len(angles)] - angles[i]
        if gap < 0: gap += 2*math.pi
        angle_gaps.append(gap)
    max_gap       = max(angle_gaps)
    coverage      = (2*math.pi - max_gap)/(2*math.pi)

    distances = []
    for i in range(len(pts_by_angle)):
        p1=pts_by_angle[i]; p2=pts_by_angle[(i+1)%len(pts_by_angle)]
        distances.append(math.sqrt((p2[0]-p1[0])**2+(p2[1]-p1[1])**2))
    avg_dist = sum(distances)/len(distances) if distances else 1
    max_dist = max(distances) if distances else 1

    is_closed = (coverage > 0.80) and (max_dist < 10*avg_dist)

    print("Couverture angulaire: {0:.1f}% | Modele: {1}".format(
        coverage*100, "FERME" if is_closed else "OUVERT"))

    if is_closed:
        final = pts_by_angle
        inner = []
    else:
        # Cote gauche trie par Y (identique v5)
        left_side = [p for p in pts_r if p[0] <= x_median]
        # Apres rotation (x,y)->( y,-x), les extensions aux marqueurs ont
        # y_new = +axis_length_r/2 ou -axis_length_r/2.
        # Si leur x_new (= ancien y) > x_median, ils sont exclus du filtre
        # et la coupe ne s'etend pas jusqu'aux marqueurs.
        # On force l'inclusion des points extremes de l'axe (|y| proche de max).
        axis_length_r = axis_length  # apres scale_factor, en metres
        y_thresh = axis_length_r * 0.5 * 0.99  # 99% de la demi-longueur
        extremes = [p for p in pts_r if abs(p[1]) >= y_thresh]
        for ep in extremes:
            if ep not in left_side:
                left_side.append(ep)
        left_side = sorted(left_side, key=lambda p: p[1])
        final = left_side
        inner = create_inner_contour_right(left_side, thickness=0.005)

    xs_f=[p[0] for p in final]; ys_f=[p[1] for p in final]
    min_x,max_x = min(xs_f),max(xs_f)
    min_y,max_y = min(ys_f),max(ys_f)
    real_w = max_x-min_x
    # real_h = etendue Y reelle des points finaux.
    # Les points extremes de l'axe (extensions aux marqueurs) sont maintenant
    # inclus dans final, donc max_y-min_y = axis_length.
    real_h = max_y-min_y

    # Mire : vise 5 cm reels, adapte automatiquement selon taille du tesson
    mire_target_m = 0.05  # 5 cm cible
    max_dim = max(real_w, real_h)
    if mire_target_m <= max_dim:
        mire_m   = mire_target_m
        mire_val = 5.0
        unit     = "cm"
    else:
        unit, umult = best_unit(max_dim)
        real_w_disp = real_w * umult
        mire_val    = round_to_nice_number(real_w_disp)
        mire_m      = mire_val / umult

    return dict(
        points=final, inner=inner, is_closed=is_closed,
        min_x=min_x, max_x=max_x, min_y=min_y, max_y=max_y,
        real_w_m=real_w, real_h_m=real_h,
        mire_m=mire_m, mire_val=mire_val, mire_unit=unit
    )

# ---------------------------------------------------------------------------
# Ecriture SVG (coordonnees metres reels)
# ---------------------------------------------------------------------------
def write_svg(sec, output_path):
    pts=sec['points']; inner=sec['inner']
    min_x=sec['min_x']; min_y=sec['min_y']; max_y=sec['max_y']
    real_w=sec['real_w_m']; real_h=sec['real_h_m']

    # Dimensions en cm pour affichage correct dans les viewers SVG
    real_w_cm = real_w * 100.0
    real_h_cm = real_h * 100.0

    # stroke-width en metres (1 unite SVG = 1 m dans les paths)
    sw_o = 0.0005   # 0.05 cm
    sw_i = 0.0003   # 0.03 cm

    # Transformation de flip vertical pour les viewers SVG :
    # Les coords des paths sont en metres avec Y croissant vers le haut (repere 3D).
    # SVG a Y croissant vers le bas -> sans flip, le tesson est visuellement inverse.
    # matrix(1,0,0,-1,0,flip_ty) : x'=x, y'=flip_ty-y
    # flip_ty = max_y + min_y -> le haut du tesson (max_y) passe en bas du viewBox,
    # le bas (min_y) passe en haut. Visuellement correct dans Inkscape/navigateur.
    # Le script PDF (parse_svg) ignore le transform et lit les coords directement -> OK.
    flip_ty = max_y + min_y

    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="{0:.4f}cm" height="{1:.4f}cm" '
        'viewBox="{2:.8f} {3:.8f} {4:.8f} {5:.8f}">'.format(
            real_w_cm, real_h_cm, min_x, min_y, real_w, real_h),
        '<!-- COUPE_META real_w_m={0:.8f} real_h_m={1:.8f} '
        'mire_m={2:.8f} mire_val={3:.8f} mire_unit={4} '
        'is_closed={5} -->'.format(
            real_w, real_h, sec['mire_m'], sec['mire_val'],
            sec['mire_unit'], 1 if sec['is_closed'] else 0),
        # Groupe avec flip Y pour affichage visuel correct
        '<g transform="matrix(1,0,0,-1,0,{0:.8f})">'.format(flip_ty)
    ]

    if len(pts) > 1:
        d = 'M {0:.6f},{1:.6f}'.format(pts[0][0], pts[0][1])
        for x,y in pts[1:]:
            d += ' L {0:.6f},{1:.6f}'.format(x, y)
        if sec['is_closed']: d += ' Z'
        lines.append('<path d="{0}" fill="none" stroke="black" '
                     'stroke-width="{1:.6f}" '
                     'stroke-linejoin="round" stroke-linecap="round"/>'.format(d, sw_o))

    if inner and len(inner) > 1:
        d = 'M {0:.6f},{1:.6f}'.format(inner[0][0], inner[0][1])
        for x,y in inner[1:]:
            d += ' L {0:.6f},{1:.6f}'.format(x, y)
        lines.append('<path d="{0}" fill="none" stroke="gray" '
                     'stroke-width="{1:.6f}" '
                     'stroke-dasharray="{2:.6f},{2:.6f}" '
                     'stroke-linejoin="round" stroke-linecap="round"/>'.format(
                         d, sw_i, sw_i*3))

    lines.append('</g>')
    lines.append('</svg>')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print("SVG : {0:.4f}cm x {1:.4f}cm -> {2}".format(real_w_cm, real_h_cm, output_path))

# ---------------------------------------------------------------------------
# Export TIFF (4 variantes API Metashape 1.5.x) + TFW world file
# ---------------------------------------------------------------------------
def write_tfw(tiff_path, ortho):
    """
    Ecrit le fichier world (.tfw) associe au TIFF.
    Format TFW (6 lignes) :
      pixel_size_x   (m/pixel, positif)
      rotation_x     (0)
      rotation_y     (0)
      pixel_size_y   (m/pixel, negatif car Y descend)
      x_centre_pixel_haut_gauche
      y_centre_pixel_haut_gauche
    On lit les attributs de l'orthomosaique Metashape.
    """
    tfw_path = os.path.splitext(tiff_path)[0] + '.tfw'
    try:
        res = ortho.resolution          # m/pixel
        # Coin haut-gauche de l'ortho en coordonnees monde
        # Metashape expose left/top sur certaines versions, sinon on utilise
        # la transformation de l'ortho.
        left = None; top = None
        try:
            left = ortho.left
            top  = ortho.top
        except AttributeError:
            pass
        if left is None:
            try:
                left = ortho.transform[3]   # colonne 3 = tx
                top  = ortho.transform[7]   # ligne  3 = ty  (matrice 3x4)
            except Exception:
                pass
        if left is None:
            print("TFW : impossible de lire les coordonnees de l'ortho.")
            return False
        # Le centre du premier pixel est decale d'un demi-pixel depuis le coin
        cx = left + res / 2.0
        cy = top  - res / 2.0
        with open(tfw_path, 'w') as f:
            f.write("{0:.10f}\n".format(res))   # pixel size X (positif)
            f.write("0.0000000000\n")            # rotation X
            f.write("0.0000000000\n")            # rotation Y
            f.write("{0:.10f}\n".format(-res))   # pixel size Y (negatif)
            f.write("{0:.10f}\n".format(cx))     # X centre pixel haut-gauche
            f.write("{0:.10f}\n".format(cy))     # Y centre pixel haut-gauche
        print("TFW ecrit : {0}  (resolution {1:.6f} m/px)".format(tfw_path, res))
        return True
    except Exception as e:
        print("TFW erreur : {0}".format(e))
        return False

def export_ortho_tiff(chunk, tiff_path):
    if not chunk.orthomosaic:
        print("Pas d'orthomosaique."); return False, 0.0
    ortho = chunk.orthomosaic
    resolution = 0.0
    try: resolution = ortho.resolution
    except Exception: pass

    def ok(): return os.path.exists(tiff_path) and os.path.getsize(tiff_path)>0

    # Metashape 2.x : exportRaster remplace exportOrthomosaic
    # Metashape 1.x : exportOrthomosaic (plusieurs variantes d'API selon sous-version)
    if MS_MAJOR >= 2:
        variantes = [
            lambda: chunk.exportRaster(tiff_path,
                source_data=Metashape.DataSource.OrthomosaicData,
                image_format=Metashape.ImageFormat.ImageFormatTIFF,
                white_background=True),
            lambda: chunk.exportRaster(tiff_path,
                source_data=Metashape.DataSource.OrthomosaicData,
                image_format=Metashape.ImageFormat.ImageFormatTIFF),
            lambda: chunk.exportRaster(tiff_path,
                source_data=Metashape.DataSource.OrthomosaicData),
            lambda: chunk.exportRaster(tiff_path),
        ]
    else:
        variantes = [
            lambda: chunk.exportOrthomosaic(tiff_path, Metashape.ImageFormat.ImageFormatTIFF, white_background=True),
            lambda: chunk.exportOrthomosaic(tiff_path, Metashape.RasterFormat.RasterFormatTIFF, white_background=True),
            lambda: chunk.exportOrthomosaic(tiff_path, image_format=Metashape.ImageFormat.ImageFormatTIFF, white_background=True),
            lambda: chunk.exportOrthomosaic(tiff_path, white_background=True),
            lambda: chunk.exportOrthomosaic(tiff_path, Metashape.ImageFormat.ImageFormatTIFF),
            lambda: chunk.exportOrthomosaic(tiff_path, Metashape.RasterFormat.RasterFormatTIFF),
            lambda: chunk.exportOrthomosaic(tiff_path, image_format=Metashape.ImageFormat.ImageFormatTIFF),
            lambda: chunk.exportOrthomosaic(tiff_path),
        ]

    for attempt, fn in enumerate(variantes):
        try:
            fn()
            if ok():
                print("TIFF exporte (variante {0})".format(attempt+1))
                # Ecrire le TFW
                write_tfw(tiff_path, ortho)
                return True, resolution
        except Exception as e:
            print("Var {0}: {1}".format(attempt+1, e))

    print("ECHEC export TIFF."); return False, 0.0

# ---------------------------------------------------------------------------
# Meta.txt
# ---------------------------------------------------------------------------
def write_meta(path, sec, rw, rh, ortho_tiff, ortho_res, svg_path, marker1_2d=None, marker2_2d=None):
    lines = [
        "svg_path={0}".format(svg_path),
        "ortho_tiff={0}".format(ortho_tiff or ""),
        "ortho_res_m={0}".format(ortho_res),
        "real_w_m={0}".format(rw),
        "real_h_m={0}".format(rh),
        "mire_m={0}".format(sec['mire_m']),
        "mire_val={0}".format(sec['mire_val']),
        "mire_unit={0}".format(sec['mire_unit']),
        "is_closed={0}".format(1 if sec['is_closed'] else 0),
    ]
    # Fraction (0..1) de position des marqueurs dans l'ortho
    if marker1_2d is not None:
        lines.append("marker1_frac_x={0:.8f}".format(marker1_2d[0]))
        lines.append("marker1_frac_y={0:.8f}".format(marker1_2d[1]))
    if marker2_2d is not None:
        lines.append("marker2_frac_x={0:.8f}".format(marker2_2d[0]))
        lines.append("marker2_frac_y={0:.8f}".format(marker2_2d[1]))
    with open(path,'w',encoding='utf-8') as f: f.write('\n'.join(lines))
    print("Meta: {0}".format(path))

# ---------------------------------------------------------------------------
# Lancement exe PDF
# ---------------------------------------------------------------------------
def find_pdf_script():
    """Cherche coupe_ceramique7_pdf (.py ou .exe) + l'executable python.
    Retourne (commande_liste) ou None.
    """
    here = os.path.dirname(os.path.abspath(__file__))

    # 1. .exe dans le meme dossier ou PATH
    for search in [here] + os.environ.get("PATH","").split(os.pathsep):
        p = os.path.join(search, "coupe_ceramique7_pdf.exe")
        if os.path.isfile(p):
            return [p]

    # 2. .py dans le meme dossier (prioritaire)
    py_script = os.path.join(here, "coupe_ceramique7_pdf.py")
    if os.path.isfile(py_script):
        python = _find_python()
        if python:
            print("Python trouve : {0}".format(python))
            return [python, py_script]
        else:
            print("AVERTISSEMENT : Python systeme introuvable.")
            print("  Installez Python 3.8+ et assurez-vous qu'il est dans le PATH.")

    # 3. Variable d'environnement
    env_val = os.environ.get("COUPE_PDF_EXE","")
    if env_val and os.path.isfile(env_val):
        return [env_val]

    return None

def _find_python():
    """Cherche un executable Python systeme (PAS Metashape).
    sys.executable dans Metashape pointe vers metashape.exe -> a ignorer.
    """
    import sys as _sys

    # Candidats explicites Windows
    win_candidates = [
        r"C:\Python313\python.exe",
        r"C:\Python312\python.exe",
        r"C:\Python311\python.exe",
        r"C:\Python310\python.exe",
        r"C:\Python39\python.exe",
        r"C:\Python38\python.exe",
    ]
    # Anaconda / Miniconda
    for root in [r"C:\ProgramData\anaconda3", r"C:\ProgramData\miniconda3",
                 os.path.join(os.environ.get("USERPROFILE",""), "anaconda3"),
                 os.path.join(os.environ.get("USERPROFILE",""), "miniconda3"),
                 os.path.join(os.environ.get("LOCALAPPDATA",""), "anaconda3"),
                 os.path.join(os.environ.get("LOCALAPPDATA",""), "miniconda3")]:
        p = os.path.join(root, "python.exe")
        if p not in win_candidates:
            win_candidates.append(p)
    # Ajouter AppData\Local\Programs\Python
    appdata = os.environ.get("LOCALAPPDATA", "")
    if appdata:
        for sub in ["Python313", "Python312", "Python311", "Python310", "Python39", "Python38"]:
            win_candidates.append(os.path.join(appdata, "Programs", "Python", sub, "python.exe"))

    for p in win_candidates:
        if os.path.isfile(p):
            return p

    # PATH systeme (en excluant les chemins Metashape)
    metashape_markers = ["metashape", "agisoft"]
    for name in ["python3", "python", "python3.exe", "python.exe"]:
        for d in os.environ.get("PATH", "").split(os.pathsep):
            # Ignorer les dossiers Metashape
            d_low = d.lower()
            if any(m in d_low for m in metashape_markers):
                continue
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p

    return None

def launch_pdf_exe(meta_path):
    import subprocess

    cmd = find_pdf_script()
    if not cmd:
        Metashape.app.messageBox(
            "Fichiers SVG/TIFF/meta generes.\n\n"
            "EXE PDF INTROUVABLE : coupe_ceramique7_pdf.exe\n"
            "Placez l'exe dans le meme dossier que ce script.\n"
            "(compiler avec build_exe.py depuis Anaconda)\n\n"
            "Commande manuelle :\n"
            "  coupe_ceramique7_pdf.exe \"{0}\"".format(meta_path))
        return
    exe = cmd[0]  # pour compatibilite avec le reste du code

    # Chemin du log produit par l'exe (meme base que meta_path)
    base_log = meta_path
    for ext in ('.meta.txt', '.meta', '.txt'):
        if base_log.lower().endswith(ext):
            base_log = base_log[:-len(ext)]
            break
    log_path = base_log + '_pdf_log.txt'

    print("Lancement : {0}".format(" ".join(cmd)))
    print("meta           : {0}".format(meta_path))
    print("log attendu    : {0}".format(log_path))

    try:
        # CREATE_NO_WINDOW sur Windows pour ne pas ouvrir une console noire
        kw = {}
        if os.name == 'nt':
            kw['creationflags'] = 0x08000000  # CREATE_NO_WINDOW

        proc = subprocess.Popen(
            cmd + [meta_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kw
        )

        # Attendre la fin (timeout 120s)
        try:
            stdout, stderr = proc.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            Metashape.app.messageBox(
                "TIMEOUT : l'exe a depasse 120 secondes.\n"
                "Log : {0}".format(log_path))
            return

        code = proc.returncode

        # Lire le log si present
        log_content = ""
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                    log_content = f.read()
            except Exception:
                pass

        pdf_path = base_log + '.pdf'
        pdf_ok   = os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0

        if pdf_ok:
            Metashape.app.messageBox(
                "PDF genere avec succes !\n\n"
                "Fichier : {0}\n"
                "Log     : {1}".format(pdf_path, log_path))
        else:
            # Afficher les 30 dernieres lignes du log pour diagnostic
            lines = log_content.strip().splitlines() if log_content else []
            tail  = "\n".join(lines[-30:]) if lines else "(log vide ou absent)"

            # Aussi decoder stdout/stderr de l'exe
            out_txt = ""
            for raw in (stdout, stderr):
                if raw:
                    try:
                        out_txt += raw.decode('utf-8', errors='replace')
                    except Exception:
                        pass

            msg = (
                "ECHEC de la generation du PDF (code {0}).\n\n"
                "--- Log ({1}) ---\n{2}".format(code, log_path, tail)
            )
            if out_txt.strip():
                msg += "\n\n--- Sortie exe ---\n" + out_txt[-800:]

            Metashape.app.messageBox(msg[:3000])   # Metashape limite la taille

    except Exception as e:
        Metashape.app.messageBox(
            "Erreur lors du lancement de l'exe :\n{0}\n\n"
            "Essayez manuellement :\n"
            "  python coupe_ceramique7_pdf.py \"{1}\"".format(e, meta_path))

# ---------------------------------------------------------------------------
# Detection echelle
# ---------------------------------------------------------------------------
def detect_scale(chunk):
    if chunk.transform and chunk.transform.scale:
        return chunk.transform.scale
    if chunk.scalebars:
        for sb in chunk.scalebars:
            if sb.reference and sb.reference.distance:
                p0,p1=sb.point0.position,sb.point1.position
                if p0 and p1:
                    d=math.sqrt((p1.x-p0.x)**2+(p1.y-p0.y)**2+(p1.z-p0.z)**2)
                    if d>0: return sb.reference.distance/d
    return 1.0

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def get_model(chunk):
    """Retourne le modele 3D actif, compatible Metashape 1.x et 2.x."""
    # Metashape 2.x : chunk.models est une liste, chunk.model pointe sur le premier
    # Metashape 1.x : chunk.model directement
    # Les deux versions supportent chunk.model -> pas de difference a gerer
    return chunk.model

def main():
    chunk = Metashape.app.document.chunk
    if not chunk or not get_model(chunk):
        Metashape.app.messageBox("Aucun modele 3D!"); return

    scale_factor = detect_scale(chunk)
    print("Facteur d'echelle: {0}".format(scale_factor))

    if scale_factor == 1.0:
        Metashape.app.messageBox(
            "ATTENTION: aucune echelle detectee.\n"
            "Le script suppose des coordonnees en metres.")

    Metashape.app.messageBox(
        "Ce script genere :\n"
        "  - SVG coupe (logique v5 identique)\n"
        "  - TIFF orthomosaique\n"
        "  - PDF A4 en 4 quadrants\n\n"
        "OK pour continuer...")

    point1, point2 = get_user_points(chunk)
    if not point1 or not point2: return

    plane_info = create_cutting_plane(point1, point2)
    plane_info['scale_factor'] = scale_factor

    print("Extraction des points de la coupe...")
    section_points = extract_section_points(chunk, plane_info)
    if not section_points:
        Metashape.app.messageBox("Aucune intersection trouvee!"); return

    points_2d = project_to_2d(section_points, plane_info)
    print("Points bruts: {0}".format(len(points_2d)))

    sec = prepare_section_v5(points_2d, plane_info, scale_factor)
    print("Coupe: {0:.2f}cm x {1:.2f}cm".format(
        sec['real_w_m']*100, sec['real_h_m']*100))

    output_path = Metashape.app.getSaveFileName(
        "Nom de base des fichiers de sortie", filter="SVG (*.svg)")
    if not output_path: return

    base      = output_path.replace('.svg','').replace('.SVG','')
    svg_path  = base+'.svg'
    tiff_path = base+'_ortho.tif'
    meta_path = base+'.meta.txt'

    write_svg(sec, svg_path)
    has_tiff, ortho_res = export_ortho_tiff(chunk, tiff_path)

    # Calculer la fraction (0..1) de position des marqueurs dans l'ortho.
    # chunk.transform.matrix.mulp() convertit chunk local -> ortho space.
    # ortho.left/right/top/bottom sont dans ce meme ortho space.
    m1_frac = m2_frac = None
    if has_tiff and chunk.orthomosaic:
        ortho = chunk.orthomosaic
        try:
            o_left   = ortho.left
            o_right  = ortho.right
            o_top    = ortho.top
            o_bottom = ortho.bottom
            T = chunk.transform.matrix
            def marker_to_frac(pos):
                p = T.mulp(pos)
                fx = (p.x - o_left)   / (o_right  - o_left)
                fy = (o_top  - p.y)   / (o_top    - o_bottom)
                return (fx, fy)
            m1_frac = marker_to_frac(point1)
            m2_frac = marker_to_frac(point2)
            print("Marqueur1 frac: fx={0:.4f} fy={1:.4f}".format(*m1_frac))
            print("Marqueur2 frac: fx={0:.4f} fy={1:.4f}".format(*m2_frac))
        except Exception as _e:
            print("AVERTISSEMENT marqueurs frac : {0}".format(_e))

    write_meta(meta_path, sec, sec['real_w_m'], sec['real_h_m'],
               tiff_path if has_tiff else None, ortho_res, svg_path,
               marker1_2d=m1_frac, marker2_2d=m2_frac)
    launch_pdf_exe(meta_path)

if __name__=="__main__":
    main()

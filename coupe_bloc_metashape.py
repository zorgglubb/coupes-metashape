"""
coupe_bloc_metashape.py  v1.0
=============================================================
Script Metashape 1.5.x et 2.x — AUCUNE dependance externe.

Coupe d'un bloc d'architecture modelise en 3D.

Logique :
  - Selection de 2 marqueurs definissant l'axe de coupe
  - Plan de coupe perpendiculaire a l'axe vertical (Z monde)
  - Extraction du profil 2D (intersection mesh / plan)
  - Export 6 orthomosaiques orthographiques si absentes :
      COUPE (vue perp. au plan), FACE, DOS, GAUCHE, DROITE, DESSUS, DESSOUS
  - Generation du fichier .meta.txt lu par coupe_bloc_pdf.exe

Produit (meme dossier que le fichier de sortie choisi) :
  <base>.svg                  Profil de coupe (vecteur, fond noir)
  <base>_vue_coupe.tif        Ortho vue coupe (perpendiculaire au plan)
  <base>_vue_face.tif         Ortho vue de face
  <base>_vue_dos.tif          Ortho vue de dos
  <base>_vue_gauche.tif       Ortho vue gauche
  <base>_vue_droite.tif       Ortho vue droite
  <base>_vue_dessus.tif       Ortho vue de dessus
  <base>_vue_dessous.tif      Ortho vue de dessous
  <base>.meta.txt             Fichier de liaison pour coupe_bloc_pdf.exe
  <base>.pdf                  Planche PDF (genere par coupe_bloc_pdf.exe)
"""

import Metashape
import math
import os
import sys

# ---------------------------------------------------------------------------
# Detection version Metashape
# ---------------------------------------------------------------------------
def _metashape_major():
    try:
        v = Metashape.app.version
        return int(str(v).split(".")[0])
    except Exception:
        return 1

MS_MAJOR = _metashape_major()
print("Metashape version : {0}  (API majeure : {1})".format(
    Metashape.app.version, MS_MAJOR))

# ---------------------------------------------------------------------------
# Constantes et utilitaires
# ---------------------------------------------------------------------------
NORMALIZED_SCALES = [1, 2, 3, 4, 5, 10, 20, 50, 100, 200, 500, 1000]

def choose_scale(real_dim_m, max_paper_cm):
    for d in NORMALIZED_SCALES:
        r = 1.0 / d
        if real_dim_m * r * 100.0 <= max_paper_cm:
            return r, d
    r = max_paper_cm / (real_dim_m * 100.0)
    return r, int(round(1.0 / r))

def vec3(x, y, z):
    return Metashape.Vector([x, y, z])

def vec_cross(a, b):
    return vec3(a.y*b.z - a.z*b.y,
                a.z*b.x - a.x*b.z,
                a.x*b.y - a.y*b.x)

def vec_dot(a, b):
    return a.x*b.x + a.y*b.y + a.z*b.z

def vec_norm(v):
    n = math.sqrt(v.x**2 + v.y**2 + v.z**2)
    return vec3(v.x/n, v.y/n, v.z/n) if n > 1e-12 else v

def vec_len(v):
    return math.sqrt(v.x**2 + v.y**2 + v.z**2)

def vec_sub(a, b):
    return vec3(a.x-b.x, a.y-b.y, a.z-b.z)

def vec_add(a, b):
    return vec3(a.x+b.x, a.y+b.y, a.z+b.z)

def vec_scale(v, s):
    return vec3(v.x*s, v.y*s, v.z*s)

# ---------------------------------------------------------------------------
# Dialogue de selection : marqueurs + mode rendu
# ---------------------------------------------------------------------------
def get_two_markers(chunk):
    """
    Ouvre une boite de dialogue PySide avec :
      - Liste des marqueurs + saisie des 2 indices
      - 2 boutons radio :
          (1) Orthomosaique  — rendu photo direct (mode par defaut)
          (2) Dessin archeo  — traitement CLAHE/contour/motifs comme coupe_ceramique7

    Retourne (pos1, pos2, label1, label2, mode)
      mode = 'ortho' ou 'dessin'
    ou (None, None, None, None, None) en cas d'annulation.
    """
    markers = [m for m in (chunk.markers or []) if m.position is not None]
    if len(markers) < 2:
        Metashape.app.messageBox(
            "Placez au moins 2 marqueurs avec une position 3D valide dans le chunk.")
        return None, None, None, None, None

    # --- Dialogue PySide ---
    try:
        from PySide2 import QtWidgets, QtCore, QtGui
    except ImportError:
        try:
            from PySide6 import QtWidgets, QtCore, QtGui
        except ImportError:
            QtWidgets = None

    if QtWidgets is None:
        # Fallback : utilisation de getString (sans cases a cocher)
        names = "\n".join("{0}: {1}".format(i, m.label) for i, m in enumerate(markers))
        result = Metashape.app.getString(
            "Marqueurs disponibles :\n{0}\n\n"
            "Entrez les 2 indices (ex: 0,1) :".format(names))
        if not result:
            return None, None, None, None, None
        try:
            idx = [int(x.strip()) for x in result.split(',')]
            if len(idx) != 2: raise ValueError()
        except (ValueError, IndexError):
            Metashape.app.messageBox("Indices invalides.")
            return None, None, None, None, None
        T = chunk.transform.matrix
        p1 = T.mulp(markers[idx[0]].position)
        p2 = T.mulp(markers[idx[1]].position)
        return p1, p2, markers[idx[0]].label, markers[idx[1]].label, 'ortho', False

    def _read_viewport_look():
        """Retourne (lx, ly, lz) normalise = direction de regard du viewport Metashape."""
        try:
            vp = Metashape.app.viewpoint
            r  = vp.rot
            try: zx = r[0][2]; zy = r[1][2]; zz = r[2][2]
            except (TypeError, IndexError):
                try: zx = r[2]; zy = r[5]; zz = r[8]
                except Exception: return None
            lx, ly, lz = -zx, -zy, -zz
            n = math.sqrt(lx*lx + ly*ly + lz*lz)
            if n < 1e-9: return None
            return (lx/n, ly/n, lz/n)
        except Exception: return None

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    dlg = QtWidgets.QDialog()
    dlg.setWindowTitle("Coupe Bloc — Paramètres")
    dlg.setMinimumWidth(460)
    dlg.setWindowFlags(dlg.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)

    dlg.setStyleSheet("""
        QDialog        { background: #2b2b2b; }
        QLabel         { color: #e0e0e0; font-size: 11px; }
        QLabel#titre   { color: #ffffff; font-size: 13px; font-weight: bold;
                         padding: 8px 0 4px 0; }
        QLabel#section { color: #aac8f0; font-size: 10px; font-weight: bold;
                         padding: 6px 0 2px 0; }
        QLineEdit      { background: #3c3c3c; color: #e8e8e8; border: 1px solid #555;
                         border-radius: 4px; padding: 5px 8px; font-size: 11px; }
        QListWidget    { background: #333333; color: #d8d8d8; border: 1px solid #555;
                         border-radius: 4px; font-size: 10px; }
        QListWidget::item:selected { background: #4a7fc1; color: white; }
        QRadioButton   { color: #e0e0e0; font-size: 11px; padding: 5px 8px; }
        QRadioButton::indicator       { width:16px; height:16px; }
        QRadioButton::indicator:checked   { background:#4a7fc1; border:2px solid #7ab0f0; border-radius:8px; }
        QRadioButton::indicator:unchecked { background:#444;    border:2px solid #666;    border-radius:8px; }
        QPushButton#ok  { background:#4a7fc1; color:white; border:none; border-radius:5px;
                          font-size:11px; font-weight:bold; padding:8px 24px; }
        QPushButton#ok:hover   { background:#5a8fd1; }
        QPushButton#ok:pressed { background:#3a6fb1; }
        QPushButton#ann { background:#555; color:#ccc; border:none; border-radius:5px;
                          font-size:11px; padding:8px 18px; }
        QPushButton#ann:hover { background:#666; }
        QFrame#sep { color:#444444; }
    """)

    lay = QtWidgets.QVBoxLayout(dlg)
    lay.setContentsMargins(22, 16, 22, 16)
    lay.setSpacing(4)

    lbl_titre = QtWidgets.QLabel("Coupe Bloc — Paramètres")
    lbl_titre.setObjectName("titre")
    lbl_titre.setAlignment(QtCore.Qt.AlignCenter)
    lay.addWidget(lbl_titre)

    def sep_line():
        f = QtWidgets.QFrame(); f.setObjectName("sep")
        f.setFrameShape(QtWidgets.QFrame.HLine)
        f.setStyleSheet("QFrame { color:#444; margin:4px 0; }")
        return f
    lay.addWidget(sep_line())

    # ── Marqueurs ────────────────────────────────────────────────────────────
    lbl_m = QtWidgets.QLabel("Marqueurs disponibles :")
    lbl_m.setObjectName("section")
    lay.addWidget(lbl_m)
    lst = QtWidgets.QListWidget()
    lst.setFixedHeight(90)
    for i, m in enumerate(markers):
        lst.addItem("{0}: {1}".format(i, m.label))
    lay.addWidget(lst)
    lbl_idx = QtWidgets.QLabel("Indices des 2 marqueurs de l’axe de coupe (ex : 0,1) :")
    lay.addWidget(lbl_idx)
    edit_idx = QtWidgets.QLineEdit()
    edit_idx.setPlaceholderText("0,1")
    if len(markers) == 2:
        edit_idx.setText("0,1")
    lay.addWidget(edit_idx)
    lay.addWidget(sep_line())

    # ── Vue actuelle dans Metashape ─────────────────────────────────────────────
    lbl_vue = QtWidgets.QLabel("Quelle vue est affichée dans Metashape en ce moment ?")
    lbl_vue.setObjectName("section")
    lay.addWidget(lbl_vue)

    lbl_vue_exp = QtWidgets.QLabel(
        "Orientez le modele 3D sur la vue souhaitee dans Metashape,\n"
        "puis cochez la case correspondante et cliquez OK.\n"
        "La direction de la camera est lue au moment du clic OK : "
        "les 6 autres vues sont deduites automatiquement.")
    lbl_vue_exp.setWordWrap(True)
    lbl_vue_exp.setStyleSheet("color:#b0b8c8; font-size:9px; padding:0 0 6px 4px;")
    lay.addWidget(lbl_vue_exp)

    grp_vue = QtWidgets.QButtonGroup(dlg)
    rb_face   = QtWidgets.QRadioButton(
        "  Vue de face  —  je vois la face principale du bloc")
    rb_dessus = QtWidgets.QRadioButton(
        "  Vue de dessus  —  je regarde le bloc par le dessus (ou légèrement de biais)")
    grp_vue.addButton(rb_face,   1)
    grp_vue.addButton(rb_dessus, 2)
    lay.addWidget(rb_face)
    lay.addWidget(rb_dessus)
    lay.addWidget(sep_line())

    # ── Mode de rendu ─────────────────────────────────────────────────────────────
    lbl_mode = QtWidgets.QLabel("Mode de rendu des orthomosaïques :")
    lbl_mode.setObjectName("section")
    lay.addWidget(lbl_mode)
    grp_mode = QtWidgets.QButtonGroup(dlg)
    rb_ortho  = QtWidgets.QRadioButton(
        "  Orthomosaïque — rendu photo direct (couleur / niveaux de gris)")
    rb_dessin = QtWidgets.QRadioButton(
        "  Dessin archéologique — traitement CLAHE, contours, motifs de gris")
    grp_mode.addButton(rb_ortho,  1)
    grp_mode.addButton(rb_dessin, 2)
    rb_ortho.setChecked(True)
    lay.addWidget(rb_ortho)
    lay.addWidget(rb_dessin)
    lay.addSpacing(4)
    lay.addWidget(sep_line())
    lay.addSpacing(2)

    # ── Boutons ────────────────────────────────────────────────────────────────────
    row_btn = QtWidgets.QHBoxLayout()
    row_btn.addStretch()
    btn_ann = QtWidgets.QPushButton("Annuler"); btn_ann.setObjectName("ann")
    btn_ok  = QtWidgets.QPushButton("OK");      btn_ok.setObjectName("ok")
    btn_ok.setDefault(True)
    row_btn.addWidget(btn_ann)
    row_btn.addSpacing(8)
    row_btn.addWidget(btn_ok)
    lay.addLayout(row_btn)

    result_holder = [None]

    def on_ok():
        txt = edit_idx.text().strip()
        try:
            parts = [int(x.strip()) for x in txt.split(',')]
            if len(parts) != 2: raise ValueError("2 indices requis")
            if not all(0 <= p < len(markers) for p in parts):
                raise ValueError("indice hors limites")
            if not rb_face.isChecked() and not rb_dessus.isChecked():
                QtWidgets.QMessageBox.warning(dlg, "Vue non choisie",
                    "Cochez la vue actuellement affichée dans Metashape\n"
                    "(Vue de face ou Vue de dessus) avant de cliquer OK.")
                return
            # Lire le viewport AU moment exact du clic OK
            look_now = _read_viewport_look()
            mode     = 'dessin' if rb_dessin.isChecked() else 'ortho'
            vue_ref  = 'face' if rb_face.isChecked() else 'dessus'
            result_holder[0] = (parts[0], parts[1], mode, vue_ref, look_now)
            dlg.accept()
        except (ValueError, Exception) as e:
            QtWidgets.QMessageBox.warning(dlg, "Erreur",
                "Paramètres invalides : {0}".format(e))

    btn_ok.clicked.connect(on_ok)
    btn_ann.clicked.connect(dlg.reject)
    lst.itemDoubleClicked.connect(lambda item: None)

    dlg.exec_()

    if result_holder[0] is None:
        return None, None, None, None, None, None

    i1, i2, mode, vue_ref, look_captured = result_holder[0]
    m1 = markers[i1]; m2 = markers[i2]
    T  = chunk.transform.matrix
    p1 = T.mulp(m1.position)
    p2 = T.mulp(m2.position)
    print("Marqueur 1 : {0}  -> ({1:.4f},{2:.4f},{3:.4f})".format(
        m1.label, p1.x, p1.y, p1.z))
    print("Marqueur 2 : {0}  -> ({1:.4f},{2:.4f},{3:.4f})".format(
        m2.label, p2.x, p2.y, p2.z))
    print("Vue ref : {0}  |  look : {1}  |  mode : {2}".format(
        vue_ref, look_captured, mode))
    return p1, p2, m1.label, m2.label, mode, (vue_ref, look_captured)

# ---------------------------------------------------------------------------
# Plan de coupe
# ---------------------------------------------------------------------------
def build_cut_plane(p1, p2, vue_orient=None):
    """
    Construit le plan de coupe perpendiculaire a Z monde.

    vue_orient = (vue_ref, look_captured) depuis le dialogue :
      - vue_ref      : 'face' | 'dessus' | 'aucune'
      - look_captured: (lx, ly, lz) direction de regard du viewport au moment du clic OK
                       ou None si non disponible

    Logique d'orientation :
      Si vue_ref == 'face' et look_captured disponible :
        L'utilisateur regardait la face du bloc.
        La normale = -look_captured projete horizontalement
        (la face est perpendiculaire a la direction de regard, la normale pointe vers lui)
        L'axe = cross(Z, normal) puis oriente pour que p1->p2 soit dans le meme sens.

      Si vue_ref == 'dessus' et look_captured disponible :
        L'utilisateur regardait le dessus.
        Le regard est approximativement -Z.
        La face = cote vers lequel pointe la normale = a determiner depuis l'axe p1->p2.
        On utilise la projection horizontale du look pour determiner l'avant du bloc :
        normal = -look_horizontal (direction depuis laquelle on regardait le dessus = avant).

      Si vue_ref == 'aucune' ou look_captured None :
        Convention geometrique pure : normal = cross(axis, Z).

    Retourne un dict avec tous les vecteurs utiles.
    """
    import math as _m

    center = vec_scale(vec_add(p1, p2), 0.5)
    up = vec3(0.0, 0.0, 1.0)

    # Axe de coupe brut = direction p1->p2 projetee horizontalement
    axis_raw = vec_sub(p2, p1)
    axis_h_raw = vec_norm(vec3(axis_raw.x, axis_raw.y, 0.0))

    def _cross_v3(a, b):
        return vec3(a.y*b.z - a.z*b.y,
                    a.z*b.x - a.x*b.z,
                    a.x*b.y - a.y*b.x)
    def _dot_v3(a, b):
        return a.x*b.x + a.y*b.y + a.z*b.z

    # Normale par defaut : cross(axis, up)
    normal_default = vec_norm(_cross_v3(axis_h_raw, up))
    axis_h = axis_h_raw
    normal  = normal_default

    if vue_orient is not None:
        vue_ref, look_captured = vue_orient
    else:
        vue_ref, look_captured = 'aucune', None

    if look_captured is not None and vue_ref in ('face', 'dessus'):
        lx, ly, lz = look_captured

        if vue_ref == 'face':
            # L'utilisateur regardait la face.
            # Direction de regard = de la camera vers le bloc = vers la normale du bloc.
            # Donc normal = look projete horizontalement (direction vers laquelle on regardait).
            # La normale pointe vers l'observateur = -look.
            # Mais l'observateur est devant la face et regarde vers le bloc :
            #   look pointe vers le bloc = vers la face = vers la normale entrante.
            #   normal (sortante, vers l'observateur) = -look_h.
            lh_n = _m.sqrt(lx*lx + ly*ly)
            if lh_n > 0.15:   # composante horizontale suffisante
                # look_h = composante horizontale du regard = vers le bloc depuis l'obs
                # normal sortante = -look_h
                nx = -lx / lh_n;  ny = -ly / lh_n
                candidate_normal = vec3(nx, ny, 0.0)
                # Orienter axis_h perpendiculairement a cette normale, dans le meme
                # sens que p1->p2 (produit scalaire positif)
                candidate_axis = vec_norm(_cross_v3(up, candidate_normal))  # cross(Z, normal)
                if _dot_v3(candidate_axis, axis_h_raw) < 0:
                    candidate_axis = vec3(-candidate_axis.x, -candidate_axis.y, 0.0)
                normal = candidate_normal
                axis_h = candidate_axis
                print("  vue_ref=face : normal deduite du regard => ({0:.3f},{1:.3f},0)".format(
                    normal.x, normal.y))
            else:
                print("  vue_ref=face : regard trop vertical, convention par defaut")

        elif vue_ref == 'dessus':
            # L'utilisateur regardait le dessus (regard vers le bas environ).
            # La composante horizontale du regard indique depuis quel cote il regardait :
            # si lh non nul, -lh = direction de l'avant du bloc (face) depuis dessus.
            lh_n = _m.sqrt(lx*lx + ly*ly)
            if lh_n > 0.10:
                # La normale = -look_horizontal (meme logique que face)
                nx = -lx / lh_n;  ny = -ly / lh_n
                candidate_normal = vec3(nx, ny, 0.0)
                candidate_axis = vec_norm(_cross_v3(up, candidate_normal))
                if _dot_v3(candidate_axis, axis_h_raw) < 0:
                    candidate_axis = vec3(-candidate_axis.x, -candidate_axis.y, 0.0)
                normal = candidate_normal
                axis_h = candidate_axis
                print("  vue_ref=dessus : normal deduite du regard => ({0:.3f},{1:.3f},0)".format(
                    normal.x, normal.y))
            else:
                # Regard purement vertical : pas d'info horizontale, convention par defaut
                print("  vue_ref=dessus : regard purement vertical, convention par defaut")

    print("  axis   = ({0:.4f}, {1:.4f}, 0)".format(axis_h.x, axis_h.y))
    print("  normal = ({0:.4f}, {1:.4f}, 0)".format(normal.x, normal.y))

    binormal = up
    axis_len = vec_len(vec_sub(p2, p1))

    return {
        'center':   center,
        'normal':   normal,
        'axis':     axis_h,
        'binormal': binormal,
        'up':       up,
        'p1':       p1,
        'p2':       p2,
        'axis_len': axis_len,
    }


# ---------------------------------------------------------------------------
# Extraction section 3D -> points 2D
# ---------------------------------------------------------------------------
def _get_model(chunk):
    """Retourne le mesh actif du chunk (API 1.x et 2.x)."""
    try:
        # Metashape 2.x
        models = [m for m in chunk.models if m is not None]
        if models:
            return models[0]
    except AttributeError:
        pass
    try:
        return chunk.model
    except AttributeError:
        return None

def extract_section_2d(chunk, plane):
    """
    Intersecte toutes les faces du mesh avec le plan de coupe.
    Retourne une liste de points 2D (u, v) en metres dans le repere du plan.
    """
    model = _get_model(chunk)
    if not model or not model.faces:
        print("ERREUR : pas de mesh disponible.")
        return []

    T = chunk.transform.matrix         # chunk local -> monde
    center  = plane['center']
    normal  = plane['normal']
    axis    = plane['axis']
    binormal= plane['binormal']
    scale   = chunk.transform.scale or 1.0

    vertices_w = []
    for v in model.vertices:
        pw = T.mulp(v.coord)
        vertices_w.append(pw)

    pts_2d = []
    for face in model.faces:
        vi = face.vertices
        v0 = vertices_w[vi[0]]
        v1 = vertices_w[vi[1]]
        v2 = vertices_w[vi[2]]
        tri = [v0, v1, v2]

        for i in range(3):
            a = tri[i]
            b = tri[(i+1) % 3]
            va = vec_sub(a, center)
            vb = vec_sub(b, center)
            da = vec_dot(normal, va)
            db = vec_dot(normal, vb)
            if da * db < 0:
                t = da / (da - db)
                ix = a.x + t * (b.x - a.x)
                iy = a.y + t * (b.y - a.y)
                iz = a.z + t * (b.z - a.z)
                p  = vec3(ix, iy, iz)
                vp = vec_sub(p, center)
                u  = vec_dot(vp, axis)
                vv = vec_dot(vp, binormal)
                pts_2d.append((u, vv))

    print("Points de section bruts : {0}".format(len(pts_2d)))
    return pts_2d

# ---------------------------------------------------------------------------
# Simplification contour
# ---------------------------------------------------------------------------
def sort_along_path(pts):
    if len(pts) < 2: return pts
    result = [pts[0]]
    rem    = list(pts[1:])
    while rem:
        last = result[-1]
        best_i = min(range(len(rem)),
                     key=lambda i: (rem[i][0]-last[0])**2 + (rem[i][1]-last[1])**2)
        result.append(rem.pop(best_i))
    return result

def douglas_peucker(pts, tol):
    if len(pts) < 3: return pts
    p0 = pts[0]; pn = pts[-1]
    dx = pn[0]-p0[0]; dy = pn[1]-p0[1]
    ln = math.sqrt(dx*dx+dy*dy)
    max_d = 0; max_i = 0
    for i in range(1, len(pts)-1):
        if ln < 1e-12:
            d = math.sqrt((pts[i][0]-p0[0])**2 + (pts[i][1]-p0[1])**2)
        else:
            d = abs(dx*(p0[1]-pts[i][1]) - (p0[0]-pts[i][0])*dy) / ln
        if d > max_d:
            max_d = d; max_i = i
    if max_d > tol:
        L = douglas_peucker(pts[:max_i+1], tol)
        R = douglas_peucker(pts[max_i:],   tol)
        return L[:-1] + R
    return [p0, pn]

def simplify(pts, tol):
    if len(pts) < 3: return pts
    return douglas_peucker(sort_along_path(pts), tol)

# ---------------------------------------------------------------------------
# Preparation de la section (similaire coupe_ceramique7)
# ---------------------------------------------------------------------------
def prepare_section(pts_2d, plane):
    """
    Prepare le profil pour l'export SVG.
    Coordonnees en metres reels.
    """
    if not pts_2d:
        return None

    xs = [p[0] for p in pts_2d]
    ys = [p[1] for p in pts_2d]
    max_dim = max(max(xs)-min(xs), max(ys)-min(ys))
    tol = max_dim * 0.0001
    pts = simplify(pts_2d, tol)
    if not pts:
        return None

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Etendre jusqu'aux marqueurs si besoin
    half = plane['axis_len'] / 2.0
    if min_x > -half:
        close = [p for p in pts if p[0] < min_x + 0.001]
        if close:
            avg_y = sum(p[1] for p in close) / len(close)
            pts.append((-half, avg_y))
    if max_x < half:
        close = [p for p in pts if p[0] > max_x - 0.001]
        if close:
            avg_y = sum(p[1] for p in close) / len(close)
            pts.append((half, avg_y))

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]

    return {
        'points': pts,
        'min_x': min(xs), 'max_x': max(xs),
        'min_y': min(ys), 'max_y': max(ys),
        'real_w_m': max(xs) - min(xs),
        'real_h_m': max(ys) - min(ys),
    }

# ---------------------------------------------------------------------------
# Calcul de la boite englobante du mesh (monde)
# ---------------------------------------------------------------------------
def mesh_bbox_world(chunk):
    """Retourne (min_x, max_x, min_y, max_y, min_z, max_z) du mesh en coord monde."""
    model = _get_model(chunk)
    if not model or not model.vertices:
        return None
    T = chunk.transform.matrix
    xs, ys, zs = [], [], []
    for v in model.vertices:
        w = T.mulp(v.coord)
        xs.append(w.x); ys.append(w.y); zs.append(w.z)
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)

# ---------------------------------------------------------------------------
# Export SVG hachures noires sur fond blanc (style archeo bloc)
# ---------------------------------------------------------------------------
def write_svg(sec, output_path):
    """
    SVG fond blanc, contour noir, remplissage hachures noires 45deg.
    1 unite SVG = 1 metre.
    Hachure : espacement ~1% de la largeur reelle, epaisseur ~0.3% de la largeur.
    """
    pts    = sec['points']
    min_x  = sec['min_x'];  min_y = sec['min_y']
    max_x  = sec['max_x'];  max_y = sec['max_y']
    real_w = sec['real_w_m']; real_h = sec['real_h_m']
    real_w_cm = real_w * 100.0
    real_h_cm = real_h * 100.0

    # Epaisseurs en metres
    sw_contour = max(0.0005, real_w * 0.0015)   # contour exterieur
    sw_hachure = max(0.0002, real_w * 0.0006)   # trait de hachure
    hatch_gap  = max(0.001,  real_w * 0.012)    # espacement entre hachures

    flip = max_y + min_y   # flip Y pour SVG

    # Generer les lignes de hachures couvrant la bbox
    # Hachures a 45 deg (direction Sud-Ouest -> Nord-Est)
    # On trace des diagonales de la bbox etendue
    diag_len = (real_w + real_h) * 1.5
    hatch_lines = []
    # Parametre t : deplace perpendiclairement aux hachures (direction NW)
    t = -(diag_len)
    while t <= diag_len:
        # Droite : direction (1,1)/sqrt(2), point de depart sur l'axe perpendiculaire
        # Origine = centre de la bbox
        cx_h = (min_x + max_x) / 2.0
        cy_h = (min_y + max_y) / 2.0
        # Vecteur perpendiculaire : (-1,1)/sqrt(2)
        ox = cx_h + t * (-0.7071)
        oy = cy_h + t *  0.7071
        # Extremites de la ligne le long de la direction (1,1)
        x1_h = ox - diag_len * 0.7071
        y1_h = oy - diag_len * 0.7071
        x2_h = ox + diag_len * 0.7071
        y2_h = oy + diag_len * 0.7071
        hatch_lines.append((x1_h, y1_h, x2_h, y2_h))
        t += hatch_gap

    # ID unique pour le clipPath
    clip_id = "clip_coupe_bloc"
    hatch_id = "hatch_coupe"

    lines_svg = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="{0:.4f}cm" height="{1:.4f}cm" '
        'viewBox="{2:.8f} {3:.8f} {4:.8f} {5:.8f}">'.format(
            real_w_cm, real_h_cm, min_x, min_y, real_w, real_h),
        '<!-- BLOC_META real_w_m={0:.8f} real_h_m={1:.8f} -->'.format(real_w, real_h),
        '<defs>',
    ]

    # ClipPath = contour de la coupe
    if len(pts) > 1:
        d_clip = 'M {0:.6f},{1:.6f}'.format(pts[0][0], pts[0][1])
        for x, y in pts[1:]:
            d_clip += ' L {0:.6f},{1:.6f}'.format(x, y)
        d_clip += ' Z'
        lines_svg.append('<clipPath id="{0}">'.format(clip_id))
        lines_svg.append(
            '<path d="{0}" transform="matrix(1,0,0,-1,0,{1:.8f})"/>'.format(
                d_clip, flip))
        lines_svg.append('</clipPath>')

    lines_svg.append('</defs>')

    # Fond blanc
    lines_svg.append(
        '<rect x="{0:.8f}" y="{1:.8f}" width="{2:.8f}" height="{3:.8f}" '
        'fill="white"/>'.format(min_x, min_y, real_w, real_h))

    # Hachures clipees sur le contour
    if hatch_lines and len(pts) > 1:
        lines_svg.append('<g clip-path="url(#{0})">'.format(clip_id))
        for x1h, y1h, x2h, y2h in hatch_lines:
            # Les hachures sont en coords "normales" (Y vers le haut),
            # le clipPath applique deja le flip, donc on doit aussi flipper les lignes.
            # Flip : y_svg = flip - y_monde
            y1s = flip - y1h
            y2s = flip - y2h
            lines_svg.append(
                '<line x1="{0:.6f}" y1="{1:.6f}" x2="{2:.6f}" y2="{3:.6f}" '
                'stroke="black" stroke-width="{4:.6f}"/>'.format(
                    x1h, y1s, x2h, y2s, sw_hachure))
        lines_svg.append('</g>')

    # Contour exterieur (par-dessus les hachures)
    if len(pts) > 1:
        lines_svg.append('<g transform="matrix(1,0,0,-1,0,{0:.8f})">'.format(flip))
        d_cont = 'M {0:.6f},{1:.6f}'.format(pts[0][0], pts[0][1])
        for x, y in pts[1:]:
            d_cont += ' L {0:.6f},{1:.6f}'.format(x, y)
        d_cont += ' Z'
        lines_svg.append(
            '<path d="{0}" fill="none" stroke="black" '
            'stroke-width="{1:.6f}" '
            'stroke-linejoin="round" stroke-linecap="round"/>'.format(d_cont, sw_contour))
        lines_svg.append('</g>')

    lines_svg.append('</svg>')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines_svg))
    print("SVG hachures : {0:.3f}cm x {1:.3f}cm -> {2}".format(
        real_w_cm, real_h_cm, output_path))

# ---------------------------------------------------------------------------
# Cameras orthographiques virtuelles pour les 6 vues
# ---------------------------------------------------------------------------
VUES = {
    'coupe':   {'desc': 'Coupe (plan de coupe)'},
    'face':    {'desc': 'Vue de face'},
    'dos':     {'desc': 'Vue de dos'},
    'gauche':  {'desc': 'Vue gauche'},
    'droite':  {'desc': 'Vue droite'},
    'dessus':  {'desc': 'Vue de dessus'},
    'dessous': {'desc': 'Vue de dessous'},
}

def _write_tfw(tiff_path, chunk):
    """
    Ecrit le fichier world (.tfw) associe au TIFF.
    Format TFW standard (6 lignes) :
      pixel_size_x   (m/pixel, positif)
      rotation_x     (0)
      rotation_y     (0)
      pixel_size_y   (m/pixel, negatif)
      x_centre_pixel_haut_gauche
      y_centre_pixel_haut_gauche
    Tente de lire ces valeurs depuis l'orthomosaique Metashape courante.
    """
    tfw_path = os.path.splitext(tiff_path)[0] + '.tfw'
    try:
        ortho = chunk.orthomosaic
        if ortho is None:
            print("  TFW : pas d'orthomosaique dans le chunk.")
            return False
        res  = None
        left = None
        top  = None
        # Lecture resolution
        try:    res = ortho.resolution
        except Exception: pass
        # Lecture coin haut-gauche (left / top)
        try:    left = ortho.left;  top = ortho.top
        except AttributeError: pass
        if left is None:
            try:
                left = ortho.transform[3]
                top  = ortho.transform[7]
            except Exception: pass
        if res is None or left is None:
            print("  TFW : attributs resolution/left/top introuvables -> TFW non ecrit.")
            return False
        cx = left + res / 2.0
        cy = top  - res / 2.0
        with open(tfw_path, 'w') as f:
            f.write("{0:.10f}\n".format(res))
            f.write("0.0000000000\n")
            f.write("0.0000000000\n")
            f.write("{0:.10f}\n".format(-res))
            f.write("{0:.10f}\n".format(cx))
            f.write("{0:.10f}\n".format(cy))
        print("  TFW ecrit : {0}  (res {1:.6f} m/px  left={2:.4f} top={3:.4f})".format(
            tfw_path, res, left, top))
        return True
    except Exception as e:
        print("  TFW erreur : {0}".format(e))
        return False


def _ortho_resolution(chunk, bbox, target_px=2000):
    """Calcule une resolution en m/px pour avoir ~target_px pixels sur la plus grande dimension."""
    bx, bx2, by, by2, bz, bz2 = bbox
    max_dim = max(bx2-bx, by2-by, bz2-bz)
    if max_dim < 1e-6:
        return 0.0005
    return max_dim / target_px

def _export_ortho_one(chunk, tiff_path):
    """Exporte l'orthomosaique courante du chunk. Plusieurs variantes API."""
    # Supprimer le fichier cible avant export pour eviter de confondre
    # un ancien TIFF avec un export reussi (protection contre faux positifs)
    if os.path.exists(tiff_path):
        try: os.remove(tiff_path)
        except Exception: pass
    def ok():
        return os.path.exists(tiff_path) and os.path.getsize(tiff_path) > 0

    if MS_MAJOR >= 2:
        variantes = [
            lambda: chunk.exportRaster(tiff_path,
                source_data=Metashape.DataSource.OrthomosaicData,
                image_format=Metashape.ImageFormat.ImageFormatTIFF,
                white_background=False),
            lambda: chunk.exportRaster(tiff_path,
                source_data=Metashape.DataSource.OrthomosaicData,
                image_format=Metashape.ImageFormat.ImageFormatTIFF),
            lambda: chunk.exportRaster(tiff_path,
                source_data=Metashape.DataSource.OrthomosaicData),
        ]
    else:
        variantes = [
            lambda: chunk.exportOrthomosaic(tiff_path,
                image_format=Metashape.ImageFormat.ImageFormatTIFF,
                white_background=False),
            lambda: chunk.exportOrthomosaic(tiff_path,
                Metashape.ImageFormat.ImageFormatTIFF, white_background=False),
            lambda: chunk.exportOrthomosaic(tiff_path,
                Metashape.RasterFormat.RasterFormatTIFF),
            lambda: chunk.exportOrthomosaic(tiff_path),
        ]

    for i, fn in enumerate(variantes):
        try:
            fn()
            if ok():
                print("  TIFF exporte (variante {0}) : {1}".format(i+1, tiff_path))
                _write_tfw(tiff_path, chunk)
                return True
        except Exception as e:
            print("  variante {0} : {1}".format(i+1, e))
    print("  ECHEC export TIFF : {0}".format(tiff_path))
    return False


def _build_ortho_for_view(chunk, doc, view_key, plane, bbox, tiff_path):
    """
    Cree une orthomosaique orthographique pour la vue demandee.
    Utilise une cascade de variantes d'API pour couvrir Metashape 1.5 a 2.x.
    Retourne True si succes.
    """
    bx0, bx1, by0, by1, bz0, bz1 = bbox
    cx = (bx0+bx1)/2; cy = (by0+by1)/2; cz = (bz0+bz1)/2

    normal    = plane['normal']
    axis      = plane['axis']
    up        = plane['up']
    neg_normal= vec3(-normal.x, -normal.y, -normal.z)
    neg_axis  = vec3(-axis.x,  -axis.y,  -axis.z)
    down      = vec3(0, 0, -1)

    # Convention geometrique rigoureuse (exemple : axis=+X, up=+Z, normal=cross(axis,up)=-Y)
    #
    # FACE    : bloc en +Y (cote normal=-Y pointe vers nous), on regarde depuis +Y
    #           look = -normal = neg_normal     up_dir = +Z
    #
    # DOS     : on regarde depuis -Y
    #           look = +normal                  up_dir = +Z
    #
    # GAUCHE  : observateur debout face au bloc (en +Y, look=-Y).
    #           Sa gauche physique = -X = neg_axis.
    #           Camera placee en -X, regarde vers +X = axis.
    #           look = axis                     up_dir = +Z
    #
    # DROITE  : Sa droite physique = +X = axis.
    #           Camera placee en +X, regarde vers -X = neg_axis.
    #           look = neg_axis                 up_dir = +Z
    #
    # DESSUS  : Camera au-dessus, look=down.
    #           Haut de l'image = devant du bloc = cote normal.
    #           up_dir = normal  (normal=-Y pointe vers devant)
    #
    # DESSOUS : Camera en-dessous, look=up.
    #           Haut de l'image = dos du bloc (coherence avec dessus retourne).
    #           up_dir = neg_normal
    #
    # COUPE   : Meme projection que face.
    view_dirs = {
        'face':    (neg_normal, up),
        'dos':     (normal,     up),
        'gauche':  (axis,       up),
        'droite':  (neg_axis,   up),
        'dessus':  (down,       normal),
        'dessous': (up,         neg_normal),
        'coupe':   (neg_normal, up),
    }

    if view_key not in view_dirs:
        print("Vue inconnue : {0}".format(view_key))
        return False

    look_dir, up_dir = view_dirs[view_key]
    res = _ortho_resolution(chunk, bbox, target_px=2000)

    # Construire la matrice de projection
    right_dir = vec_norm(vec_cross(look_dir, up_dir))
    true_up   = vec_norm(vec_cross(right_dir, look_dir))

    # OrthoProjection avec matrice
    def _try_with_proj(proj_obj, extra_kw):
        """Tente buildOrthomosaic avec une projection et des kwargs variables."""
        # Tous les noms d'arguments possibles selon version Metashape
        surface_variants = [
            {'surface_data': Metashape.DataSource.ModelData},
            {'surface_data': Metashape.ModelData},
            {'surface': Metashape.ModelData},
            {'surface': Metashape.DataSource.ModelData},
            {},
        ]
        blend_variants = [
            {'blending_mode': Metashape.BlendingMode.MosaicBlending},
            {'blending_mode': Metashape.MosaicBlending},
            {'blending': Metashape.BlendingMode.MosaicBlending},
            {'blending': Metashape.MosaicBlending},
            {},
        ]
        res_variants = [
            {'resolution': res},
            {'ortho_resolution': res},
            {},
        ]
        proj_variants = [
            {'projection': proj_obj} if proj_obj else {},
            {},
        ]
        fill_variants = [
            {'fill_holes': True},
            {},
        ]

        attempts = 0
        for sv in surface_variants:
            for bv in blend_variants:
                for rv in res_variants:
                    for pv in proj_variants:
                        for fv in fill_variants:
                            kw = {}
                            kw.update(sv); kw.update(bv); kw.update(rv)
                            kw.update(pv); kw.update(fv); kw.update(extra_kw)
                            try:
                                # Supprimer l'ortho precedente pour eviter export parasite
                                try:
                                    # Supprime l'ortho precedente pour eviter export parasite.
                                    # chunk.remove() existe depuis ~1.6 ; sur 1.5 on ignore l'erreur.
                                    ortho_prev = chunk.orthomosaic
                                    if ortho_prev is not None:
                                        try:
                                            chunk.remove(ortho_prev)
                                        except (AttributeError, RuntimeError, Exception):
                                            pass  # 1.5 : remove() absent ou non supporte
                                except Exception: pass
                                chunk.buildOrthomosaic(**kw)
                                doc.save()
                                if _export_ortho_one(chunk, tiff_path):
                                    print("  buildOrthomosaic OK (variante {0})".format(attempts))
                                    return True
                            except Exception as e:
                                err = str(e)
                                # Arreter si c'est une vraie erreur metier, pas un mauvais arg
                                if 'invalid keyword' not in err and 'unexpected keyword' not in err and                                    'got an unexpected' not in err and 'argument' not in err.lower():
                                    print("  variante {0} erreur metier : {1}".format(attempts, err))
                                    return False
                            attempts += 1
        return False

    # ---- Methode A : projection personnalisee (sans rotation du chunk) ----
    proj = None
    try:
        proj = Metashape.OrthoProjection()
        proj.type = Metashape.OrthoProjection.Type.Planar
        # Convention OrthoProjection : col 0 = right, col 1 = up, col 2 = back (-look)
        # Metashape inverse X lors du rendu -> inverser right_dir pour corriger le miroir
        m = Metashape.Matrix([
            [-right_dir.x, -right_dir.y, -right_dir.z,  0],
            [ true_up.x,    true_up.y,    true_up.z,    0],
            [-look_dir.x,  -look_dir.y,  -look_dir.z,   0],
            [cx,             cy,            cz,           1],
        ])
        proj.matrix = m
    except Exception as e:
        print("  OrthoProjection non disponible : {0}".format(e))
        proj = None

    if _try_with_proj(proj, {}):
        return True

    # ---- Methode B : rotation du chunk + ortho standard ----
    # Metashape buildOrthomosaic standard projette selon -Z_chunk (nadir).
    # Le TIFF resultant place X_chunk vers la droite de l'image.
    # Il faut donc que X_chunk = -right_dir (inversion pour annuler le miroir) :
    #   X_chunk = -right_dir  -> image: droite = right_dir de la vue  (correct)
    #   Y_chunk = true_up     -> image: haut = true_up               (correct)
    #   Z_chunk = look_dir    -> -Z_chunk pointe vers le modele       (correct)
    print("  Methode B : rotation chunk...")
    orig_transform = None
    try:
        orig_transform = chunk.transform.matrix

        rot = Metashape.Matrix([
            [-right_dir.x, -right_dir.y, -right_dir.z,  0],
            [ true_up.x,    true_up.y,    true_up.z,    0],
            [ look_dir.x,   look_dir.y,   look_dir.z,   0],
            [0,             0,            0,             1],
        ])
        chunk.transform.matrix = rot * orig_transform

        if _try_with_proj(None, {}):
            chunk.transform.matrix = orig_transform
            doc.save()
            return True

        # Restaurer en cas d'echec
        chunk.transform.matrix = orig_transform
        doc.save()

    except Exception as e:
        print("  Methode B erreur : {0}".format(e))
        if orig_transform is not None:
            try:
                chunk.transform.matrix = orig_transform
                doc.save()
            except Exception:
                pass

    return False


def generate_all_orthos(chunk, doc, plane, bbox, base_path):
    """
    Pour chaque vue, verifie si le TIFF existe.
    Si non, le cree. Retourne un dict {vue_key: tiff_path_ou_None}.
    """
    result = {}
    for key in VUES:
        tiff_path = "{0}_vue_{1}.tif".format(base_path, key)
        result[key] = None

        if os.path.exists(tiff_path) and os.path.getsize(tiff_path) > 0:
            print("Vue {0} : TIFF existant utilise -> {1}".format(key, tiff_path))
            result[key] = tiff_path
            continue

        print("Vue {0} : generation de l'orthomosaique...".format(key))
        ok = _build_ortho_for_view(chunk, doc, key, plane, bbox, tiff_path)
        if ok:
            result[key] = tiff_path
        else:
            print("Vue {0} : ECHEC de generation (case 'non disponible' dans le PDF)".format(key))

    return result

# ---------------------------------------------------------------------------
# Calcul dimensions reelles de chaque vue (pour la mire)
# ---------------------------------------------------------------------------
def view_real_dims(bbox, plane):
    """
    Retourne les dimensions reelles (w, h) en metres de chaque vue
    a partir de la boite englobante.
    """
    bx0, bx1, by0, by1, bz0, bz1 = bbox
    dx = bx1 - bx0
    dy = by1 - by0
    dz = bz1 - bz0

    # Projeter la boite sur chaque plan de vue
    # axis = direction X de la coupe (horizontal)
    # normal = perpendiculaire a l'axe (horizontal)
    # up = Z monde

    # Pour simplifier : on utilise les dimensions brutes de la boite
    # face/dos : largeur = projection sur axis, hauteur = dz
    # gauche/droite : largeur = projection sur normal, hauteur = dz
    # dessus/dessous : largeur = projection sur axis, hauteur = projection sur normal
    # coupe : meme que face mais recadre sur la coupe

    ax = plane['axis']
    no = plane['normal']

    # Projeter les diagonales de la boite sur les axes
    corners = [
        (bx0, by0, bz0), (bx1, by0, bz0), (bx0, by1, bz0), (bx1, by1, bz0),
        (bx0, by0, bz1), (bx1, by0, bz1), (bx0, by1, bz1), (bx1, by1, bz1),
    ]
    proj_ax  = [c[0]*ax.x  + c[1]*ax.y  + c[2]*ax.z  for c in corners]
    proj_no  = [c[0]*no.x  + c[1]*no.y  + c[2]*no.z  for c in corners]
    proj_z   = [c[2] for c in corners]

    w_ax = max(proj_ax) - min(proj_ax)    # largeur selon l'axe de coupe
    w_no = max(proj_no) - min(proj_no)    # profondeur selon la normale
    h_z  = max(proj_z)  - min(proj_z)     # hauteur verticale

    dims = {
        'face':    (w_ax, h_z),
        'dos':     (w_ax, h_z),
        'gauche':  (w_no, h_z),
        'droite':  (w_no, h_z),
        'dessus':  (w_ax, w_no),
        'dessous': (w_ax, w_no),
        'coupe':   (w_ax, h_z),
    }
    return dims

# ---------------------------------------------------------------------------
# Calcul des positions des marqueurs (fraction 0..1) dans chaque vue
# ---------------------------------------------------------------------------
def _marker_fracs_for_view(p1, p2, plane, bbox, view_key):
    """
    Projette les 2 marqueurs monde sur le plan de chaque vue orthographique
    et retourne leurs coordonnees en fraction (0..1) de la boite englobante.

    Convention fraction : (0,0) = coin haut-gauche de l'image ortho.
    Cela correspond a la convention des TIFF raster (row=0 en haut).

    Vues laterales (face, dos, gauche, droite, coupe) :
      X papier = projection sur l'axe horizontal de la vue
      Y papier = altitude Z (0=haut du bloc = bz1, 1=bas = bz0)

    Vues plan (dessus, dessous) :
      X papier = projection sur l'axe de coupe (axis)
      Y papier = projection sur la normale (normal)
      Dessus : vu de dessus, Y papier = profondeur depuis l'avant du bloc
      Dessous : vu de dessous, X et Y inverses
    """
    bx0, bx1, by0, by1, bz0, bz1 = bbox
    ax = plane['axis'];   no = plane['normal']

    def proj_ax(p):    return p.x*ax.x + p.y*ax.y + p.z*ax.z
    def proj_no(p):    return p.x*no.x + p.y*no.y + p.z*no.z

    # Bornes de la boite projetee sur chaque axe
    corners_w = []
    for bx in (bx0,bx1):
        for by in (by0,by1):
            for bz in (bz0,bz1):
                import Metashape as _MS
                c = _MS.Vector([bx,by,bz])
                corners_w.append(c)
    ax_vals = [proj_ax(c) for c in corners_w]
    no_vals  = [proj_no(c) for c in corners_w]
    ax_min, ax_max = min(ax_vals), max(ax_vals)
    no_min, no_max = min(no_vals), max(no_vals)
    z_min,  z_max  = bz0, bz1

    def frac(val, mn, mx):
        if mx - mn < 1e-9: return 0.5
        return (val - mn) / (mx - mn)

    # Fractions coherentes avec view_dirs corrigees.
    # right_dir = cross(look, up_dir) donne la direction droite de l'image.
    # frac_x = (proj sur right - min) / (max - min)
    # frac_y = 1 - (proj sur up_dir - min) / (max - min)  [haut image = up_dir max]
    #
    # face/coupe : look=neg_normal, up=+Z, right=cross(neg_normal,+Z)=+axis
    #   frac_x = frac(proj_ax),  frac_y = 1-frac(z)
    # dos       : look=normal,   up=+Z, right=cross(normal,+Z)=-axis
    #   frac_x = 1-frac(proj_ax), frac_y = 1-frac(z)
    # gauche    : look=axis,     up=+Z, right=cross(axis,+Z)=-normal → proj sur -normal = -(proj_no)
    #   frac_x = 1-frac(proj_no), frac_y = 1-frac(z)
    # droite    : look=neg_axis, up=+Z, right=cross(neg_axis,+Z)=normal → proj sur normal = proj_no
    #   NB: right=(0,1,0)=+Y mais proj_no = dot(p,(0,-1,0)) = -p.y
    #   frac_x = 1-frac(proj_no),  (car right=+Y, proj sur +Y = -proj_no, croissant inverse)
    #   En pratique les deux vues lat. gauche/droite ont la meme formule frac_x = 1-frac(proj_no)
    #   mais droite : right=+Y (neg_normal direction) → frac_x = (no_max-proj_no)/(no_max-no_min)
    #   = 1-frac(proj_no)   idem gauche (symetrie attendue car les deux voient la profondeur)
    # dessus    : look=down, up_dir=normal, right=cross(down,normal)=cross(-Z,-Y)=-X=-axis
    #   frac_x = 1-frac(proj_ax),  frac_y = 1-frac(proj_no)
    # dessous   : look=up, up_dir=neg_normal, right=cross(up,neg_normal)=cross(+Z,+Y)=-X=-axis
    #   frac_x = 1-frac(proj_ax),  frac_y = frac(proj_no)
    if view_key in ('face', 'coupe'):
        fx1 = frac(proj_ax(p1), ax_min, ax_max)
        fy1 = 1.0 - frac(p1.z, z_min, z_max)
        fx2 = frac(proj_ax(p2), ax_min, ax_max)
        fy2 = 1.0 - frac(p2.z, z_min, z_max)
    elif view_key == 'dos':
        fx1 = 1.0 - frac(proj_ax(p1), ax_min, ax_max)
        fy1 = 1.0 - frac(p1.z, z_min, z_max)
        fx2 = 1.0 - frac(proj_ax(p2), ax_min, ax_max)
        fy2 = 1.0 - frac(p2.z, z_min, z_max)
    elif view_key in ('gauche', 'droite'):
        # Les deux vues laterales projettent la profondeur (proj_no) en X
        # right = -normal (gauche) ou +neg_normal (droite) — dans les deux cas
        # la direction droite de l'image est opposee a normal croissant
        fx1 = 1.0 - frac(proj_no(p1), no_min, no_max)
        fy1 = 1.0 - frac(p1.z, z_min, z_max)
        fx2 = 1.0 - frac(proj_no(p2), no_min, no_max)
        fy2 = 1.0 - frac(p2.z, z_min, z_max)
    elif view_key == 'dessus':
        # right = -axis, up_dir = normal
        # frac_x = 1-frac(proj_ax),  frac_y = 1-frac(proj_no)
        fx1 = 1.0 - frac(proj_ax(p1), ax_min, ax_max)
        fy1 = 1.0 - frac(proj_no(p1), no_min, no_max)
        fx2 = 1.0 - frac(proj_ax(p2), ax_min, ax_max)
        fy2 = 1.0 - frac(proj_no(p2), no_min, no_max)
    elif view_key == 'dessous':
        # right = -axis, up_dir = neg_normal
        # frac_x = 1-frac(proj_ax),  frac_y = frac(proj_no)
        fx1 = 1.0 - frac(proj_ax(p1), ax_min, ax_max)
        fy1 = frac(proj_no(p1), no_min, no_max)
        fx2 = 1.0 - frac(proj_ax(p2), ax_min, ax_max)
        fy2 = frac(proj_no(p2), no_min, no_max)
    else:
        return None

    return (fx1, fy1, fx2, fy2)


# ---------------------------------------------------------------------------
# Ecriture du fichier .meta.txt
# ---------------------------------------------------------------------------
def write_meta(path, base, plane, bbox, sec, tiffs, real_dims, p1=None, p2=None, mode='ortho'):
    bx0, bx1, by0, by1, bz0, bz1 = bbox
    lines = [
        "script=coupe_bloc",
        "base={0}".format(base),
        "svg_path={0}.svg".format(base),
        "mode={0}".format(mode),
        # Dimensions globales du bloc
        "bloc_w_m={0:.6f}".format(bx1 - bx0),
        "bloc_d_m={0:.6f}".format(by1 - by0),
        "bloc_h_m={0:.6f}".format(bz1 - bz0),
        # Axe de coupe
        "cut_axis_x={0:.6f}".format(plane['axis'].x),
        "cut_axis_y={0:.6f}".format(plane['axis'].y),
        "cut_normal_x={0:.6f}".format(plane['normal'].x),
        "cut_normal_y={0:.6f}".format(plane['normal'].y),
        # Section 2D
        "section_w_m={0:.6f}".format(sec['real_w_m']),
        "section_h_m={0:.6f}".format(sec['real_h_m']),
    ]
    # Chemins TIFF par vue
    for key in VUES:
        val = tiffs.get(key, '') or ''
        lines.append("tiff_{0}={1}".format(key, val))
    # Dimensions reelles par vue
    for key, (w, h) in real_dims.items():
        lines.append("dim_{0}_w={1:.6f}".format(key, w))
        lines.append("dim_{0}_h={1:.6f}".format(key, h))
    # Positions marqueurs par vue (fractions 0..1)
    if p1 is not None and p2 is not None:
        for key in VUES:
            fracs = _marker_fracs_for_view(p1, p2, plane, bbox, key)
            if fracs:
                fx1, fy1, fx2, fy2 = fracs
                lines.append("m1_frac_{0}_x={1:.8f}".format(key, fx1))
                lines.append("m1_frac_{0}_y={1:.8f}".format(key, fy1))
                lines.append("m2_frac_{0}_x={1:.8f}".format(key, fx2))
                lines.append("m2_frac_{0}_y={1:.8f}".format(key, fy2))
                print("  Fracs {0}: M1({1:.3f},{2:.3f}) M2({3:.3f},{4:.3f})".format(
                    key, fx1, fy1, fx2, fy2))

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print("Meta : {0}".format(path))

# ---------------------------------------------------------------------------
# Lancement de coupe_bloc_pdf.exe
# ---------------------------------------------------------------------------
def _find_python():
    """Cherche Python systeme (hors Metashape)."""
    metashape_markers = ["metashape", "agisoft"]
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

    for p in win_candidates:
        if os.path.isfile(p):
            return p

    for name in ["python3", "python", "python3.exe", "python.exe"]:
        for d in os.environ.get("PATH", "").split(os.pathsep):
            d_low = d.lower()
            if any(m in d_low for m in metashape_markers):
                continue
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    return None


def find_pdf_exe():
    """Cherche coupe_bloc_pdf.exe ou coupe_bloc_pdf.py + python."""
    here = os.path.dirname(os.path.abspath(__file__))
    for search in [here] + os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(search, "coupe_bloc_pdf.exe")
        if os.path.isfile(p):
            return [p]
    py_script = os.path.join(here, "coupe_bloc_pdf.py")
    if os.path.isfile(py_script):
        python = _find_python()
        if python:
            return [python, py_script]
    env_val = os.environ.get("COUPE_BLOC_PDF_EXE", "")
    if env_val and os.path.isfile(env_val):
        return [env_val]
    return None


def launch_pdf_exe(meta_path):
    import subprocess

    cmd = find_pdf_exe()
    if not cmd:
        Metashape.app.messageBox(
            "Fichiers SVG/TIFF/meta generes.\n\n"
            "EXE PDF INTROUVABLE : coupe_bloc_pdf.exe\n"
            "Placez l'exe dans le meme dossier que ce script.\n"
            "(compiler avec build_exe.py depuis Anaconda)\n\n"
            "Commande manuelle :\n"
            "  coupe_bloc_pdf.exe \"{0}\"".format(meta_path))
        return

    base_log = meta_path
    for ext in ('.meta.txt', '.meta', '.txt'):
        if base_log.lower().endswith(ext):
            base_log = base_log[:-len(ext)]
            break
    log_path = base_log + '_pdf_log.txt'

    print("Lancement : {0}".format(" ".join(cmd)))

    try:
        kw = {}
        if os.name == 'nt':
            kw['creationflags'] = 0x08000000  # CREATE_NO_WINDOW

        proc = subprocess.Popen(
            cmd + [meta_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kw)

        try:
            stdout, stderr = proc.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            Metashape.app.messageBox(
                "TIMEOUT : l'exe a depasse 5 minutes.\nLog : {0}".format(log_path))
            return

        code = proc.returncode
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
                "PDF genere avec succes !\n\nFichier : {0}\nLog : {1}".format(
                    pdf_path, log_path))
        else:
            lines = log_content.strip().splitlines() if log_content else []
            tail  = "\n".join(lines[-30:]) if lines else "(log vide)"
            out_txt = ""
            for raw in (stdout, stderr):
                if raw:
                    try:
                        out_txt += raw.decode('utf-8', errors='replace')
                    except Exception:
                        pass
            msg = "ECHEC PDF (code {0}).\n\n--- Log ---\n{1}".format(code, tail)
            if out_txt.strip():
                msg += "\n\n--- Sortie ---\n" + out_txt[-800:]
            Metashape.app.messageBox(msg[:3000])

    except Exception as e:
        Metashape.app.messageBox(
            "Erreur lancement exe :\n{0}\n\n"
            "Commande manuelle :\n  coupe_bloc_pdf.exe \"{1}\"".format(e, meta_path))

# ---------------------------------------------------------------------------
# Point d'entree principal
# ---------------------------------------------------------------------------
def main():
    doc   = Metashape.app.document
    chunk = doc.chunk
    if chunk is None:
        Metashape.app.messageBox("Aucun chunk actif.")
        return

    # 1. Selection des 2 marqueurs + mode de rendu + flip normale
    p1, p2, lbl1, lbl2, mode_rendu, vue_orient = get_two_markers(chunk)
    if p1 is None:
        return
    print("Mode rendu PDF : {0}  |  vue_orient : {1}".format(mode_rendu, vue_orient))

    # 2. Plan de coupe
    print("Construction du plan de coupe...")
    plane = build_cut_plane(p1, p2, vue_orient=vue_orient)
    print("  Axe    : ({0:.4f}, {1:.4f}, {2:.4f})".format(
        plane['axis'].x, plane['axis'].y, plane['axis'].z))
    print("  Normal : ({0:.4f}, {1:.4f}, {2:.4f})".format(
        plane['normal'].x, plane['normal'].y, plane['normal'].z))
    print("  Longueur axe : {0:.4f} m".format(plane['axis_len']))

    # 3. Extraction section 3D
    print("Extraction de la section 3D...")
    pts_2d = extract_section_2d(chunk, plane)
    if not pts_2d:
        Metashape.app.messageBox(
            "Aucune intersection trouvee avec le mesh.\n"
            "Verifiez que les marqueurs traversent bien le modele.")
        return

    sec = prepare_section(pts_2d, plane)
    if sec is None:
        Metashape.app.messageBox("Impossible de preparer la section (trop peu de points).")
        return
    print("Section : {0:.3f} m x {1:.3f} m".format(sec['real_w_m'], sec['real_h_m']))

    # 4. Boite englobante du mesh
    bbox = mesh_bbox_world(chunk)
    if bbox is None:
        Metashape.app.messageBox("Impossible de calculer la boite englobante du mesh.")
        return
    print("Bbox monde : X[{0:.3f},{1:.3f}] Y[{2:.3f},{3:.3f}] Z[{4:.3f},{5:.3f}]".format(*bbox))

    # 5. Chemin de sortie
    output_path = Metashape.app.getSaveFileName(
        "Nom de base des fichiers de sortie", filter="SVG (*.svg)")
    if not output_path:
        return
    base = output_path.replace('.svg', '').replace('.SVG', '')
    svg_path  = base + '.svg'
    meta_path = base + '.meta.txt'

    # 6. Export SVG
    write_svg(sec, svg_path)

    # 7. Generation / recuperation des orthomosaiques
    print("Generation des orthomosaiques des 6 vues...")
    tiffs = generate_all_orthos(chunk, doc, plane, bbox, base)

    # Compter les succes
    n_ok = sum(1 for v in tiffs.values() if v is not None)
    print("{0}/{1} orthomosaiques disponibles.".format(n_ok, len(VUES)))

    # 8. Dimensions reelles par vue
    real_dims = view_real_dims(bbox, plane)

    # 9. Meta.txt
    write_meta(meta_path, base, plane, bbox, sec, tiffs, real_dims,
               p1=p1, p2=p2, mode=mode_rendu)

    # 10. Lancement PDF
    launch_pdf_exe(meta_path)


if __name__ == "__main__":
    main()

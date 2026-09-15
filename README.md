# Plugin Metashape — Coupes archéologiques

Plugin pour **Agisoft Metashape Pro** permettant de générer automatiquement des planches PDF de coupes archéologiques à partir de modèles 3D photogrammétriques.

Deux modules indépendants :

| Module | Usage |
|--------|-------|
| **Coupe Céramique** | Section orthographique d'un tesson ou vase céramique — 4 vues + coupe + bol de profil |
| **Coupe Bloc** | 7 vues orthographiques d'un bloc d'architecture (face, dos, gauche, droite, dessus, dessous, coupe) |

---

## Aperçu

Le plugin s'intègre dans Metashape via un **lanceur graphique** (`lanceur_metashape.py`). Il génère :
- Des orthomosaïques TIFF par direction de vue
- Une coupe vectorielle SVG avec hachures
- Une **planche PDF A3 Portrait** à échelle normalisée avec mires graduées

Deux modes de rendu : **orthomosaïque photo** ou **dessin archéologique** (traitement CLAHE + contour Otsu).

---

## Fichiers

```
lanceur_metashape.py          Interface graphique principale (à charger dans Metashape)
coupe_bloc_metashape.py       Module Coupe Bloc — calcul Metashape
coupe_bloc_pdf.py             Module Coupe Bloc — génération PDF
coupe_ceramique7_metashape.py Module Coupe Céramique — calcul Metashape
coupe_ceramique7_pdf.py       Module Coupe Céramique — génération PDF
build_exe.py                  Compilation PyInstaller des générateurs PDF
mode_emploi_coupe_bloc.pdf    Manuel d'utilisation Coupe Bloc
mode_emploi_coupe_ceramique.pdf Manuel d'utilisation Coupe Céramique
```

---

## Prérequis

| Logiciel | Version |
|----------|---------|
| Agisoft Metashape Pro | 1.5+ (2.x recommandé) |
| Python (Anaconda/Miniconda) | 3.8+ |

Dépendances Python (pour compiler les .exe ou lancer les .py directement) :

```bash
pip install reportlab Pillow opencv-python numpy pyinstaller
```

---

## Installation

1. Cloner ou télécharger ce dépôt
2. Placer **tous les fichiers dans un même dossier**
3. Compiler les générateurs PDF (une seule fois) :

```bash
# Depuis Anaconda Prompt, dans le dossier du plugin
python build_exe.py
```

Cela produit `coupe_bloc_pdf.exe` et `coupe_ceramique7_pdf.exe` dans le même dossier.

4. Dans Metashape : **Tools → Run Script → `lanceur_metashape.py`**

---

## Utilisation — Coupe Bloc

1. Ouvrir un projet Metashape avec un mesh reconstruit
2. Placer **2 marqueurs** sur l'axe de coupe souhaité
3. Lancer le script via le lanceur → **▶ Coupe Bloc**
4. Dans le dialogue :
   - Saisir les indices des 2 marqueurs
   - Orienter le modèle 3D sur la **vue de face** (ou dessus) dans Metashape
   - Cocher la case correspondante — la direction de caméra est lue au clic OK
   - Choisir le mode de rendu
5. Choisir le nom du fichier de sortie
6. Le PDF est généré automatiquement

### Planche PDF générée

```
┌────────────────┬──────────────────────┐
│  Vue de face   │  Vue de dessus       │
├────────────────┼──────────────────────┤
│  Vue gauche    │  Coupe (hachures)    │
├────────────────┼──────────────────────┤
│  Vue droite    │  Vue de dos          │
│                ├──────────────────────┤
│                │  Vue de dessous      │
└────────────────┴──────────────────────┘
```

Toutes les vues sont à la **même échelle normalisée** (1:1, 1:2, 1:5, 1:10…), calculée automatiquement depuis les dimensions réelles des TIFF (fichiers `.tfw`).

---

## Utilisation — Coupe Céramique

1. Ouvrir un projet Metashape avec le modèle 3D du tesson
2. Placer **2 marqueurs** de part et d'autre de l'axe de symétrie
3. Lancer → **▶ Coupe Céramique**
4. Suivre le dialogue (choix des marqueurs, mode de rendu)
5. Le PDF est généré automatiquement

---

## Modes de rendu

| Mode | Description |
|------|-------------|
| **Orthomosaïque** | Rendu photo direct, couleur ou niveaux de gris |
| **Dessin archéologique** | Traitement CLAHE (contraste adaptatif), seuillage Otsu, contour principal — style dessin archéo |

---

## Compatibilité Metashape

Le plugin détecte automatiquement la version de l'API Metashape (1.5 à 2.x) et utilise les méthodes disponibles (`buildOrthomosaic`, `exportRaster`, `exportOrthomosaic`).

---

## Auteurs

**M. Belarbi** — Photogrammetrie archeologique  
Développé avec [Claude.ai](https://claude.ai) (Anthropic)

---

## Licence

MIT License — voir [LICENSE](LICENSE)

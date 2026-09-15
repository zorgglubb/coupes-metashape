# Changelog

## [1.0.0] — 2024

### Coupe Bloc
- 7 vues orthographiques (face, dos, gauche, droite, dessus, dessous, coupe)
- Détection automatique de l'orientation via la caméra viewport Metashape
- Dialogue : cocher "Vue de face" ou "Vue de dessus" — les autres vues sont déduites
- Échelle unique normalisée pour toutes les vues, calculée depuis les fichiers TFW
- Mode rendu : orthomosaïque photo ou dessin archéologique (CLAHE + contour Otsu)
- Trait de coupe normalisé sur les vues dessus/dessous
- Suppression de l'orthomosaïque du chunk avant chaque buildOrthomosaic (évite les exports parasites)
- Suppression du TIFF cible avant export (évite la réutilisation silencieuse d'anciens fichiers)
- Mise en page A3 Portrait : col. gauche (face/gauche/droite) + col. droite (dessus/coupe/dos/dessous)

### Coupe Céramique
- 4 vues orthographiques + coupe + profil
- Mode dessin archéologique Q2 (CLAHE raster) et Q4 (overlay vectoriel zones/motifs)
- Planche PDF A3 Portrait

### Lanceur
- Interface graphique sombre unifiée (PySide2/PySide6)
- Boutons Coupe Bloc et Coupe Céramique
- Fallback getString() si PySide non disponible

### Build
- `build_exe.py` v8 : compilation PyInstaller dual-cible (ceramique / bloc)
- Sélection par argument : `python build_exe.py bloc` ou `python build_exe.py ceramique`

### Compatibilité Metashape
- API 1.5 à 2.x : cascade de variantes pour buildOrthomosaic, exportRaster, exportOrthomosaic
- Correction miroir orthomosaïques : inversion right_dir dans matrices méthode A et B
